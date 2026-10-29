"""管理接口口令校验的单元测试。"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import auth
from app.config import Settings
from tests.helpers import build_settings


def make_request(token=None):
    headers = {} if token is None else {auth.ADMIN_TOKEN_HEADER: token}
    return SimpleNamespace(headers=headers)


@pytest.fixture
def with_admin_token(monkeypatch):
    monkeypatch.setattr(
        auth, "get_settings", lambda: build_settings(admin_token="s3cr3t-token")
    )


@pytest.fixture
def without_admin_token(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: build_settings(admin_token=""))


def test_require_admin_accepts_matching_token(with_admin_token):
    assert auth.require_admin(make_request("s3cr3t-token")) is None


def test_require_admin_rejects_wrong_token(with_admin_token):
    with pytest.raises(HTTPException) as exc:
        auth.require_admin(make_request("wrong"))
    assert exc.value.status_code == 403


def test_require_admin_rejects_missing_header(with_admin_token):
    with pytest.raises(HTTPException) as exc:
        auth.require_admin(make_request(None))
    assert exc.value.status_code == 403


def test_admin_api_disabled_when_token_not_configured(without_admin_token):
    with pytest.raises(HTTPException) as exc:
        auth.require_admin(make_request("anything"))
    assert exc.value.status_code == 503


def test_no_username_based_exemption_remains():
    """回归护栏：不允许重新引入按用户名豁免配额/模型绑定的逻辑。"""
    assert not hasattr(auth, "_staff")
    assert "quota_exempt_users" not in Settings.model_fields
