"""请求 schema 测试：思考模式解析与 input 归一化。"""
import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatCompletionRequest, ChatMessage, EmbeddingRequest


def make_request(**kwargs) -> ChatCompletionRequest:
    return ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="你好")], **kwargs
    )


def test_resolve_think_prefers_explicit_flag():
    assert make_request(think=False, reasoning=True).resolve_think() is False
    assert make_request(think=True).resolve_think() is True


def test_resolve_think_falls_back_to_reasoning():
    assert make_request(reasoning=True).resolve_think() is True


def test_resolve_think_reads_extra_body():
    assert make_request(extra_body={"reasoning": True}).resolve_think() is True
    assert make_request(extra_body={"think": True}).resolve_think() is True


def test_resolve_think_defaults_to_false():
    assert make_request().resolve_think() is False


def test_embedding_request_normalizes_single_input():
    assert EmbeddingRequest(input="一段文本").texts() == ["一段文本"]


def test_embedding_request_keeps_list_order():
    req = EmbeddingRequest(input=["a", "b", "c"])
    assert req.texts() == ["a", "b", "c"]
    assert req.encoding_format == "float"


def test_chat_message_rejects_unknown_role():
    with pytest.raises(ValidationError):
        ChatMessage(role="developer", content="hi")
