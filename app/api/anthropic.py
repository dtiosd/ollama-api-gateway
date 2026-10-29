"""Anthropic Messages 兼容接口，供 Claude Code / CC Switch 调用。"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sse_starlette.sse import EventSourceResponse

from app.api.auth import verify_api_key
from app.api.chat import _record_usage
from app.config import get_settings
from app.db.models import ApiKeyModel
from app.llm.anthropic import (
    AnthropicStreamBuilder,
    estimate_input_tokens,
    model_missing,
    openai_completion_to_anthropic,
    to_chat_request,
)
from app.llm.concurrency import ModelQueueTimeoutError, ollama_concurrency
from app.llm.ollama_client import chat_complete

logger = logging.getLogger(__name__)

anthropic_router = APIRouter(prefix="/anthropic", tags=["Anthropic 兼容"])


class AnthropicMessagesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: Optional[str] = None
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    max_tokens: Optional[int] = None
    system: Optional[Any] = None
    stream: bool = False
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None
    thinking: Optional[Dict[str, Any]] = None


def _error(status: int, message: str, err_type: str = "invalid_request_error") -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"type": "error", "error": {"type": err_type, "message": message}},
    )


def _resolve_model(requested: Optional[str], api_key_model: ApiKeyModel) -> str | JSONResponse:
    bound = (api_key_model.bound_model or "").strip()
    model = (requested or "").strip() or bound or get_settings().ollama_default_model
    if not model:
        return _error(400, "未指定 model，且未配置默认模型")
    if bound and model != bound:
        return _error(403, "您调用的模型未找到", "permission_error")
    return model


def _failure(exc: Exception, model: str) -> JSONResponse:
    if isinstance(exc, ModelQueueTimeoutError):
        return _error(429, str(exc), "rate_limit_error")
    if isinstance(exc, ValueError):
        return _error(400, str(exc))
    if model_missing(exc):
        return _error(404, f"模型 {model} 不存在", "not_found_error")
    return _error(502, f"模型调用失败: {exc}", "api_error")


def _stream_error(exc: Exception, model: str) -> Dict[str, str]:
    failure = _failure(exc, model)
    payload = json.loads(failure.body.decode("utf-8"))
    return {"event": "error", "data": json.dumps(payload, ensure_ascii=False)}


async def _prepare(body: AnthropicMessagesRequest, api_key_model: ApiKeyModel):
    if not body.messages:
        return _error(400, "messages 不能为空")
    model = _resolve_model(body.model, api_key_model)
    if isinstance(model, JSONResponse):
        return model
    try:
        openai_req = to_chat_request(body, model)
    except Exception as exc:
        logger.exception("Anthropic 请求转换失败")
        return _error(400, f"请求格式无法解析: {exc}")
    if not any(msg.role in ("user", "assistant", "tool") for msg in openai_req.messages):
        return _error(400, "messages 不能为空")
    try:
        lease = await ollama_concurrency.acquire(model)
    except ModelQueueTimeoutError as exc:
        return _error(429, str(exc), "rate_limit_error")
    return model, openai_req, lease


@anthropic_router.post("/v1/messages")
async def create_message(
    body: AnthropicMessagesRequest,
    api_key_model: ApiKeyModel = Depends(verify_api_key),
):
    prepared = await _prepare(body, api_key_model)
    if isinstance(prepared, JSONResponse):
        return prepared
    model, openai_req, lease = prepared
    api_key_id = api_key_model.id

    if body.stream:
        builder = AnthropicStreamBuilder(
            model,
            estimate_input_tokens(body.system, body.messages, body.tools),
        )

        async def event_generator():
            try:
                async for event in builder.stream(openai_req):
                    yield event
            except Exception as exc:
                logger.exception("Anthropic 流式聊天失败")
                yield _stream_error(exc, model)
            finally:
                lease.release()
                usage = builder.usage_for_billing()
                if usage["total_tokens"]:
                    try:
                        await _record_usage(api_key_id, usage, model)
                    except Exception:
                        logger.exception("Anthropic 流式用量记账失败")

        return EventSourceResponse(event_generator())

    try:
        try:
            result, usage = await chat_complete(openai_req)
        except Exception as exc:
            logger.exception("Anthropic 非流式聊天失败")
            return _failure(exc, model)
    finally:
        lease.release()

    await _record_usage(api_key_id, usage, model)
    return JSONResponse(content=openai_completion_to_anthropic(result))


@anthropic_router.post("/v1/messages/count_tokens")
async def count_tokens(
    body: AnthropicMessagesRequest,
    api_key_model: ApiKeyModel = Depends(verify_api_key),
):
    model = _resolve_model(body.model, api_key_model)
    if isinstance(model, JSONResponse):
        return model
    return {"input_tokens": estimate_input_tokens(body.system, body.messages, body.tools)}
