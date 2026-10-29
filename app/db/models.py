"""API 密钥及用量相关模型"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ApiKeyModel(Base):
    """API 密钥表：同一用户可为不同模型各一把密钥"""

    __tablename__ = "api_key"
    __table_args__ = (
        UniqueConstraint("username", "bound_model", name="uq_api_key_username_model"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(
        String(100), index=True, comment="用户名"
    )
    api_key: Mapped[str] = mapped_column(
        String(80), unique=True, index=True, comment="API 密钥，格式 sk-xxx"
    )
    bound_model: Mapped[str] = mapped_column(
        String(128), default="", index=True, comment="绑定的模型名，该密钥只能调用此模型"
    )
    token_quota: Mapped[int] = mapped_column(
        BigInteger, default=100000, comment="剩余可用 token 数量"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="是否启用；禁用后不可调用模型接口"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="生成时间"
    )


class ApiUsageModel(Base):
    """按月用量"""

    __tablename__ = "api_usage"
    __table_args__ = (
        UniqueConstraint(
            "api_key_id", "year_month", "model_name", name="uq_api_usage_key_month_model"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[int] = mapped_column(
        ForeignKey("api_key.id", ondelete="CASCADE"), index=True, comment="API 密钥 ID"
    )
    year_month: Mapped[str] = mapped_column(String(7), index=True, comment="年月，YYYY-MM")
    model_name: Mapped[str] = mapped_column(String(128), default="", index=True, comment="调用的模型名")
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    completion_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    total_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    request_count: Mapped[int] = mapped_column(Integer, default=0)


class ApiUsageWeekModel(Base):
    """按周用量（ISO 周，YYYY-Www）"""

    __tablename__ = "api_usage_week"
    __table_args__ = (
        UniqueConstraint(
            "api_key_id", "year_week", "model_name", name="uq_api_usage_key_week_model"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[int] = mapped_column(
        ForeignKey("api_key.id", ondelete="CASCADE"), index=True
    )
    year_week: Mapped[str] = mapped_column(String(8), index=True, comment="ISO 周，YYYY-Www")
    model_name: Mapped[str] = mapped_column(String(128), default="", index=True, comment="调用的模型名")
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    completion_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    total_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    request_count: Mapped[int] = mapped_column(Integer, default=0)


class ApiUsageDayModel(Base):
    """按日用量（YYYY-MM-DD）"""

    __tablename__ = "api_usage_day"
    __table_args__ = (
        UniqueConstraint(
            "api_key_id", "year_day", "model_name", name="uq_api_usage_key_day_model"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[int] = mapped_column(
        ForeignKey("api_key.id", ondelete="CASCADE"), index=True
    )
    year_day: Mapped[str] = mapped_column(String(10), index=True, comment="日期，YYYY-MM-DD")
    model_name: Mapped[str] = mapped_column(String(128), default="", index=True, comment="调用的模型名")
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    completion_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    total_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    request_count: Mapped[int] = mapped_column(Integer, default=0)


class ApiUsageYearModel(Base):
    """按年用量（YYYY）"""

    __tablename__ = "api_usage_year"
    __table_args__ = (
        UniqueConstraint(
            "api_key_id", "year", "model_name", name="uq_api_usage_key_year_model"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[int] = mapped_column(
        ForeignKey("api_key.id", ondelete="CASCADE"), index=True
    )
    year: Mapped[str] = mapped_column(String(4), index=True, comment="年份，YYYY")
    model_name: Mapped[str] = mapped_column(String(128), default="", index=True, comment="调用的模型名")
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    completion_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    total_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
