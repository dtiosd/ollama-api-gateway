"""OpenAI 兼容聊天与向量接口"""
from __future__ import annotations

import json
import logging
from typing import Dict, List

import base64
import struct

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from app.api.auth import verify_api_key
from app.config import get_settings
from app.db import AsyncSessionLocal
from app.db.models import ApiKeyModel
from app.db.repository import ApiUsageRepository
from app.llm.concurrency import ModelQueueTimeoutError, ollama_concurrency
from app.llm.ollama_client import (
    chat_complete,
    chat_stream,
    embed_texts,
    list_ollama_models,
)
from app.schemas.chat import ChatCompletionRequest, EmbeddingRequest

logger = logging.getLogger(__name__)

chat_router = APIRouter(prefix="/v1", tags=["OpenAI 兼容"])


async def _record_usage(
    api_key_id: int,
    usage: Dict[str, int],
    model: str,
) -> None:
    total = int(usage.get("total_tokens") or 0)
    if total <= 0:
        return

    async with AsyncSessionLocal() as session:
        usage_repo = ApiUsageRepository(session)
        await usage_repo.record_usage_and_deduct(
            api_key_id,
            int(usage.get("prompt_tokens") or 0),
            int(usage.get("completion_tokens") or 0),
            total,
            model,
        )


@chat_router.get("/models")
async def get_models(
    api_key_model: ApiKeyModel = Depends(verify_api_key),
):
    bound = (api_key_model.bound_model or "").strip()
    try:
        models = await list_ollama_models()
    except Exception as e:
        logger.exception("列出 Ollama 模型失败")
        raise HTTPException(status_code=502, detail=f"无法连接 Ollama: {e}") from e
    if bound:
        matched = [m for m in models if m.get("id") == bound]
        if matched:
            return {"object": "list", "data": matched}
        return {
            "object": "list",
            "data": [{"id": bound, "object": "model", "created": 0, "owned_by": "ollama"}],
        }
    return {"object": "list", "data": models}


def _encode_embedding(vector: List[float], encoding_format: str):
    if encoding_format == "base64":
        raw = struct.pack(f"<{len(vector)}f", *vector)
        return base64.b64encode(raw).decode("ascii")
    return [float(x) for x in vector]


@chat_router.post("/embeddings")
async def create_embeddings(
    body: EmbeddingRequest,
    api_key_model: ApiKeyModel = Depends(verify_api_key),
):
    """OpenAI 兼容向量接口：转发 Ollama /api/embed，计入用量与配额。"""
    inputs = [t for t in body.texts() if t is not None]
    if not inputs:
        raise HTTPException(status_code=400, detail="input 不能为空")
    if any(not isinstance(t, str) for t in inputs):
        raise HTTPException(status_code=400, detail="input 必须是字符串或字符串数组")

    bound = (api_key_model.bound_model or "").strip()
    model = body.model or bound or get_settings().ollama_default_model
    if not model:
        raise HTTPException(status_code=400, detail="未指定 model，且未配置默认模型")
    if bound and model != bound:
        raise HTTPException(status_code=403, detail="您调用的模型未找到")

    try:
        lease = await ollama_concurrency.acquire(model)
    except ModelQueueTimeoutError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e

    try:
        try:
            vectors, prompt_tokens = await embed_texts(model, inputs)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(
                    status_code=400, detail=f"模型 {model} 不存在或不支持 embedding"
                ) from e
            logger.exception("embedding 调用失败")
            raise HTTPException(
                status_code=502, detail=f"模型调用失败: {e.response.text[:200]}"
            ) from e
        except Exception as e:
            logger.exception("embedding 调用失败")
            raise HTTPException(status_code=502, detail=f"模型调用失败: {e}") from e
    finally:
        lease.release()

    if len(vectors) != len(inputs):
        raise HTTPException(
            status_code=502, detail=f"模型 {model} 未返回向量，请确认其为 embedding 模型"
        )

    usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": 0,
        "total_tokens": prompt_tokens,
    }
    await _record_usage(api_key_model.id, usage, model)

    return JSONResponse(
        content={
            "object": "list",
            "model": model,
            "data": [
                {
                    "object": "embedding",
                    "index": i,
                    "embedding": _encode_embedding(v, body.encoding_format),
                }
                for i, v in enumerate(vectors)
            ],
            "usage": usage,
        }
    )


@chat_router.post("/chat/completions")
async def create_chat_completions(
    body: ChatCompletionRequest,
    api_key_model: ApiKeyModel = Depends(verify_api_key),
):
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages 不能为空")

    api_key_id = api_key_model.id
    bound = (api_key_model.bound_model or "").strip()
    model = body.model or bound or get_settings().ollama_default_model
    if not model:
        raise HTTPException(status_code=400, detail="未指定 model，且未配置默认模型")
    if bound and model != bound:
        raise HTTPException(
            status_code=403,
            detail="您调用的模型未找到",
        )
    try:
        lease = await ollama_concurrency.acquire(model)
    except ModelQueueTimeoutError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e

    if body.stream:
        async def event_generator():
            final_usage: Dict[str, int] | None = None
            try:
                async for data, usage in chat_stream(body):
                    if usage:
                        final_usage = usage
                    if data == "[DONE]":
                        yield {"data": "[DONE]"}
                    else:
                        yield {"data": data}
            except Exception as e:
                logger.exception("流式聊天失败")
                err = {
                    "error": {
                        "message": str(e),
                        "type": "server_error",
                    }
                }
                yield {"data": json.dumps(err, ensure_ascii=False)}
                yield {"data": "[DONE]"}
            finally:
                lease.release()
                if final_usage:
                    try:
                        await _record_usage(api_key_id, final_usage, model)
                    except Exception:
                        logger.exception("流式用量记账失败")

        return EventSourceResponse(event_generator())

    try:
        try:
            result, usage = await chat_complete(body)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.exception("非流式聊天失败")
            raise HTTPException(status_code=502, detail=f"模型调用失败: {e}") from e
    finally:
        lease.release()

    await _record_usage(api_key_id, usage, model)
    return JSONResponse(content=result)
