"""HTTP 层测试：管理接口在未携带 / 携带错误口令时被拒绝。"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.config as app_config
from app.api.keys import keys_router


@pytest.fixture
def client(monkeypatch, request):
    monkeypatch.setenv("ADMIN_TOKEN", request.param)
    app_config.get_settings.cache_clear()
    api = FastAPI()
    api.include_router(keys_router)
    yield TestClient(api)
    app_config.get_settings.cache_clear()


@pytest.mark.parametrize("client", [""], indirect=True)
def test_management_api_disabled_without_admin_token(client):
    resp = client.get("/backend/api-keys")
    assert resp.status_code == 503
    assert "ADMIN_TOKEN" in resp.json()["detail"]


@pytest.mark.parametrize("client", ["configured-token"], indirect=True)
def test_management_api_rejects_missing_header(client):
    assert client.get("/backend/api-keys").status_code == 403


@pytest.mark.parametrize("client", ["configured-token"], indirect=True)
def test_management_api_rejects_wrong_header(client):
    resp = client.get("/backend/api-keys", headers={"X-Admin-Token": "wrong"})
    assert resp.status_code == 403
