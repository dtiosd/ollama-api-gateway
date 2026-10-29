"""向量（embeddings）示例：需先安装 openai，并让 Ollama 拉取 embedding 模型

    ollama pull nomic-embed-text
    $env:GATEWAY_API_KEY = "sk-你生成的密钥"
    python examples/embeddings.py
"""
import os

from openai import OpenAI

client = OpenAI(
    api_key=os.environ["GATEWAY_API_KEY"],
    base_url=os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8001/v1"),
)

resp = client.embeddings.create(
    model=os.environ.get("GATEWAY_EMBEDDING_MODEL", "nomic-embed-text"),
    input=["Ollama 兼容网关", "API Key 用量统计"],
)

for item in resp.data:
    print(item.index, len(item.embedding))
