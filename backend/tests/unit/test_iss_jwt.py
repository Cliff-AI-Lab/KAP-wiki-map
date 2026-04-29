"""M1 ISS 集成 · 批 1 · JWT 验签单测。"""

from __future__ import annotations

import time

import jwt
import pytest

from packages.auth.iss_jwt import ISSJWTError, decode_iss_jwt, extract_user_key
from packages.common import settings


_TEST_SECRET = "kap-iss-shared-secret-for-unit-test-only"


@pytest.fixture(autouse=True)
def _set_jwt_secret(monkeypatch):
    """每个测试都用固定 secret，避免依赖真实 ISS 密钥。"""
    monkeypatch.setattr(settings, "iss_jwt_secret", _TEST_SECRET)
    monkeypatch.setattr(settings, "iss_jwt_algorithm", "HS512")
    monkeypatch.setattr(settings, "iss_jwt_user_key_claim", "user_key")


def _make_token(payload: dict, secret: str = _TEST_SECRET, algorithm: str = "HS512") -> str:
    return jwt.encode(payload, secret, algorithm=algorithm)


class TestDecodeJWT:
    def test_valid_token(self) -> None:
        token = _make_token({"user_key": "abc-uuid", "exp": int(time.time()) + 60})
        claims = decode_iss_jwt(token)
        assert claims["user_key"] == "abc-uuid"

    def test_missing_secret_raises(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "iss_jwt_secret", "")
        token = _make_token({"user_key": "abc"})
        with pytest.raises(ISSJWTError, match="未配置"):
            decode_iss_jwt(token)

    def test_empty_token_raises(self) -> None:
        with pytest.raises(ISSJWTError, match="为空"):
            decode_iss_jwt("")

    def test_wrong_signature_raises(self) -> None:
        token = _make_token({"user_key": "x"}, secret="not-the-real-secret")
        with pytest.raises(ISSJWTError, match="验签失败"):
            decode_iss_jwt(token)

    def test_expired_token_raises(self) -> None:
        token = _make_token({"user_key": "x", "exp": int(time.time()) - 60})
        with pytest.raises(ISSJWTError, match="验签失败"):
            decode_iss_jwt(token)

    def test_expired_token_passes_when_verify_off(self) -> None:
        token = _make_token({"user_key": "x", "exp": int(time.time()) - 60})
        claims = decode_iss_jwt(token, verify_exp=False)
        assert claims["user_key"] == "x"

    def test_malformed_token_raises(self) -> None:
        with pytest.raises(ISSJWTError):
            decode_iss_jwt("not-a-jwt-at-all")


class TestExtractUserKey:
    def test_extracts_user_key(self) -> None:
        token = _make_token({"user_key": "abc-uuid-123"})
        assert extract_user_key(token) == "abc-uuid-123"

    def test_missing_user_key_claim_raises(self) -> None:
        token = _make_token({"sub": "user1"})  # 没有 user_key
        with pytest.raises(ISSJWTError, match="缺少"):
            extract_user_key(token)

    def test_custom_claim_name_via_settings(self, monkeypatch) -> None:
        """ISS 升级换 claim 名时只改配置不改代码。"""
        monkeypatch.setattr(settings, "iss_jwt_user_key_claim", "uk")
        token = _make_token({"uk": "custom-claim-value"})
        assert extract_user_key(token) == "custom-claim-value"

    def test_user_key_is_int_returns_str(self) -> None:
        """ISS user_key 是 UUID 字符串，但万一是 int，确保转 str。"""
        token = _make_token({"user_key": 12345})
        assert extract_user_key(token) == "12345"
