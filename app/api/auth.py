"""OpenAI 兼容接口的 API 密钥验证，以及管理接口的口令验证"""
import hmac
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.status import (
    HTTP_401_UNAUTHORIZED,
    HTTP_402_PAYMENT_REQUIRED,
    HTTP_403_FORBIDDEN,
    HTTP_503_SERVICE_UNAVAILABLE,
)

from app.config import get_settings
from app.db import AsyncSessionLocal
from app.db.models import ApiKeyModel
from app.db.repository import ApiKeyRepository

_http_bearer = HTTPBearer(auto_error=False)

ADMIN_TOKEN_HEADER = "X-Admin-Token"


def require_admin(request: Request) -> None:
    """管理接口口令校验：未配置 ADMIN_TOKEN 时直接禁用管理接口。"""
    expected = get_settings().admin_token
    if not expected:
        raise HTTPException(
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            detail="管理接口未启用：请在 .env 中配置 ADMIN_TOKEN",
        )
    provided = request.headers.get(ADMIN_TOKEN_HEADER) or ""
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=f"管理口令无效，请在请求头 {ADMIN_TOKEN_HEADER} 中携带正确口令",
        )


async def _extract_api_key(request: Request) -> Optional[str]:
    """优先 Authorization Bearer，其次 X-API-Key"""
    auth: Optional[HTTPAuthorizationCredentials] = await _http_bearer(request)
    if auth and auth.credentials and auth.credentials.startswith("sk-"):
        return auth.credentials
    api_key = request.headers.get("X-API-Key")
    if api_key and api_key.startswith("sk-"):
        return api_key
    return None


async def verify_api_key(
    request: Request,
) -> ApiKeyModel:
    """强制校验 API Key：无效 401，配额用尽 402。"""
    api_key_str = await _extract_api_key(request)
    if not api_key_str:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="缺少 API 密钥。请在请求头中携带 Authorization: Bearer sk-xxx 或 X-API-Key: sk-xxx",
        )

    # 鉴权只使用一个短生命周期 Session，避免推理和流式输出期间占用连接池。
    async with AsyncSessionLocal() as session:
        repo = ApiKeyRepository(session)
        model = await repo.get_by_api_key(api_key_str)
    if not model:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="API 密钥无效或已失效",
        )
    if not model.is_active:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="API 密钥已禁用",
        )
    if model.token_quota <= 0:
        raise HTTPException(
            status_code=HTTP_402_PAYMENT_REQUIRED,
            detail="API 密钥 token 配额已用完，请充值或联系管理员",
        )
    return model
