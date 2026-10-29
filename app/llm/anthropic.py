"""Anthropic Messages API 与内部 OpenAI 请求之间的转换。"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessageChunk

from app.llm.ollama_client import (
    _extract_usage,
    _reasoning_content,
    _tool_calls_openai,
    build_llm,
    openai_messages_to_lc,
)
from app.schemas.chat import ChatCompletionRequest, ChatMessage


def estimate_input_tokens(system: Any, messages: Any, tools: Any) -> int:
    try:
        blob = json.dumps(
            {"system": system, "messages": messages, "tools": tools},
            ensure_ascii=False,
            default=str,
        )
    except TypeError:
        blob = f"{system}{messages}"
    return max(1, len(blob) // 4) if blob else 0


def model_missing(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(token in text for token in ("not found", "does not exist", "unknown model"))


def _system_text(system: Any) -> str:
    if system is None:
        return ""
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        parts: List[str] = []
        for block in system:
            if isinstance(block, str):
                if block:
                    parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text") or ""
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    return str(system)


def _image_part(block: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    source = block.get("source") or {}
    if not isinstance(source, dict):
        return None
    if source.get("type") == "base64":
        media = source.get("media_type") or "image/png"
        data = source.get("data") or ""
        if not data:
            return None
        url = f"data:{media};base64,{data}"
    elif source.get("type") == "url":
        url = source.get("url") or ""
        if not url:
            return None
    else:
        return None
    return {"type": "image_url", "image_url": {"url": url}}


def _document_text(block: Dict[str, Any]) -> str:
    source = block.get("source") or {}
    if isinstance(source, dict) and source.get("type") == "text":
        return str(source.get("data") or "")
    media = ""
    if isinstance(source, dict):
        media = str(source.get("media_type") or "")
    return f"[document{': ' + media if media else ''}]"


def _tool_result_text(content: Any, is_error: bool) -> str:
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text" or "text" in block:
                    parts.append(str(block.get("text") or ""))
                elif block.get("type") == "image":
                    parts.append("[image]")
        text = "\n".join(p for p in parts if p)
    elif content is None:
        text = ""
    else:
        text = json.dumps(content, ensure_ascii=False)
    if is_error:
        return f"Error: {text}" if text else "Error"
    return text


def _user_to_messages(content: Any) -> List[ChatMessage]:
    if isinstance(content, str):
        return [ChatMessage(role="user", content=content)]
    if not isinstance(content, list):
        return [ChatMessage(role="user", content="" if content is None else str(content))]

    out: List[ChatMessage] = []
    parts: List[Dict[str, Any]] = []

    def flush_parts() -> None:
        nonlocal parts
        if not parts:
            return
        if len(parts) == 1 and parts[0].get("type") == "text":
            out.append(ChatMessage(role="user", content=parts[0].get("text") or ""))
        else:
            out.append(ChatMessage(role="user", content=parts))
        parts = []

    for block in content:
        if isinstance(block, str):
            if block:
                parts.append({"type": "text", "text": block})
            continue
        if not isinstance(block, dict):
            continue
        btype = block.get("type") or ""
        if btype == "tool_result":
            flush_parts()
            out.append(
                ChatMessage(
                    role="tool",
                    content=_tool_result_text(block.get("content"), bool(block.get("is_error"))),
                    tool_call_id=str(block.get("tool_use_id") or ""),
                )
            )
        elif btype == "image":
            image = _image_part(block)
            if image:
                parts.append(image)
        elif btype == "document":
            parts.append({"type": "text", "text": _document_text(block)})
        elif btype in ("thinking", "redacted_thinking"):
            continue
        else:
            text = block.get("text") or ""
            if text or btype == "text":
                parts.append({"type": "text", "text": str(text)})
    flush_parts()
    return out


def _tool_arguments(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        return json.dumps(raw, ensure_ascii=False)
    if raw is None:
        return "{}"
    return json.dumps(raw, ensure_ascii=False)


def _assistant_to_message(content: Any) -> ChatMessage:
    if isinstance(content, str):
        return ChatMessage(role="assistant", content=content)
    texts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type") or ""
            if btype == "text":
                texts.append(str(block.get("text") or ""))
            elif btype == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id") or f"toolu_{uuid.uuid4().hex[:24]}",
                        "type": "function",
                        "function": {
                            "name": block.get("name") or "",
                            "arguments": _tool_arguments(block.get("input")),
                        },
                    }
                )
    message = ChatMessage(role="assistant", content="".join(texts) or None)
    if tool_calls:
        message.tool_calls = tool_calls
    return message


def anthropic_to_openai_messages(system: Any, messages: Any) -> List[ChatMessage]:
    out: List[ChatMessage] = []
    sys_text = _system_text(system)
    if sys_text:
        out.append(ChatMessage(role="system", content=sys_text))
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")
        if role == "assistant":
            out.append(_assistant_to_message(content))
        elif role == "system":
            text = _system_text(content)
            if text:
                out.append(ChatMessage(role="system", content=text))
        else:
            out.extend(_user_to_messages(content))
    return out


def anthropic_tools_to_openai(tools: Any) -> Optional[List[Dict[str, Any]]]:
    if not tools:
        return None
    result: List[Dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = tool.get("name")
        if not name:
            continue
        schema = tool.get("input_schema") or tool.get("parameters") or {
            "type": "object",
            "properties": {},
        }
        result.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.get("description") or "",
                    "parameters": schema,
                },
            }
        )
    return result or None


def anthropic_tool_choice(choice: Any) -> Any:
    if choice is None or not isinstance(choice, (str, dict)):
        return None
    if isinstance(choice, str):
        return choice
    ctype = choice.get("type")
    if ctype in ("auto", "none"):
        return ctype
    if ctype == "any":
        return "required"
    if ctype == "tool":
        name = choice.get("name") or ""
        if name:
            return {"type": "function", "function": {"name": name}}
    return None


def to_chat_request(body: Any, model: str) -> ChatCompletionRequest:
    thinking = getattr(body, "thinking", None)
    think = bool(isinstance(thinking, dict) and thinking.get("type") == "enabled")
    return ChatCompletionRequest(
        model=model,
        messages=anthropic_to_openai_messages(body.system, body.messages),
        temperature=body.temperature,
        top_p=body.top_p,
        max_tokens=body.max_tokens,
        stream=bool(body.stream),
        tools=anthropic_tools_to_openai(body.tools),
        tool_choice=anthropic_tool_choice(body.tool_choice) if body.tools else None,
        think=think,
    )


def _parse_tool_input(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip() or "{}"
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"raw": raw}
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
    if raw is None:
        return {}
    return {"value": raw}


def openai_completion_to_anthropic(result: Dict[str, Any]) -> Dict[str, Any]:
    choice = (result.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    blocks: List[Dict[str, Any]] = []
    reasoning = message.get("reasoning_content")
    text = message.get("content") or ""
    if reasoning:
        blocks.append(
            {
                "type": "thinking",
                "thinking": reasoning,
                "signature": "ollama_gateway",
            }
        )
    tool_calls = message.get("tool_calls") or []
    if text or not tool_calls:
        if text or not blocks:
            blocks.append({"type": "text", "text": text})
    for tc in tool_calls:
        fn = tc.get("function") or {}
        blocks.append(
            {
                "type": "tool_use",
                "id": tc.get("id") or f"toolu_{uuid.uuid4().hex[:24]}",
                "name": fn.get("name") or "",
                "input": _parse_tool_input(fn.get("arguments")),
            }
        )
    if tool_calls:
        stop_reason = "tool_use"
    elif choice.get("finish_reason") == "length":
        stop_reason = "max_tokens"
    else:
        stop_reason = "end_turn"
    usage = result.get("usage") or {}
    return {
        "id": f"msg_{uuid.uuid4().hex}",
        "type": "message",
        "role": "assistant",
        "model": result.get("model") or "",
        "content": blocks,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": int(usage.get("prompt_tokens") or 0),
            "output_tokens": int(usage.get("completion_tokens") or 0),
        },
    }


def _sse(event: str, data: Dict[str, Any]) -> Dict[str, str]:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


def _chunk_text(chunk: Any) -> str:
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: List[str] = []
        for part in content:
            if isinstance(part, str):
                texts.append(part)
            elif isinstance(part, dict) and part.get("type") in (None, "text"):
                texts.append(str(part.get("text") or ""))
        return "".join(texts)
    return "" if content is None else str(content)


def _chunk_reasoning(chunk: Any) -> str:
    extra = _reasoning_content(chunk) or ""
    content = getattr(chunk, "content", None)
    from_content = ""
    if isinstance(content, list):
        bits: List[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") in ("thinking", "reasoning"):
                bits.append(
                    str(part.get("thinking") or part.get("reasoning") or part.get("text") or "")
                )
        from_content = "".join(bits)
    if extra and from_content:
        if from_content.startswith(extra) or extra.startswith(from_content):
            return extra if len(extra) >= len(from_content) else from_content
        return extra + from_content
    return extra or from_content


class AnthropicStreamBuilder:
    """把模型增量块转成 Anthropic SSE 事件。工具参数先攒齐，再在结束时一次性输出。"""

    def __init__(self, model: str, estimate_input: int = 0):
        self.model = model
        self.msg_id = f"msg_{uuid.uuid4().hex}"
        self.estimate_input = estimate_input
        self.reported_input = 0
        self.reported_output = 0
        self.stop_reason = "end_turn"
        self.block_index = 0
        self.thinking_open = False
        self.text_open = False
        self._thinking_index = 0
        self._text_index = 0
        self._reasoning_sent = ""
        self._text_sent = False
        self.tools: Dict[int, Dict[str, str]] = {}

    def usage_for_billing(self) -> Dict[str, int]:
        prompt = self.reported_input
        completion = self.reported_output
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        }

    def _display_usage(self) -> Dict[str, int]:
        return {
            "input_tokens": self.reported_input or self.estimate_input,
            "output_tokens": self.reported_output,
        }

    def start_events(self) -> List[Dict[str, str]]:
        usage = self._display_usage()
        return [
            _sse(
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": self.msg_id,
                        "type": "message",
                        "role": "assistant",
                        "content": [],
                        "model": self.model,
                        "stop_reason": None,
                        "stop_sequence": None,
                        "usage": {
                            "input_tokens": usage["input_tokens"],
                            "output_tokens": 0,
                        },
                    },
                },
            )
        ]

    def _close_thinking(self, events: List[Dict[str, str]]) -> None:
        if not self.thinking_open:
            return
        events.append(_sse("content_block_delta", {
            "type": "content_block_delta",
            "index": self._thinking_index,
            "delta": {"type": "signature_delta", "signature": "ollama_gateway"},
        }))
        events.append(_sse("content_block_stop", {
            "type": "content_block_stop",
            "index": self._thinking_index,
        }))
        self.thinking_open = False

    def _close_text(self, events: List[Dict[str, str]]) -> None:
        if not self.text_open:
            return
        events.append(_sse("content_block_stop", {
            "type": "content_block_stop",
            "index": self._text_index,
        }))
        self.text_open = False

    def _open_thinking(self, events: List[Dict[str, str]]) -> None:
        if self.thinking_open or self.text_open or self.tools:
            return
        self._thinking_index = self.block_index
        self.block_index += 1
        self.thinking_open = True
        events.append(_sse("content_block_start", {
            "type": "content_block_start",
            "index": self._thinking_index,
            "content_block": {"type": "thinking", "thinking": "", "signature": ""},
        }))

    def _open_text(self, events: List[Dict[str, str]]) -> None:
        if self.text_open:
            return
        self._close_thinking(events)
        self._text_index = self.block_index
        self.block_index += 1
        self.text_open = True
        events.append(_sse("content_block_start", {
            "type": "content_block_start",
            "index": self._text_index,
            "content_block": {"type": "text", "text": ""},
        }))

    def _push_reasoning(self, events: List[Dict[str, str]], text: str) -> None:
        if not text:
            return
        prev = self._reasoning_sent
        if prev and text.startswith(prev):
            delta = text[len(prev):]
            self._reasoning_sent = text
        elif prev and prev.startswith(text):
            return
        else:
            delta = text
            self._reasoning_sent += text
        if not delta or self.text_open or self.tools:
            return
        self._open_thinking(events)
        if not self.thinking_open:
            return
        events.append(_sse("content_block_delta", {
            "type": "content_block_delta",
            "index": self._thinking_index,
            "delta": {"type": "thinking_delta", "thinking": delta},
        }))

    def _push_text(self, events: List[Dict[str, str]], text: str) -> None:
        if not text:
            return
        self._text_sent = True
        self._open_text(events)
        events.append(_sse("content_block_delta", {
            "type": "content_block_delta",
            "index": self._text_index,
            "delta": {"type": "text_delta", "text": text},
        }))

    def _tool_key(self, index: Any, tid: str) -> int:
        if tid:
            for existing, tool in self.tools.items():
                if tool["id"] == tid:
                    return existing
        if index is not None:
            key = int(index)
            existing = self.tools.get(key)
            if existing is None or not tid or not existing["id"] or existing["id"] == tid:
                return key
            return (max(self.tools) + 1) if self.tools else 0
        if self.tools:
            return max(self.tools)
        return 0

    def _add_tool_piece(self, piece: Any, *, cumulative: bool) -> None:
        if isinstance(piece, dict):
            name = piece.get("name") or ""
            args = piece.get("args") or ""
            tid = str(piece.get("id") or "")
            index = piece.get("index")
        else:
            name = getattr(piece, "name", None) or ""
            args = getattr(piece, "args", None) or ""
            tid = str(getattr(piece, "id", None) or "")
            index = getattr(piece, "index", None)
        if not isinstance(args, str):
            args = json.dumps(args, ensure_ascii=False)
        key = self._tool_key(index, tid)
        tool = self.tools.get(key)
        if tool is None:
            tool = {"id": tid, "name": "", "args": ""}
            self.tools[key] = tool
        if tid and not tool["id"]:
            tool["id"] = tid
        if name and not tool["name"]:
            tool["name"] = str(name)
        if not args:
            return
        if cumulative:
            if (not tool["args"]) or args.startswith(tool["args"]):
                tool["args"] = args
        else:
            tool["args"] += args

    def _accumulate_tools(self, chunk: Any) -> None:
        raw = getattr(chunk, "tool_call_chunks", None) or []
        if raw:
            for piece in raw:
                self._add_tool_piece(piece, cumulative=False)
            return
        calls = _tool_calls_openai(chunk) or []
        for index, tc in enumerate(calls):
            fn = tc.get("function") or {}
            self._add_tool_piece(
                {
                    "name": fn.get("name") or "",
                    "args": fn.get("arguments") or "",
                    "id": tc.get("id") or "",
                    "index": index,
                },
                cumulative=True,
            )

    def _note_stop(self, chunk: Any) -> None:
        meta = getattr(chunk, "response_metadata", None) or {}
        done = meta.get("done_reason") or meta.get("finish_reason")
        if done in ("length", "max_tokens"):
            self.stop_reason = "max_tokens"

    def feed(self, chunk: Any) -> List[Dict[str, str]]:
        events: List[Dict[str, str]] = []
        usage = _extract_usage(chunk)
        if usage.get("prompt_tokens"):
            self.reported_input = int(usage["prompt_tokens"])
        if usage.get("completion_tokens"):
            self.reported_output = int(usage["completion_tokens"])
        self._note_stop(chunk)
        self._push_reasoning(events, _chunk_reasoning(chunk))
        self._push_text(events, _chunk_text(chunk))
        self._accumulate_tools(chunk)
        return events

    def _emit_tools(self, events: List[Dict[str, str]]) -> None:
        for key in sorted(self.tools):
            tool = self.tools[key]
            if not tool["name"] and not tool["args"]:
                continue
            index = self.block_index
            self.block_index += 1
            events.append(_sse("content_block_start", {
                "type": "content_block_start",
                "index": index,
                "content_block": {
                    "type": "tool_use",
                    "id": tool["id"] or f"toolu_{uuid.uuid4().hex[:24]}",
                    "name": tool["name"] or "tool",
                    "input": {},
                },
            }))
            events.append(_sse("content_block_delta", {
                "type": "content_block_delta",
                "index": index,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": json.dumps(
                        _parse_tool_input(tool["args"]), ensure_ascii=False
                    ),
                },
            }))
            events.append(_sse("content_block_stop", {
                "type": "content_block_stop",
                "index": index,
            }))

    def finish_events(self) -> List[Dict[str, str]]:
        events: List[Dict[str, str]] = []
        if self._reasoning_sent and not self._text_sent and not self.tools:
            self._close_thinking(events)
            self._push_text(events, self._reasoning_sent)
        self._close_thinking(events)
        self._close_text(events)
        if self.tools:
            self.stop_reason = "tool_use"
            self._emit_tools(events)
        elif not self._text_sent and not self._reasoning_sent:
            self._open_text(events)
            self._close_text(events)
        events.append(_sse("message_delta", {
            "type": "message_delta",
            "delta": {"stop_reason": self.stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": self._display_usage()["output_tokens"]},
        }))
        events.append(_sse("message_stop", {"type": "message_stop"}))
        return events

    async def stream(self, req: ChatCompletionRequest) -> Any:
        for event in self.start_events():
            yield event
        llm = build_llm(req)
        messages = openai_messages_to_lc(req.messages)
        async for chunk in llm.astream(messages):
            if not isinstance(chunk, AIMessageChunk):
                chunk = AIMessageChunk(content=getattr(chunk, "content", "") or "")
            for event in self.feed(chunk):
                yield event
        for event in self.finish_events():
            yield event
