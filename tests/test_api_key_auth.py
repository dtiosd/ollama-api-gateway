"""API 密钥鉴权与模型绑定的行为测试。

这些分支正是历史上"按用户名豁免配额/模型绑定"所在的位置，因此这里断言的是
「对所有密钥一律生效」这一条规则本身，而不只是豁免代码不存在。
"""
import asyncio
import inspect
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api import auth, chat
from app.db.repository import ApiUsageRepository


class _FakeSession:
    """鉴权只用到 session 的生命周期，不需要真实数据库。"""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeRepo:
    rows: dict[str, SimpleNamespace] = {}

    def __init__(self, session):
        pass

    async def get_by_api_key(self, api_key):
        return self.rows.get(api_key)


def make_key_row(**overrides) -> SimpleNamespace:
    row = dict(
        id=1,
        username="alice",
        api_key="sk-alice",
        token_quota=1000,
        is_active=True,
        bound_model="",
    )
    return SimpleNamespace(**{**row, **overrides})


def http_request(headers: dict[str, str]) -> Request:
    raw = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()]
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "path": "/v1/chat/completions",
            "raw_path": b"/v1/chat/completions",
            "scheme": "http",
            "query_string": b"",
            "root_path": "",
            "headers": raw,
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
        }
    )


@pytest.fixture
def key_store(monkeypatch):
    """替换掉数据库访问，返回可写入的假密钥表。"""
    _FakeRepo.rows = {}
    monkeypatch.setattr(auth, "AsyncSessionLocal", _FakeSession)
    monkeypatch.setattr(auth, "ApiKeyRepository", _FakeRepo)
    return _FakeRepo.rows


def run_verify(headers: dict[str, str]):
    return asyncio.run(auth.verify_api_key(http_request(headers)))


def status_of(call):
    with pytest.raises(HTTPException) as exc:
        call()
    return exc.value.status_code


# ---------------------------------------------------------------- 401 分支


def test_missing_credentials_is_401(key_store):
    key_store["sk-alice"] = make_key_row()
    assert status_of(lambda: run_verify({})) == 401


def test_non_sk_prefixed_token_is_ignored(key_store):
    key_store["sk-alice"] = make_key_row()
    assert status_of(lambda: run_verify({"Authorization": "Bearer not-an-sk"})) == 401


def test_unknown_key_is_401(key_store):
    key_store["sk-alice"] = make_key_row()
    assert status_of(
        lambda: run_verify({"Authorization": "Bearer sk-does-not-exist"})
    ) == 401


def test_disabled_key_is_401(key_store):
    key_store["sk-alice"] = make_key_row(is_active=False)
    assert status_of(lambda: run_verify({"X-API-Key": "sk-alice"})) == 401


# ---------------------------------------------------------------- 402 分支


def test_zero_quota_is_402(key_store):
    """配额耗尽必须拒绝——历史上这里是按用户名豁免的口子。"""
    key_store["sk-alice"] = make_key_row(token_quota=0)
    assert status_of(lambda: run_verify({"X-API-Key": "sk-alice"})) == 402


def test_negative_quota_is_402(key_store):
    key_store["sk-alice"] = make_key_row(token_quota=-1)
    assert status_of(lambda: run_verify({"X-API-Key": "sk-alice"})) == 402


def test_quota_applies_regardless_of_username(key_store):
    """同名的两个密钥都受配额约束，不存在某个用户名被跳过。"""
    key_store["sk-admin"] = make_key_row(username="admin", token_quota=0)
    key_store["sk-alice"] = make_key_row(username="alice", token_quota=0)
    assert status_of(lambda: run_verify({"X-API-Key": "sk-admin"})) == 402
    assert status_of(lambda: run_verify({"X-API-Key": "sk-alice"})) == 402


# ---------------------------------------------------------------- 放行分支


def test_positive_quota_passes_via_bearer(key_store):
    key_store["sk-alice"] = make_key_row(token_quota=1)
    assert run_verify({"Authorization": "Bearer sk-alice"}).token_quota == 1


def test_positive_quota_passes_via_x_api_key(key_store):
    key_store["sk-alice"] = make_key_row()
    assert run_verify({"X-API-Key": "sk-alice"}).api_key == "sk-alice"


def test_large_quota_is_the_unlimited_path(key_store):
    """要"无限额度"就建一个极大配额的密钥：仍走正常的、可审计的扣减路径。"""
    key_store["sk-alice"] = make_key_row(token_quota=2**62)
    assert run_verify({"X-API-Key": "sk-alice"}).token_quota == 2**62


# ---------------------------------------------------------------- 回归护栏


def test_usage_recording_always_deducts():
    """扣减不能再被一个开关参数跳过。"""
    params = inspect.signature(ApiUsageRepository.record_usage_and_deduct).parameters
    assert "deduct_quota" not in params
    assert "api_key_id" in params


# ------------------------------------------------------------ 模型绑定


def build_chat_client(key_row: SimpleNamespace) -> TestClient:
    api = FastAPI()
    api.include_router(chat.chat_router)
    api.dependency_overrides[auth.verify_api_key] = lambda: key_row
    return TestClient(api)


def test_embeddings_reject_model_outside_binding():
    client = build_chat_client(make_key_row(bound_model="qwen2.5:7b"))
    resp = client.post("/v1/embeddings", json={"model": "llama3.2:3b", "input": ["hi"]})
    assert resp.status_code == 403


def test_chat_completions_reject_model_outside_binding():
    client = build_chat_client(make_key_row(bound_model="qwen2.5:7b"))
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "llama3.2:3b", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 403


def test_bound_model_limits_the_model_listing(monkeypatch):
    async def fake_models():
        return [{"id": "qwen2.5:7b", "object": "model"}, {"id": "llama3.2:3b", "object": "model"}]

    monkeypatch.setattr(chat, "list_ollama_models", fake_models)

    bound = build_chat_client(make_key_row(bound_model="qwen2.5:7b"))
    body = bound.get("/v1/models", headers={"X-API-Key": "sk-alice"}).json()
    assert [m["id"] for m in body["data"]] == ["qwen2.5:7b"]

    unbound = build_chat_client(make_key_row(bound_model=""))
    body = unbound.get("/v1/models", headers={"X-API-Key": "sk-alice"}).json()
    assert len(body["data"]) == 2
