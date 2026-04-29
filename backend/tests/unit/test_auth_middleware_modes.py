"""M1 ISS 集成 · 批 1 · AuthMiddleware 三模式 dispatch 单测。"""

from __future__ import annotations

import json
import time

import jwt
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from api.middleware.auth import AuthMiddleware, reset_api_key_map_for_test
from packages.auth import iss_session
from packages.common import settings


_TEST_SECRET = "kap-iss-shared-secret-for-unit-test-only"


@pytest.fixture(autouse=True)
def _reset_caches() -> None:
    reset_api_key_map_for_test()
    yield
    reset_api_key_map_for_test()


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/whoami")
    async def whoami(request: Request) -> dict:
        u = request.state.user
        return {
            "user_id": u.user_id,
            "source": u.source,
            "roles": u.roles,
            "dept_id": u.dept_id,
            "data_scope_level": u.data_scope_level,
        }

    return app


# ════════════════════════════════════════════════════════════════════════
#  api_key 模式（M0 行为不破坏）
# ════════════════════════════════════════════════════════════════════════


class TestApiKeyMode:
    def test_default_admin_key_passes(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "kap_auth_mode", "api_key")
        monkeypatch.setattr(settings, "auth_required", False)
        client = TestClient(_build_app())
        r = client.get("/whoami", headers={"X-API-Key": "bw-admin-key"})
        assert r.status_code == 200
        assert r.json()["user_id"] == "admin"
        assert r.json()["source"] == "api_key"

    def test_anonymous_passes_when_auth_not_required(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "kap_auth_mode", "api_key")
        monkeypatch.setattr(settings, "auth_required", False)
        client = TestClient(_build_app())
        r = client.get("/whoami")
        assert r.status_code == 200
        assert r.json()["user_id"] == "anonymous"
        assert r.json()["source"] == "anonymous"

    def test_anonymous_blocked_when_auth_required(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "kap_auth_mode", "api_key")
        monkeypatch.setattr(settings, "auth_required", True)
        monkeypatch.setattr(settings, "api_keys", "valid-key:user1:reader")
        client = TestClient(_build_app())
        r = client.get("/whoami")
        assert r.status_code == 401


# ════════════════════════════════════════════════════════════════════════
#  jwt 模式（M1 批 1 新增）
# ════════════════════════════════════════════════════════════════════════


def _make_jwt(payload: dict) -> str:
    return jwt.encode(payload, _TEST_SECRET, algorithm="HS512")


class _FakeRedis:
    """最小 fakeredis 替代品，仅实现 get / close。"""

    def __init__(self, store: dict[str, str] | None = None) -> None:
        self._store = store or {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def close(self) -> None:
        pass


@pytest.fixture
def _jwt_mode(monkeypatch):
    """配置 JWT 模式 + 注入 fakeredis。"""
    monkeypatch.setattr(settings, "kap_auth_mode", "jwt")
    monkeypatch.setattr(settings, "iss_jwt_secret", _TEST_SECRET)
    monkeypatch.setattr(settings, "iss_jwt_algorithm", "HS512")
    monkeypatch.setattr(settings, "iss_jwt_user_key_claim", "user_key")
    monkeypatch.setattr(settings, "iss_redis_url", "redis://fake")
    monkeypatch.setattr(settings, "iss_token_key_prefix", "login_tokens:")

    def _inject_redis(store: dict[str, str]):
        iss_session._async_redis = _FakeRedis(store)

    yield _inject_redis
    iss_session._async_redis = None


class TestJwtMode:
    def test_valid_jwt_with_iss_user_passes(self, _jwt_mode) -> None:
        login_user_payload = {
            "userid": 100,
            "username": "alice",
            "roles": ["DG", "READER"],
            "permissions": ["system:user:list"],
            "sysUser": {"deptId": 200},
        }
        _jwt_mode({
            "login_tokens:abc-uuid": json.dumps(login_user_payload),
        })
        token = _make_jwt({"user_key": "abc-uuid", "exp": int(time.time()) + 60})

        client = TestClient(_build_app())
        r = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["user_id"] == "100"
        assert body["source"] == "jwt"
        assert body["dept_id"] == 200
        assert "DG" in body["roles"] and "READER" in body["roles"]

    def test_missing_token_returns_401(self, _jwt_mode) -> None:
        _jwt_mode({})
        client = TestClient(_build_app())
        r = client.get("/whoami")
        assert r.status_code == 401
        assert "缺少" in r.json()["detail"]

    def test_invalid_signature_returns_401(self, _jwt_mode) -> None:
        _jwt_mode({})
        bad_token = jwt.encode({"user_key": "x"}, "wrong-secret", algorithm="HS512")
        client = TestClient(_build_app())
        r = client.get("/whoami", headers={"Authorization": f"Bearer {bad_token}"})
        assert r.status_code == 401
        assert "验签失败" in r.json()["detail"]

    def test_redis_miss_returns_401(self, _jwt_mode) -> None:
        _jwt_mode({})  # 空 redis，token 在但 LoginUser 不在
        token = _make_jwt({"user_key": "missing-uuid", "exp": int(time.time()) + 60})
        client = TestClient(_build_app())
        r = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401
        assert "ISS 会话失效" in r.json()["detail"]


# ════════════════════════════════════════════════════════════════════════
#  gateway_header 模式（M1 批 1 新增）
# ════════════════════════════════════════════════════════════════════════


class TestGatewayHeaderMode:
    def test_full_headers_construct_user_context(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "kap_auth_mode", "gateway_header")
        client = TestClient(_build_app())
        r = client.get(
            "/whoami",
            headers={
                "X-User-Id": "42",
                "X-User-Name": "bob",
                "X-User-Roles": "SME,READER",
                "X-User-Perms": "kap:doc:read,kap:doc:write",
                "X-Dept-Id": "101",
                "X-Data-Scope": "3",
                "X-Access-Level": "CONFIDENTIAL",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["user_id"] == "42"
        assert body["source"] == "gateway"
        assert body["dept_id"] == 101
        assert body["data_scope_level"] == 3
        assert "SME" in body["roles"]

    def test_missing_user_id_header_returns_401(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "kap_auth_mode", "gateway_header")
        client = TestClient(_build_app())
        r = client.get("/whoami")
        assert r.status_code == 401
        assert "X-User-Id" in r.json()["detail"]

    def test_invalid_dept_id_falls_back_to_none(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "kap_auth_mode", "gateway_header")
        client = TestClient(_build_app())
        r = client.get(
            "/whoami",
            headers={"X-User-Id": "1", "X-Dept-Id": "not-a-number"},
        )
        assert r.status_code == 200
        assert r.json()["dept_id"] is None
