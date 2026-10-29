"""langchain-ollama ChatOllama 适配：多模态、思考、工具调用、流式/非流式"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from functools import lru_cache
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_ollama import ChatOllama

from app.config import get_settings
from app.schemas.chat import ChatCompletionRequest, ChatMessage

_http_client: httpx.AsyncClient | None = None
_http_client_lock = asyncio.Lock()
_models_cache: List[Dict[str, Any]] = []
_models_cache_expires_at = 0.0


def _convert_content(content: Any) -> Any:
    """OpenAI content -> langchain content（支持多模态 image_url）"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)

    parts: List[Dict[str, Any]] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        t = item.get("type")
        if t == "text":
            parts.append({"type": "text", "text": item.get("text", "")})
        elif t == "image_url":
            image_url = item.get("image_url") or {}
            url = image_url.get("url") if isinstance(image_url, dict) else image_url
            if url:
                parts.append({"type": "image_url", "image_url": {"url": url}})
    return parts if parts else ""


def _openai_tool_calls_to_lc(tool_calls: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """OpenAI tool_calls -> langchain tool_calls ({id,name,args})"""
    if not tool_calls:
        return []
    converted: List[Dict[str, Any]] = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        if "function" in tc:
            fn = tc.get("function") or {}
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args else {}
                except json.JSONDecodeError:
                    args = {"raw": args}
            converted.append(
                {
                    "id": tc.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                    "name": fn.get("name") or "",
                    "args": args if isinstance(args, dict) else {"value": args},
                    "type": "tool_call",
                }
            )
        else:
            args = tc.get("args") or {}
            converted.append(
                {
                    "id": tc.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                    "name": tc.get("name") or "",
                    "args": args if isinstance(args, dict) else {"value": args},
                    "type": "tool_call",
                }
            )
    return converted


def openai_messages_to_lc(messages: List[ChatMessage]) -> List[BaseMessage]:
    result: List[BaseMessage] = []
    for msg in messages:
        role = msg.role
        content = _convert_content(msg.content)
        if role == "system":
            result.append(SystemMessage(content=content))
        elif role == "user":
            result.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_tool_calls = _openai_tool_calls_to_lc(msg.tool_calls)
            if lc_tool_calls:
                result.append(
                    AIMessage(content=content or "", tool_calls=lc_tool_calls)
                )
            else:
                result.append(AIMessage(content=content or ""))
        elif role == "tool":
            result.append(
                ToolMessage(
                    content=content if isinstance(content, str) else json.dumps(content),
                    tool_call_id=msg.tool_call_id or "",
                )
            )
    return result


@lru_cache(maxsize=64)
def _cached_llm(
    model: str,
    base_url: str,
    temperature: float,
    reasoning: bool,
    top_p: float | None,
    max_tokens: int | None,
) -> ChatOllama:
    kwargs: Dict[str, Any] = {
        "model": model,
        "base_url": base_url,
        "temperature": temperature,
        "reasoning": reasoning,
    }
    if top_p is not None:
        kwargs["top_p"] = top_p
    if max_tokens is not None:
        kwargs["num_predict"] = max_tokens
    return ChatOllama(**kwargs)


def build_llm(req: ChatCompletionRequest) -> Any:
    settings = get_settings()
    model = req.model or settings.ollama_default_model
    if not model:
        raise ValueError("未指定 model，且未配置 OLLAMA_DEFAULT_MODEL")
    llm = _cached_llm(
        model,
        settings.ollama_base_url,
        req.temperature if req.temperature is not None else 0.7,
        req.resolve_think(),
        req.top_p,
        req.max_tokens,
    )
    if req.tools:
        llm = llm.bind_tools(req.tools, tool_choice=req.tool_choice)
    return llm


def _extract_usage(msg: BaseMessage) -> Dict[str, int]:
    meta = getattr(msg, "usage_metadata", None) or {}
    if meta:
        prompt = int(meta.get("input_tokens") or 0)
        completion = int(meta.get("output_tokens") or 0)
        total = int(meta.get("total_tokens") or (prompt + completion))
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        }

    resp_meta = getattr(msg, "response_metadata", None) or {}
    prompt = int(resp_meta.get("prompt_eval_count") or 0)
    completion = int(resp_meta.get("eval_count") or 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


def _tool_calls_openai(msg: BaseMessage) -> Optional[List[Dict[str, Any]]]:
    tool_calls = getattr(msg, "tool_calls", None) or []
    if not tool_calls:
        additional = getattr(msg, "additional_kwargs", None) or {}
        tool_calls = additional.get("tool_calls") or []
    if not tool_calls:
        return None

    result = []
    for tc in tool_calls:
        if isinstance(tc, dict):
            if "function" in tc:
                result.append(tc)
                continue
            args = tc.get("args") or tc.get("arguments") or {}
            if not isinstance(args, str):
                args = json.dumps(args, ensure_ascii=False)
            result.append(
                {
                    "id": tc.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": tc.get("name") or "",
                        "arguments": args,
                    },
                }
            )
        else:
            name = getattr(tc, "name", "") or ""
            args = getattr(tc, "args", {}) or {}
            if not isinstance(args, str):
                args = json.dumps(args, ensure_ascii=False)
            result.append(
                {
                    "id": getattr(tc, "id", None) or f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {"name": name, "arguments": args},
                }
            )
    return result or None


def _reasoning_content(msg: BaseMessage) -> Optional[str]:
    additional = getattr(msg, "additional_kwargs", None) or {}
    for key in ("reasoning_content", "reasoning", "thinking"):
        val = additional.get(key)
        if val:
            return str(val)
    meta = getattr(msg, "response_metadata", None) or {}
    for key in ("reasoning_content", "reasoning", "thinking"):
        val = meta.get(key)
        if val:
            return str(val)
    return None


def message_to_openai_completion(msg: BaseMessage, model: str) -> Dict[str, Any]:
    usage = _extract_usage(msg)
    tool_calls = _tool_calls_openai(msg)
    content = msg.content
    if isinstance(content, list):
        texts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                texts.append(p.get("text", ""))
            elif isinstance(p, str):
                texts.append(p)
        content = "".join(texts)

    message: Dict[str, Any] = {
        "role": "assistant",
        "content": content if content else (None if tool_calls else ""),
    }
    if tool_calls:
        message["tool_calls"] = tool_calls
    reasoning = _reasoning_content(msg)
    if reasoning:
        message["reasoning_content"] = reasoning

    finish_reason = "tool_calls" if tool_calls else "stop"
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }
        ],
        "usage": usage,
    }


def chunk_to_openai_delta(
    chunk: AIMessageChunk,
    model: str,
    completion_id: str,
    *,
    include_role: bool = False,
) -> Dict[str, Any]:
    content = chunk.content
    if isinstance(content, list):
        texts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                texts.append(p.get("text", ""))
            elif isinstance(p, str):
                texts.append(p)
        content = "".join(texts)

    delta: Dict[str, Any] = {}
    if include_role:
        delta["role"] = "assistant"
    if content:
        delta["content"] = content

    reasoning = _reasoning_content(chunk)
    if reasoning:
        delta["reasoning_content"] = reasoning

    tool_calls = _tool_calls_openai(chunk)
    if tool_calls:
        delta["tool_calls"] = [
            {
                "index": i,
                "id": tc["id"],
                "type": "function",
                "function": tc["function"],
            }
            for i, tc in enumerate(tool_calls)
        ]

    return {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": None,
            }
        ],
    }


async def chat_complete(req: ChatCompletionRequest) -> Tuple[Dict[str, Any], Dict[str, int]]:
    llm = build_llm(req)
    messages = openai_messages_to_lc(req.messages)
    msg = await llm.ainvoke(messages)
    model = req.model or get_settings().ollama_default_model
    result = message_to_openai_completion(msg, model)
    return result, result["usage"]


async def chat_stream(
    req: ChatCompletionRequest,
) -> AsyncIterator[Tuple[str, Optional[Dict[str, int]]]]:
    """
    产出 (sse_data_json_or_DONE, usage_or_None)。
    最后 yield ("[DONE]", usage)。
    """
    llm = build_llm(req)
    messages = openai_messages_to_lc(req.messages)
    model = req.model or get_settings().ollama_default_model
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    first = True
    usage: Dict[str, int] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    finish_reason = "stop"

    async for chunk in llm.astream(messages):
        if not isinstance(chunk, AIMessageChunk):
            chunk = AIMessageChunk(content=getattr(chunk, "content", "") or "")

        payload = chunk_to_openai_delta(chunk, model, completion_id, include_role=first)
        first = False

        u = _extract_usage(chunk)
        if u["total_tokens"]:
            usage = u
        if _tool_calls_openai(chunk):
            finish_reason = "tool_calls"

        yield json.dumps(payload, ensure_ascii=False), None

    end_payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": finish_reason,
            }
        ],
        "usage": usage,
    }
    yield json.dumps(end_payload, ensure_ascii=False), usage
    yield "[DONE]", usage


async def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        async with _http_client_lock:
            if _http_client is None:
                _http_client = httpx.AsyncClient(
                    timeout=30.0,
                    limits=httpx.Limits(
                        max_connections=20,
                        max_keepalive_connections=10,
                    ),
                )
    return _http_client


async def embed_texts(model: str, inputs: List[str]) -> Tuple[List[List[float]], int]:
    """调用 Ollama 生成向量，返回 (向量列表, prompt token 数)。

    优先 /api/embed（Ollama >= 0.5），老版本回退到 /api/embeddings 逐条调用。
    """
    client = await _get_http_client()
    base = get_settings().ollama_base_url.rstrip("/")

    resp = await client.post(
        f"{base}/api/embed", json={"model": model, "input": inputs}, timeout=60.0
    )
    if resp.status_code == 404:
        vectors: List[List[float]] = []
        prompt_tokens = 0
        for text in inputs:
            single = await client.post(
                f"{base}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=60.0,
            )
            single.raise_for_status()
            data = single.json()
            vectors.append(data.get("embedding") or [])
            prompt_tokens += int(data.get("prompt_eval_count") or 0)
        return vectors, prompt_tokens

    resp.raise_for_status()
    data = resp.json()
    return data.get("embeddings") or [], int(data.get("prompt_eval_count") or 0)


async def list_ollama_models() -> List[Dict[str, Any]]:
    global _models_cache, _models_cache_expires_at

    settings = get_settings()
    now = time.monotonic()
    if _models_cache and now < _models_cache_expires_at:
        return list(_models_cache)

    client = await _get_http_client()

    url = f"{settings.ollama_base_url.rstrip('/')}/api/tags"
    resp = await client.get(url)
    resp.raise_for_status()
    data = resp.json()

    models = []
    created = int(time.time())
    for m in data.get("models") or []:
        name = m.get("name") or m.get("model") or ""
        if not name:
            continue
        models.append(
            {
                "id": name,
                "object": "model",
                "created": created,
                "owned_by": "ollama",
            }
        )
    _models_cache = models
    _models_cache_expires_at = now + settings.ollama_models_cache_ttl
    return list(models)


async def close_ollama_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
