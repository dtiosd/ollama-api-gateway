"""配置层测试：驱动转换、CORS 与免配额名单解析。"""
from app.config import to_sync_database_url
from tests.helpers import build_settings


def test_to_sync_database_url_switches_driver():
    url = to_sync_database_url("postgresql+asyncpg://u:p@127.0.0.1:5432/db")
    assert url == "postgresql+psycopg2://u:p@127.0.0.1:5432/db"


def test_to_sync_database_url_fixes_typo_scheme():
    url = to_sync_database_url("postgres+asyncpg://u:p@127.0.0.1:5432/db")
    assert url.startswith("postgresql+psycopg2://")


def test_to_sync_database_url_keeps_other_drivers():
    url = to_sync_database_url("sqlite:///./local.db")
    assert url == "sqlite:///./local.db"


def test_cors_wildcard_disables_credentials():
    settings = build_settings(cors_allow_origins="*")
    assert settings.cors_origin_list == ["*"]
    assert settings.allow_anonymous_cors is False


def test_cors_explicit_origins_allow_credentials():
    settings = build_settings(cors_allow_origins="https://a.example, https://b.example")
    assert settings.cors_origin_list == ["https://a.example", "https://b.example"]
    assert settings.allow_anonymous_cors is True
