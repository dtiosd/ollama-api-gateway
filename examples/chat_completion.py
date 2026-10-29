"""聊天补全示例：python -m pip install openai 后运行

用法（PowerShell）：
    $env:GATEWAY_BASE_URL = "http://127.0.0.1:8001/v1"
    $env:GATEWAY_API_KEY  = "sk-你生成的密钥"
    $env:GATEWAY_MODEL    = "qwen2.5:7b"
    python examples/chat_completion.py
"""
import os

from openai import OpenAI

client = OpenAI(
    api_key=os.environ["GATEWAY_API_KEY"],
    base_url=os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8001/v1"),
)

resp = client.chat.completions.create(
    model=os.environ.get("GATEWAY_MODEL", "qwen2.5:7b"),
    messages=[{"role": "user", "content": "你好"}],
)
print(resp.choices[0].message.content)
