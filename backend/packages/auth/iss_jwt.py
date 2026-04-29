"""ISS-Auth HS512 JWT 验签（与 ``com.isoftstone.common.core.utils.JwtUtils`` 对齐）。

ISS JWT 特征：
- 算法 HS512（HMAC-SHA512），共享密钥 ``ISS_JWT_SECRET``
- claims 仅承载 ``user_key`` UUID（``SecurityConstants.USER_KEY``），不含 user_id/roles
- 真正的用户信息在 Redis ``login_tokens:{user_key}``，验签后再去取（见 ``iss_session``）

依赖 PyJWT 标准库实现，避免自己写 base64url + HMAC 比较。
"""

from __future__ import annotations

import jwt
from jwt import InvalidTokenError

from packages.common import get_logger, settings

log = get_logger("auth.iss_jwt")


class ISSJWTError(Exception):
    """JWT 验签 / 解码失败。"""


def decode_iss_jwt(token: str, *, verify_exp: bool = True) -> dict:
    """验签 ISS JWT 并返回 claims dict。

    Args:
        token: 不含 "Bearer " 前缀的 JWT 字符串。
        verify_exp: 是否校验过期时间（测试期可关，生产必开）。

    Raises:
        ISSJWTError: secret 未配置 / 签名错误 / token 过期 / 格式非法。
    """
    if not token:
        raise ISSJWTError("token 为空")
    secret = settings.iss_jwt_secret
    if not secret:
        raise ISSJWTError("ISS_JWT_SECRET 未配置，无法验签")
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[settings.iss_jwt_algorithm],
            options={"verify_exp": verify_exp},
        )
    except InvalidTokenError as e:
        # PyJWT 异常类涵盖签名错误 / 过期 / 格式错误等
        raise ISSJWTError(f"JWT 验签失败: {e}") from e
    return claims


def extract_user_key(token: str, *, verify_exp: bool = True) -> str:
    """从 JWT 提取 user_key UUID（用于到 Redis 取 LoginUser）。

    Raises:
        ISSJWTError: 验签失败 / claims 中缺少 user_key 字段。
    """
    claims = decode_iss_jwt(token, verify_exp=verify_exp)
    key_field = settings.iss_jwt_user_key_claim
    user_key = claims.get(key_field)
    if not user_key:
        raise ISSJWTError(
            f"JWT claims 中缺少 ``{key_field}`` 字段（实际 keys={list(claims.keys())}）"
        )
    return str(user_key)
