from typing import Optional

from pydantic import BaseModel, Field


class CreateApiKeyRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100, description="用户名")
    token_quota: int = Field(100000, ge=1, description="token 配额，默认 10 万")
    model: str = Field(..., min_length=1, max_length=128, description="绑定的模型名")


class UpdateApiKeyRequest(BaseModel):
    token_quota: Optional[int] = Field(None, ge=0, description="新的 token 余额")
    is_active: Optional[bool] = Field(None, description="是否启用")


class ApiKeyResponse(BaseModel):
    id: int
    username: str
    api_key: str
    model: str
    token_quota: int
    is_active: bool
    created_at: str


class ApiUsageResponse(BaseModel):
    id: int
    api_key_id: int
    username: str
    period: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    request_count: int
