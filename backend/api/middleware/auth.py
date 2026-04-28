"""认证中间件 — API Key / Bearer Token 解析。

PoC 阶段默认不强制认证，未携带凭证的请求附加匿名 UserContext。
生产环境应设置 AUTH_REQUIRED=true 和 API_KEYS 环境变量。
"""

from __future__ import annotations

import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from packages.common import settings
from packages.common.auth import UserContext

_auth_log = logging.getLogger("auth")


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
                )
        if result:
            return result

    # auth_required=True 但没配 API_KEYS → 生产环境不应使用 PoC 密钥
    if settings.auth_required:
        _auth_log.error(
            "AUTH_REQUIRED=true but API_KEYS is empty. No users will be authenticated."
        )
        return {}

    # PoC 默认值 — 仅 auth_required=False (开发环境) 时启用
    _auth_log.warning(
        "Using built-in PoC API keys. Set API_KEYS env var for production."
    )
    return {
        "bw-default-key": UserContext(
            user_id="default_user", org_id="default",
            access_level="INTERNAL", display_name="默认用户", roles=["reader"],
        ),
        "bw-admin-key": UserContext(
            user_id="admin", org_id="default",
            access_level="SECRET", display_name="管理员", roles=["admin", "reader"],
        ),
    }


_API_KEY_MAP: dict[str, UserContext] = _build_api_key_map()

# 不需要认证的路径
SKIP_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


class AuthMiddleware(BaseHTTPMiddleware):
    """从请求头中提取 API Key 或 Bearer Token，注入 UserContext。"""

    async def dispatch(self, request: Request, call_next):
        # 跳过不需要认证的路径
        if request.url.path in SKIP_PATHS:
            request.state.user = UserContext(user_id="anonymous", org_id="default")
            return await call_next(request)

        token = self._extract_token(request)

        if not token:
            if settings.auth_required:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "缺少认证凭证，请提供 X-API-Key 或 Bearer Token"},
                )
            # PoC 模式默认放行
            request.state.user = UserContext(user_id="anonymous", org_id="default")
            return await call_next(request)

        user_ctx_template = _API_KEY_MAP.get(token)
        # 每次请求创建副本，防止可变状态跨请求泄漏
        user_ctx = user_ctx_template.model_copy() if user_ctx_template else None
        if not user_ctx:
            if settings.auth_required:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "无效的认证凭证"},
                )
            # PoC 模式：未识别的 key 也放行，附加匿名上下文
            user_ctx = UserContext(user_id="anonymous", org_id="default")

        request.state.user = user_ctx
        return await call_next(request)

    @staticmethod
    def _extract_token(request: Request) -> str | None:
        """从 X-API-Key 或 Authorization: Bearer 中提取 token。"""
        # 优先检查 X-API-Key
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return api_key

        # 其次检查 Bearer Token
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:].strip()

        return None


def get_current_user(request: Request) -> UserContext:
    """从 request.state 中获取当前用户上下文。"""
    return getattr(request.state, "user", UserContext(user_id="anonymous"))
