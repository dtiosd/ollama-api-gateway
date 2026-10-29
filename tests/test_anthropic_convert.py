"""Anthropic <-> OpenAI 协议转换测试。"""
from app.llm.anthropic import (
    anthropic_to_openai_messages,
    anthropic_tool_choice,
    anthropic_tools_to_openai,
    estimate_input_tokens,
    model_missing,
    openai_completion_to_anthropic,
)


def test_system_string_becomes_first_message():
    msgs = anthropic_to_openai_messages("你是助手", [{"role": "user", "content": "你好"}])
    assert [(m.role, m.content) for m in msgs] == [
        ("system", "你是助手"),
        ("user", "你好"),
    ]


def test_system_block_list_is_joined():
    msgs = anthropic_to_openai_messages(
        [{"type": "text", "text": "A"}, {"type": "text", "text": "B"}], []
    )
    assert msgs[0].content == "A\nB"


def test_tool_result_becomes_tool_message():
    msgs = anthropic_to_openai_messages(
        None,
        [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"}
                ],
            }
        ],
    )
    assert msgs[0].role == "tool"
    assert msgs[0].tool_call_id == "toolu_1"
    assert msgs[0].content == "ok"


def test_image_block_becomes_image_url_part():
    msgs = anthropic_to_openai_messages(
        None,
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": "AAA"},
                    }
                ],
            }
        ],
    )
    part = msgs[0].content[0]
    assert part["type"] == "image_url"
    assert part["image_url"]["url"] == "data:image/png;base64,AAA"


def test_tools_are_wrapped_as_openai_functions():
    tools = anthropic_tools_to_openai(
        [{"name": "get_time", "description": "查询时间", "input_schema": {"type": "object"}}]
    )
    assert tools[0]["type"] == "function"
    assert tools[0]["function"]["name"] == "get_time"
    assert tools[0]["function"]["parameters"] == {"type": "object"}


def test_tools_empty_inputs_return_none():
    assert anthropic_tools_to_openai(None) is None
    assert anthropic_tools_to_openai([{"description": "缺少 name"}]) is None


def test_tool_choice_mapping():
    assert anthropic_tool_choice(None) is None
    assert anthropic_tool_choice("auto") == "auto"
    assert anthropic_tool_choice({"type": "none"}) == "none"
    assert anthropic_tool_choice({"type": "any"}) == "required"
    assert anthropic_tool_choice({"type": "tool", "name": "get_time"}) == {
        "type": "function",
        "function": {"name": "get_time"},
    }


def test_estimate_input_tokens_is_positive():
    assert estimate_input_tokens("sys", [{"role": "user", "content": "你好"}], None) >= 1
    assert estimate_input_tokens(None, None, None) >= 1


def test_model_missing_detects_common_errors():
    assert model_missing(RuntimeError("model 'qwen9' not found")) is True
    assert model_missing(RuntimeError("connection refused")) is False


def test_openai_text_completion_becomes_anthropic_message():
    payload = openai_completion_to_anthropic(
        {
            "model": "qwen2.5:7b",
            "choices": [{"message": {"content": "你好"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        }
    )
    assert payload["role"] == "assistant"
    assert payload["stop_reason"] == "end_turn"
    assert payload["content"] == [{"type": "text", "text": "你好"}]


def test_openai_tool_calls_switch_stop_reason():
    payload = openai_completion_to_anthropic(
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {"id": "call_1", "function": {"name": "get_time", "arguments": "{}"}}
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
    )
    assert payload["stop_reason"] == "tool_use"
    assert payload["content"][0]["type"] == "tool_use"
    assert payload["content"][0]["name"] == "get_time"
