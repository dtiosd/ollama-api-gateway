from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: Optional[Union[str, List[Dict[str, Any]]]] = None
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


class EmbeddingRequest(BaseModel):
    model: Optional[str] = None
    input: Union[str, List[str]]
    encoding_format: Literal["float", "base64"] = "float"
    user: Optional[str] = None

    def texts(self) -> List[str]:
        return [self.input] if isinstance(self.input, str) else list(self.input)


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    # 思考模式：think / reasoning 均可
    think: Optional[bool] = None
    reasoning: Optional[bool] = None
    # 兼容 OpenAI extra_body
    extra_body: Optional[Dict[str, Any]] = None

    def resolve_think(self) -> bool:
        if self.think is not None:
            return bool(self.think)
        if self.reasoning is not None:
            return bool(self.reasoning)
        if self.extra_body:
            if "think" in self.extra_body:
                return bool(self.extra_body["think"])
            if "reasoning" in self.extra_body:
                return bool(self.extra_body["reasoning"])
        return False
