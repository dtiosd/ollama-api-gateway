"""API 密钥及用量仓储"""
from __future__ import annotations

import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ApiKeyModel,
    ApiUsageDayModel,
    ApiUsageModel,
    ApiUsageWeekModel,
    ApiUsageYearModel,
)


class ApiKeyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_api_key(self, api_key: str) -> Optional[ApiKeyModel]:
        result = await self.session.execute(
            select(ApiKeyModel).where(ApiKeyModel.api_key == api_key)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, api_key_id: int) -> Optional[ApiKeyModel]:
        result = await self.session.execute(
            select(ApiKeyModel).where(ApiKeyModel.id == api_key_id)
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> Optional[ApiKeyModel]:
        result = await self.session.execute(
            select(ApiKeyModel).where(ApiKeyModel.username == username)
        )
        return result.scalar_one_or_none()

    async def get_by_username_and_model(
        self, username: str, bound_model: str
    ) -> Optional[ApiKeyModel]:
        result = await self.session.execute(
            select(ApiKeyModel).where(
                ApiKeyModel.username == username,
                ApiKeyModel.bound_model == bound_model,
            )
        )
        return result.scalar_one_or_none()

    async def create_api_key(
        self, username: str, token_quota: int = 100000, bound_model: str = ""
    ) -> ApiKeyModel:
        api_key = f"sk-{secrets.token_hex(16)}"
        model = ApiKeyModel(
            username=username,
            api_key=api_key,
            token_quota=token_quota,
            bound_model=(bound_model or "").strip(),
            is_active=True,
        )
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return model

    async def list_all(self, username: Optional[str] = None) -> list[ApiKeyModel]:
        stmt = select(ApiKeyModel).order_by(ApiKeyModel.id.desc())
        if username:
            stmt = stmt.where(ApiKeyModel.username == username)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_quota(self, api_key_id: int, token_quota: int) -> Optional[ApiKeyModel]:
        model = await self.get_by_id(api_key_id)
        if not model:
            return None
        model.token_quota = token_quota
        await self.session.commit()
        await self.session.refresh(model)
        return model

    async def set_active(self, api_key_id: int, is_active: bool) -> Optional[ApiKeyModel]:
        model = await self.get_by_id(api_key_id)
        if not model:
            return None
        model.is_active = is_active
        await self.session.commit()
        await self.session.refresh(model)
        return model

    async def delete(self, api_key_id: int) -> bool:
        model = await self.get_by_id(api_key_id)
        if not model:
            return False
        await self.session.delete(model)
        await self.session.commit()
        return True

    async def deduct_tokens(self, api_key_id: int, total_tokens: int) -> bool:
        model = await self.get_by_id(api_key_id)
        if not model:
            return False
        model.token_quota -= total_tokens
        await self.session.commit()
        return True


class ApiUsageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_usage_and_deduct(
        self,
        api_key_id: int,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        model_name: str,
    ) -> bool:
        """在一个事务内按模型累计日、周、月、年用量，并扣减余额。"""
        now = datetime.now()
        model_name = (model_name or "")[:128]
        async with self.session.begin():
            result = await self.session.execute(
                update(ApiKeyModel)
                .where(ApiKeyModel.id == api_key_id)
                .values(token_quota=ApiKeyModel.token_quota - total_tokens)
            )
            if result.rowcount == 0:
                return False

            await self._upsert_atomic(
                ApiUsageDayModel, "year_day", now.strftime("%Y-%m-%d"),
                api_key_id, model_name, prompt_tokens, completion_tokens, total_tokens,
            )
            await self._upsert_atomic(
                ApiUsageWeekModel, "year_week", now.strftime("%G-W%V"),
                api_key_id, model_name, prompt_tokens, completion_tokens, total_tokens,
            )
            await self._upsert_atomic(
                ApiUsageModel, "year_month", now.strftime("%Y-%m"),
                api_key_id, model_name, prompt_tokens, completion_tokens, total_tokens,
            )
            await self._upsert_atomic(
                ApiUsageYearModel, "year", now.strftime("%Y"),
                api_key_id, model_name, prompt_tokens, completion_tokens, total_tokens,
            )
        return True

    async def _upsert_atomic(
        self,
        model_cls,
        period_attr: str,
        period_value: str,
        api_key_id: int,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
    ) -> None:
        period_col = getattr(model_cls, period_attr)
        statement = pg_insert(model_cls).values(
            api_key_id=api_key_id,
            model_name=model_name,
            **{period_attr: period_value},
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            request_count=1,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[model_cls.api_key_id, period_col, model_cls.model_name],
            set_={
                "prompt_tokens": model_cls.prompt_tokens + statement.excluded.prompt_tokens,
                "completion_tokens": (
                    model_cls.completion_tokens + statement.excluded.completion_tokens
                ),
                "total_tokens": model_cls.total_tokens + statement.excluded.total_tokens,
                "request_count": model_cls.request_count + 1,
            },
        )
        await self.session.execute(statement)

    async def list_by(
        self,
        model_cls,
        period_attr: str,
        username: Optional[str] = None,
        period: Optional[str] = None,
    ) -> list[tuple[object, str]]:
        period_col = getattr(model_cls, period_attr)
        stmt = (
            select(model_cls, ApiKeyModel.username)
            .join(ApiKeyModel, model_cls.api_key_id == ApiKeyModel.id)
            .order_by(period_col.desc(), ApiKeyModel.username, model_cls.model_name)
        )
        if username:
            stmt = stmt.where(ApiKeyModel.username == username)
        if period:
            stmt = stmt.where(period_col == period)
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def list_grouped(
        self,
        model_cls,
        period_attr: str,
        group_by: str,
        username: Optional[str] = None,
        period: Optional[str] = None,
    ) -> list[dict]:
        """按用户名或模型聚合用量（不区分另一维度），返回 dict 列表。"""
        period_col = getattr(model_cls, period_attr)
        group_col = (
            ApiKeyModel.username if group_by == "username" else model_cls.model_name
        )
        # 按模型汇总时附带涉及的用户名；按用户名汇总时附带涉及的模型
        extra_col = model_cls.model_name if group_by == "username" else ApiKeyModel.username
        stmt = (
            select(
                period_col.label("period"),
                group_col.label("group_key"),
                func.array_agg(func.distinct(extra_col)).label("extra_keys"),
                func.coalesce(func.sum(model_cls.prompt_tokens), 0).label("prompt_tokens"),
                func.coalesce(func.sum(model_cls.completion_tokens), 0).label(
                    "completion_tokens"
                ),
                func.coalesce(func.sum(model_cls.total_tokens), 0).label("total_tokens"),
                func.coalesce(func.sum(model_cls.request_count), 0).label("request_count"),
            )
            .join(ApiKeyModel, model_cls.api_key_id == ApiKeyModel.id)
            .group_by(period_col, group_col)
            .order_by(period_col.desc(), group_col)
        )
        if username:
            stmt = stmt.where(ApiKeyModel.username == username)
        if period:
            stmt = stmt.where(period_col == period)
        result = await self.session.execute(stmt)
        return [dict(row._mapping) for row in result.all()]
