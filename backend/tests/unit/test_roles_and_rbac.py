"""KAP 角色枚举 + RBAC Dependency 单测（坑 7 + 坑 8 验收）。

覆盖：

- 角色枚举值与 V15 别名兼容（admin / editor）
- 密级字符串 ↔ int 双向映射
- UserContext 自动同步 access_level → max_access_level
- RequireRole / RequireAccessLevel Dependency 拦截
- normalize_roles 规范化
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient

from packages.common.auth import UserContext
from packages.common.roles import (
    ACCESS_CONFIDENTIAL,
    ACCESS_INTERNAL,
    ACCESS_PUBLIC,
    ACCESS_TOP_SECRET,
    ALL_ROLES,
    LEGACY_ROLE_ADMIN,
    LEGACY_ROLE_EDITOR,
    ROLE_AIOPS,
    ROLE_DG,
    ROLE_READER,
    ROLE_SEC,
    ROLE_SME,
    RequireAccessLevel,
    RequireRole,
    access_level_label,
    access_level_to_int,
    normalize_roles,
)


# ────────── 密级映射 ──────────


class TestAccessLevel:
    def test_string_to_int(self) -> None:
        assert access_level_to_int("PUBLIC") == 0
        assert access_level_to_int("INTERNAL") == 1
        assert access_level_to_int("CONFIDENTIAL") == 2
        assert access_level_to_int("SECRET") == 2  # V15 兼容
        assert access_level_to_int("TOP_SECRET") == 3

    def test_chinese_to_int(self) -> None:
        assert access_level_to_int("公开") == 0
        assert access_level_to_int("内部") == 1
        assert access_level_to_int("秘密") == 2
        assert access_level_to_int("机密") == 3

    def test_int_passthrough(self) -> None:
        assert access_level_to_int(0) == 0
        assert access_level_to_int(3) == 3

    def test_int_out_of_range_uses_default(self) -> None:
        assert access_level_to_int(99) == ACCESS_INTERNAL  # default
        assert access_level_to_int(-1) == ACCESS_INTERNAL

    def test_none_uses_default(self) -> None:
        assert access_level_to_int(None) == ACCESS_INTERNAL
        assert access_level_to_int(None, default=ACCESS_PUBLIC) == ACCESS_PUBLIC

    def test_unknown_string_uses_default(self) -> None:
        assert access_level_to_int("UNKNOWN_STR") == ACCESS_INTERNAL

    def test_label(self) -> None:
        assert access_level_label(0) == "公开"
        assert access_level_label(1) == "内部"
        assert access_level_label(2) == "秘密"
        assert access_level_label(3) == "机密"


# ────────── 角色规范化 ──────────


class TestNormalizeRoles:
    def test_kap_roles_passthrough(self) -> None:
        result = normalize_roles([ROLE_DG, ROLE_SME])
        assert ROLE_DG in result
        assert ROLE_SME in result

    def test_admin_expands(self) -> None:
        """V15 admin → DG + SME + AIOps + READER。"""
        result = normalize_roles([LEGACY_ROLE_ADMIN])
        assert ROLE_DG in result
        assert ROLE_SME in result
        assert ROLE_AIOPS in result
        assert ROLE_READER in result

    def test_editor_expands(self) -> None:
        """V15 editor → SME + READER。"""
        result = normalize_roles([LEGACY_ROLE_EDITOR])
        assert ROLE_SME in result
        assert ROLE_READER in result

    def test_lowercase_reader(self) -> None:
        result = normalize_roles(["reader"])
        assert ROLE_READER in result

    def test_empty(self) -> None:
        assert normalize_roles([]) == []

    def test_dedup(self) -> None:
        result = normalize_roles([ROLE_DG, ROLE_DG, LEGACY_ROLE_ADMIN])
        # admin 包含 DG，不应重复
        assert result.count(ROLE_DG) == 1


# ────────── UserContext 同步 ──────────


class TestUserContextSync:
    def test_default_internal(self) -> None:
        u = UserContext()
        assert u.access_level == "INTERNAL"
        assert u.max_access_level == 1

    def test_secret_syncs_to_int(self) -> None:
        u = UserContext(access_level="SECRET")
        assert u.max_access_level == 2

    def test_explicit_max_access_level_wins(self) -> None:
        """显式传 max_access_level 时优先（用于 ISS 直接传 int 的场景）。"""
        u = UserContext(access_level="INTERNAL", max_access_level=3)
        assert u.max_access_level == 3

    def test_chinese_string(self) -> None:
        u = UserContext(access_level="机密")
        assert u.max_access_level == 3


# ────────── RequireRole Dependency ──────────


def _make_app_with_role_check(*roles: str) -> FastAPI:
    """构造测试 app：一个端点要求指定角色。"""
    app = FastAPI()

    @app.get("/protected")
    async def protected(user=Depends(RequireRole(*roles))):
        return {"user_id": user.user_id, "roles": user.roles}

    @app.middleware("http")
    async def inject_user(request, call_next):
        # 测试用：从 X-Test-Roles header 注入
        roles_str = request.headers.get("X-Test-Roles", "")
        roles_list = [r.strip() for r in roles_str.split(",") if r.strip()]
        request.state.user = UserContext(
            user_id="test-user",
            roles=roles_list,
        )
        return await call_next(request)

    return app


class TestRequireRole:
    def test_allowed_role_passes(self) -> None:
        app = _make_app_with_role_check(ROLE_SME)
        client = TestClient(app)
        r = client.get("/protected", headers={"X-Test-Roles": "SME"})
        assert r.status_code == 200

    def test_disallowed_role_403(self) -> None:
        app = _make_app_with_role_check(ROLE_SME)
        client = TestClient(app)
        r = client.get("/protected", headers={"X-Test-Roles": "READER"})
        assert r.status_code == 403
        assert "需要角色" in r.json()["detail"]

    def test_anonymous_403(self) -> None:
        app = _make_app_with_role_check(ROLE_DG)
        client = TestClient(app)
        r = client.get("/protected")  # 无 X-Test-Roles
        assert r.status_code == 403

    def test_legacy_admin_expands(self) -> None:
        """V15 admin 通过别名扩展应能访问 RequireRole(ROLE_DG)。"""
        app = _make_app_with_role_check(ROLE_DG)
        client = TestClient(app)
        r = client.get("/protected", headers={"X-Test-Roles": "admin"})
        assert r.status_code == 200

    def test_multiple_allowed_roles(self) -> None:
        """RequireRole(SME, DG) 任一即可。"""
        app = _make_app_with_role_check(ROLE_SME, ROLE_DG)
        client = TestClient(app)
        r = client.get("/protected", headers={"X-Test-Roles": "DG"})
        assert r.status_code == 200


# ────────── RequireAccessLevel Dependency ──────────


def _make_app_with_access_check(min_level: int) -> FastAPI:
    app = FastAPI()

    @app.get("/secure")
    async def secure(user=Depends(RequireAccessLevel(min_level))):
        return {"user_id": user.user_id, "level": user.max_access_level}

    @app.middleware("http")
    async def inject_user(request, call_next):
        level = int(request.headers.get("X-Test-Level", "1"))
        request.state.user = UserContext(
            user_id="test-user",
            max_access_level=level,
        )
        return await call_next(request)

    return app


class TestRequireAccessLevel:
    def test_higher_level_passes(self) -> None:
        app = _make_app_with_access_check(ACCESS_INTERNAL)
        client = TestClient(app)
        r = client.get("/secure", headers={"X-Test-Level": "2"})
        assert r.status_code == 200

    def test_equal_level_passes(self) -> None:
        app = _make_app_with_access_check(ACCESS_CONFIDENTIAL)
        client = TestClient(app)
        r = client.get("/secure", headers={"X-Test-Level": "2"})
        assert r.status_code == 200

    def test_lower_level_403(self) -> None:
        app = _make_app_with_access_check(ACCESS_TOP_SECRET)
        client = TestClient(app)
        r = client.get("/secure", headers={"X-Test-Level": "1"})
        assert r.status_code == 403
        assert "需要密级" in r.json()["detail"]
