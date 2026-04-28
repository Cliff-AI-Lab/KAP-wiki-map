"""认证中间件单元测试。"""

import pytest
from packages.common.auth import UserContext
from api.middleware.auth import AuthMiddleware, _API_KEY_MAP, SKIP_PATHS


class TestUserContext:
    """UserContext 模型测试。"""

    def test_default_values(self):
        ctx = UserContext()
        assert ctx.user_id == "anonymous"
        assert ctx.org_id == "default"
        assert ctx.access_level == "INTERNAL"
        assert ctx.department_id == ""
        assert ctx.roles == []
        assert ctx.display_name == ""

    def test_custom_values(self):
        ctx = UserContext(
            user_id="user_001",
            org_id="org_enterprise_a",
            access_level="CONFIDENTIAL",
            department_id="tech",
            roles=["admin", "reader"],
            display_name="张三",
        )
        assert ctx.user_id == "user_001"
        assert ctx.org_id == "org_enterprise_a"
        assert ctx.access_level == "CONFIDENTIAL"
        assert ctx.department_id == "tech"
        assert ctx.roles == ["admin", "reader"]
        assert ctx.display_name == "张三"


class TestAPIKeyMap:
    """内置 API Key 映射测试。"""

    def test_default_key_exists(self):
        assert "bw-default-key" in _API_KEY_MAP
        ctx = _API_KEY_MAP["bw-default-key"]
        assert ctx.user_id == "default_user"
        assert ctx.org_id == "default"

    def test_admin_key_exists(self):
        assert "bw-admin-key" in _API_KEY_MAP
        ctx = _API_KEY_MAP["bw-admin-key"]
        assert ctx.access_level == "SECRET"
        assert "admin" in ctx.roles

    def test_unknown_key_not_in_map(self):
        assert "nonexistent-key" not in _API_KEY_MAP


class TestSkipPaths:
    """跳过认证的路径测试。"""

    def test_health_in_skip_paths(self):
        assert "/health" in SKIP_PATHS

    def test_docs_in_skip_paths(self):
        assert "/docs" in SKIP_PATHS

    def test_api_path_not_skipped(self):
        assert "/api/v1/qa/ask" not in SKIP_PATHS


class TestTokenExtraction:
    """Token 提取逻辑测试。"""

    def test_extract_api_key_header(self):
        """模拟 X-API-Key 头解析。"""

        class MockRequest:
            def __init__(self, headers):
                self.headers = headers

        req = MockRequest({"X-API-Key": "bw-default-key"})
        token = AuthMiddleware._extract_token(req)
        assert token == "bw-default-key"

    def test_extract_bearer_token(self):
        """模拟 Bearer Token 解析。"""

        class MockRequest:
            def __init__(self, headers):
                self.headers = headers

        req = MockRequest({"Authorization": "Bearer my-secret-token"})
        token = AuthMiddleware._extract_token(req)
        assert token == "my-secret-token"

    def test_no_token_returns_none(self):
        """无认证头返回 None。"""

        class MockRequest:
            def __init__(self, headers):
                self.headers = headers

        req = MockRequest({})
        token = AuthMiddleware._extract_token(req)
        assert token is None

    def test_api_key_takes_priority(self):
        """X-API-Key 优先于 Bearer Token。"""

        class MockRequest:
            def __init__(self, headers):
                self.headers = headers

        req = MockRequest({
            "X-API-Key": "bw-admin-key",
            "Authorization": "Bearer other-token",
        })
        token = AuthMiddleware._extract_token(req)
        assert token == "bw-admin-key"
