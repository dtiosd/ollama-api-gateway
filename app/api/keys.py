"""API 密钥管理接口（需 ADMIN_TOKEN 口令）"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_admin
from app.db import get_session
from app.db.models import (
    ApiUsageDayModel,
    ApiUsageModel,
    ApiUsageWeekModel,
    ApiUsageYearModel,
)
from app.db.repository import ApiKeyRepository, ApiUsageRepository
from app.llm.ollama_client import list_ollama_models
from app.schemas import (
    ApiKeyResponse,
    ApiUsageResponse,
    CreateApiKeyRequest,
    UpdateApiKeyRequest,
)

keys_router = APIRouter(
    prefix="/backend/api-keys",
    tags=["API 密钥管理"],
    dependencies=[Depends(require_admin)],
)


def _to_response(model) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=model.id,
        username=model.username,
        api_key=model.api_key,
        model=model.bound_model,
        token_quota=model.token_quota,
        is_active=model.is_active,
        created_at=model.created_at.isoformat(),
    )


def _usage_rows(rows, period_attr: str) -> List[ApiUsageResponse]:
    return [
        ApiUsageResponse(
            id=r.id,
            api_key_id=r.api_key_id,
            username=uname,
            period=getattr(r, period_attr),
            model=r.model_name,
            prompt_tokens=r.prompt_tokens,
            completion_tokens=r.completion_tokens,
            total_tokens=r.total_tokens,
            request_count=r.request_count,
        )
        for r, uname in rows
    ]


def _join_keys(keys) -> str:
    """把聚合出的数组转成逗号分隔文本（过滤空值）。"""
    if not keys:
        return "—"
    values = [str(k) for k in keys if k]
    return "、".join(values) if values else "—"


async def _collect_usage(
    session: AsyncSession,
    model_cls,
    period_attr: str,
    group_by: str,
    username: Optional[str],
    period: Optional[str] = None,
) -> List[ApiUsageResponse]:
    """group_by: username=按用户名汇总（不区分模型）；model=按模型汇总；其余为明细。"""
    repo = ApiUsageRepository(session)
    if group_by in ("username", "model"):
        rows = await repo.list_grouped(
            model_cls, period_attr, group_by, username=username, period=period
        )
        return [
            ApiUsageResponse(
                id=0,
                api_key_id=0,
                username=(
                    r["group_key"]
                    if group_by == "username"
                    else _join_keys(r["extra_keys"])
                ),
                period=r["period"],
                model=r["group_key"] if group_by == "model" else "",
                prompt_tokens=r["prompt_tokens"],
                completion_tokens=r["completion_tokens"],
                total_tokens=r["total_tokens"],
                request_count=r["request_count"],
            )
            for r in rows
        ]
    rows = await repo.list_by(
        model_cls, period_attr, username=username, period=period
    )
    return _usage_rows(rows, period_attr)


@keys_router.post("", response_model=ApiKeyResponse)
async def create_api_key(
    body: CreateApiKeyRequest,
    session: AsyncSession = Depends(get_session),
):
    """生成 API 密钥：同一用户名可为不同模型各建一把"""
    repo = ApiKeyRepository(session)
    username = body.username.strip()
    bound_model = body.model.strip()
    if not bound_model:
        raise HTTPException(status_code=400, detail="请选择绑定的模型")
    existing = await repo.get_by_username_and_model(username, bound_model)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"用户名「{username}」已绑定模型「{bound_model}」",
        )
    try:
        model = await repo.create_api_key(
            username=username, token_quota=body.token_quota, bound_model=bound_model
        )
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"用户名「{username}」已绑定模型「{bound_model}」",
        ) from None
    return _to_response(model)


@keys_router.get("", response_model=List[ApiKeyResponse])
async def list_api_keys(
    username: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """列出 API 密钥，可按用户名筛选"""
    repo = ApiKeyRepository(session)
    models = await repo.list_all(username=username)
    return [_to_response(m) for m in models]


@keys_router.get("/models")
async def list_available_models():
    """管理页用：列出 Ollama 已安装模型，供创建密钥时绑定。"""
    try:
        models = await list_ollama_models()
        names = [m.get("id") for m in models if m.get("id")]
    except Exception:
        names = []
    if not names:
        names = ["qwen2.5:7b", "llama3.2:3b"]
    return {"models": names}


@keys_router.get("/usage/daily", response_model=List[ApiUsageResponse])
async def list_api_usage_daily(
    username: Optional[str] = None,
    group_by: str = "username",
    session: AsyncSession = Depends(get_session),
):
    """按日用量只返回当天记录。"""
    today = datetime.now().strftime("%Y-%m-%d")
    return await _collect_usage(
        session, ApiUsageDayModel, "year_day", group_by, username, period=today
    )


@keys_router.get("/usage/weekly", response_model=List[ApiUsageResponse])
async def list_api_usage_weekly(
    username: Optional[str] = None,
    group_by: str = "username",
    session: AsyncSession = Depends(get_session),
):
    return await _collect_usage(
        session, ApiUsageWeekModel, "year_week", group_by, username
    )


@keys_router.get("/usage/yearly", response_model=List[ApiUsageResponse])
async def list_api_usage_yearly(
    username: Optional[str] = None,
    group_by: str = "username",
    session: AsyncSession = Depends(get_session),
):
    return await _collect_usage(session, ApiUsageYearModel, "year", group_by, username)


@keys_router.get("/usage", response_model=List[ApiUsageResponse])
async def list_api_usage(
    username: Optional[str] = None,
    group_by: str = "username",
    session: AsyncSession = Depends(get_session),
):
    """按月统计用量，默认按用户名汇总"""
    return await _collect_usage(
        session, ApiUsageModel, "year_month", group_by, username
    )


@keys_router.patch("/{api_key_id}", response_model=ApiKeyResponse)
async def update_api_key(
    api_key_id: int,
    body: UpdateApiKeyRequest,
    session: AsyncSession = Depends(get_session),
):
    """调整 token 余额或启用/禁用"""
    if body.token_quota is None and body.is_active is None:
        raise HTTPException(status_code=400, detail="请至少提供 token_quota 或 is_active")
    repo = ApiKeyRepository(session)
    model = None
    if body.token_quota is not None:
        model = await repo.update_quota(api_key_id, body.token_quota)
        if not model:
            raise HTTPException(status_code=404, detail="API 密钥不存在")
    if body.is_active is not None:
        model = await repo.set_active(api_key_id, body.is_active)
        if not model:
            raise HTTPException(status_code=404, detail="API 密钥不存在")
    return _to_response(model)


@keys_router.delete("/{api_key_id}")
async def delete_api_key(
    api_key_id: int,
    session: AsyncSession = Depends(get_session),
):
    """作废删除 API 密钥"""
    repo = ApiKeyRepository(session)
    ok = await repo.delete(api_key_id)
    if not ok:
        raise HTTPException(status_code=404, detail="API 密钥不存在")
    return {"ok": True}
