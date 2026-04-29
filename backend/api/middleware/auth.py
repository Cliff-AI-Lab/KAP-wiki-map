"""认证中间件 — 三模式 dispatch（M0 PoC + M1 ISS 集成）。

M1 改造（决策书 §9.1 / PRD §10.4）：

- ``api_key`` 模式（dev 默认）— 静态 API Key 字典，用于 PoC 和单机调试
- ``jwt`` 模式（sandbox 推荐）— 验签 ISS HS512 JWT + 共享 ISS Redis 拿 LoginUser
- ``gateway_header`` 模式（prod 推荐）— 信任 ISS-Gateway 注入的 ``X-User-*`` header，
  自己不验签（适合 KAP 部署在 ISS 网关后面的私有化场景）

模式由 ``settings.kap_auth_mode`` 决定；sandbox/prod 强制非 api_key（config.model_post_init）。
"""

from __future__ import annotations

import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from packages.common import settings
from packages.common.auth import UserContext

_auth_log = logging.getLogger("auth")


# ════════════════════════════════════════════════════════════════════════
#  api_key 模式（M0 PoC，原始实现保留）
# ════════════════════════════════════════════════════════════════════════


def _build_api_key_map() -> dict[str, UserContext]:
    """从环境变量构建 API Key 映射。

    格式: API_KEYS="key1:user_id1:role1,key2:user_id2:role2"
    未配置时: auth_required=True → 空映射(拒绝所有), False → PoC默认密钥。
    """
    api_keys_str = settings.api_keys
    if api_keys_str:
        result: dict[str, UserContext] = {}
        for entry in api_keys_str.split(","):
            parts = entry.strip().split(":")
            if len(parts) >= 2:
                key, user_id = parts[0], parts[1]
                role = parts[2] if len(parts) > 2 else "reader"
                access = "SECRET" if role == "admin" else "INTERNAL"
                result[key] = UserContext(
                    user_id=user_id, org_id="default",
                    access_level=access, display_name=user_id,
                    roles=[role, "reader"] if role != "reader" else ["reader"],
                    source="api_key",
                )
        if result:
            return result

    if settings.auth_required:
        _auth_log.error(
            "AUTH_REQUIRED=true but API_KEYS is empty. No users will be authenticated."
        )
        return {}

    _auth_log.warning(
        "Using built-in PoC API keys. Set API_KEYS env var for production."
    )
    return {
        "bw-default-key": UserContext(
            user_id="default_user", org_id="default",
            access_level="INTERNAL", display_name="默认用户",
            roles=["reader"], source="api_key",
        ),
        "bw-admin-key": UserContext(
            user_id="admin", org_id="default",
            access_level="SECRET", display_name="管理员",
            roles=["admin", "reader"], source="api_key",
        ),
    }


_API_KEY_MAP: dict[str, UserContext] | None = None


def _get_api_key_map() -> dict[str, UserContext]:
    """懒加载 API Key 映射（避免 import 时副作用，便于测试 monkeypatch settings）。"""
    global _API_KEY_MAP
    if _API_KEY_MAP is None:
        _API_KEY_MAP = _build_api_key_map()
    return _API_KEY_MAP


def reset_api_key_map_for_test() -> None:
    """测试用：清掉缓存，让下次读 settings 重建。"""
    global _API_KEY_MAP
    _API_KEY_MAP = None


# 不需要认证的路径
SKIP_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


# ════════════════════════════════════════════════════════════════════════
#  AuthMiddleware
# ════════════════════════════════════════════════════════════════════════


class AuthMiddleware(BaseHTTPMiddleware):
    """三模式 dispatch：根据 ``settings.kap_auth_mode`` 选择验证逻辑。"""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in SKIP_PATHS:
            request.state.user = UserContext(user_id="anonymous", org_id="default")
            return await call_next(request)

        mode = settings.kap_auth_mode
        try:
            if mode == "jwt":
                user_ctx, error_resp = await self._auth_jwt(request)
            elif mode == "gateway_header":
                user_ctx, error_resp = self._auth_gateway_header(request)
            else:  # api_key
                user_ctx, error_resp = self._auth_api_key(request)
        except Exception as e:
            _auth_log.exception("auth_dispatch_failed mode=%s error=%s", mode, e)
            return JSONResponse(
                status_code=500,
                content={"detail": f"认证内部错误（mode={mode}）"},
            )

        if error_resp is not None:
            return error_resp

        request.state.user = user_ctx
        return await call_next(request)

    # ── api_key 模式（M0 行为保留）──

    def _auth_api_key(self, request: Request) -> tuple[UserContext, JSONResponse | None]:
        token = self._extract_token(request)
        api_key_map = _get_api_key_map()

        if not token:
            if settings.auth_required:
                return UserContext(), JSONResponse(
                    status_code=401,
                    content={"detail": "缺少认证凭证，请提供 X-API-Key 或 Bearer Token"},
                )
            return (
                UserContext(user_id="anonymous", org_id="default", source="anonymous"),
                None,
            )

        user_ctx_template = api_key_map.get(token)
        user_ctx = user_ctx_template.model_copy() if user_ctx_template else None
        if not user_ctx:
            if settings.auth_required:
                return UserContext(), JSONResponse(
                    status_code=403,
                    content={"detail": "无效的认证凭证"},
                )
            user_ctx = UserContext(user_id="anonymous", org_id="default", source="anonymous")

        return user_ctx, None

    # ── jwt 模式（M1 批 1 新增）──

    async def _auth_jwt(self, request: Request) -> tuple[UserContext, JSONResponse | None]:
        """验签 ISS JWT → Redis 拿 LoginUser → 转 UserContext。"""
        from packages.auth.iss_jwt import ISSJWTError, extract_user_key
        from packages.auth.iss_session import (
            ISSSessionError,
            fetch_iss_login_user,
            iss_login_user_to_kap_context,
        )

        token = self._extract_token(request)
        if not token:
            return UserContext(), JSONResponse(
                status_code=401,
                content={"detail": "缺少 Bearer Token"},
            )

        try:
            user_key = extract_user_key(token)
        except ISSJWTError as e:
            _auth_log.warning("jwt_decode_failed: %s", e)
            return UserContext(), JSONResponse(
                status_code=401,
                content={"detail": f"JWT 验签失败: {e}"},
            )

        try:
            iss_user = await fetch_iss_login_user(user_key)
        except ISSSessionError as e:
            _auth_log.warning("iss_redis_fetch_failed user_key=%s: %s", user_key, e)
            return UserContext(), JSONResponse(
                status_code=401,
                content={"detail": f"ISS 会话失效: {e}"},
            )

        return iss_login_user_to_kap_context(iss_user), None

    # ── gateway_header 模式（M1 批 1 新增）──

    def _auth_gateway_header(
        self, request: Request
    ) -> tuple[UserContext, JSONResponse | None]:
        """信任 ISS-Gateway 注入的 X-User-* header。

        Header 约定（与 ISS HeaderInterceptor 对齐 + KAP 扩展）：
        - X-User-Id      : 整数 user_id（必填）
        - X-User-Name    : 用户名 / 昵称
        - X-User-Roles   : 逗号分隔角色列表
        - X-User-Perms   : 逗号分隔权限码（可选）
        - X-Dept-Id      : 部门 ID（整数）
        - X-Data-Scope   : 数据权限级别 1-5（默认 5）
        - X-Access-Level : KAP 密级字符串（PUBLIC/INTERNAL/CONFIDENTIAL/SECRET/TOP_SECRET）
        """
        h = request.headers
        user_id = h.get("X-User-Id")
        if not user_id:
            return UserContext(), JSONResponse(
                status_code=401,
                content={"detail": "缺少网关注入的 X-User-Id header"},
            )

        roles = [r.strip() for r in h.get("X-User-Roles", "").split(",") if r.strip()]
        perms = {p.strip() for p in h.get("X-User-Perms", "").split(",") if p.strip()}

        try:
            dept_id = int(h["X-Dept-Id"]) if h.get("X-Dept-Id") else None
        except ValueError:
            dept_id = None
        try:
            data_scope = int(h.get("X-Data-Scope", "5"))
        except ValueError:
            data_scope = 5

        return (
            UserContext(
                user_id=user_id,
                display_name=h.get("X-User-Name", user_id),
                roles=roles,
                permissions=perms,
                dept_id=dept_id,
                data_scope_level=data_scope,
                access_level=h.get("X-Access-Level", "INTERNAL"),
                source="gateway",
            ),
            None,
        )

    # ── 工具方法 ──

    @staticmethod
    def _extract_token(request: Request) -> str | None:
        """从 X-API-Key 或 Authorization: Bearer 中提取 token。"""
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return api_key

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:].strip()

        return None


def get_current_user(request: Request) -> UserContext:
    """从 request.state 中获取当前用户上下文。"""
    return getattr(request.state, "user", UserContext(user_id="anonymous"))
