"""共享 ISS Redis 读 LoginUser，并把 ISS 用户身份转换为 KAP UserContext。

ISS-Auth 把 LoginUser 存在 Redis ``login_tokens:{user_key}``（``CacheConstants.LOGIN_TOKEN_KEY``）。
KAP Python 后端通过共享密钥验签 JWT 拿到 user_key 之后，直接读 Redis 取出完整 LoginUser，
而不是走 HTTP 调 ISS-Auth 来回（性能 + 单点故障考量）。

私有化部署可能 ISS Redis 与 KAP 自己的 Redis 是不同实例，因此 ``iss_redis_url`` 单独配置。
"""

from __future__ import annotations

import json

from packages.auth.iss_models import ISSLoginUser
from packages.common import get_logger, settings

log = get_logger("auth.iss_session")


class ISSSessionError(Exception):
    """ISS Redis 会话读取失败 / LoginUser 反序列化失败 / token 已过期被清理。"""


_async_redis = None


def _get_iss_redis():
    """异步 redis 客户端（懒加载单例）。

    使用独立连接池（与 KAP 自己的 Redis 解耦）；连接失败抛 ISSSessionError，
    不静默降级（坑 F 同款门控）。
    """
    global _async_redis
    if _async_redis is None:
        if not settings.iss_redis_url:
            raise ISSSessionError(
                "ISS_REDIS_URL 未配置，无法读取 ISS LoginUser。"
                "kap_auth_mode=jwt 必须配 ISS Redis 地址。"
            )
        try:
            import redis.asyncio as aioredis
        except ImportError as e:
            raise ISSSessionError(f"缺少 redis 依赖: {e}") from e
        _async_redis = aioredis.from_url(
            settings.iss_redis_url,
            decode_responses=True,
            encoding="utf-8",
        )
    return _async_redis


async def fetch_iss_login_user(user_key: str) -> ISSLoginUser:
    """从 ISS Redis 读取 LoginUser。

    Raises:
        ISSSessionError: token 已过期被清理 / Redis 不可达 / 反序列化失败。
    """
    if not user_key:
        raise ISSSessionError("user_key 为空")
    client = _get_iss_redis()
    full_key = f"{settings.iss_token_key_prefix}{user_key}"
    try:
        raw = await client.get(full_key)
    except Exception as e:
        raise ISSSessionError(f"ISS Redis 读取失败 key={full_key}: {e}") from e
    if raw is None:
        raise ISSSessionError(
            f"ISS LoginUser 不存在 key={full_key}（token 可能已过期或被登出清理）"
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ISSSessionError(f"ISS LoginUser 反序列化失败 key={full_key}: {e}") from e
    try:
        return ISSLoginUser.from_redis_payload(payload)
    except Exception as e:
        raise ISSSessionError(f"ISS LoginUser Pydantic 验证失败: {e}") from e


def iss_login_user_to_kap_context(iss_user: ISSLoginUser):
    """把 ISS LoginUser 转换为 KAP UserContext。

    映射规则：
    - ``userid`` → ``user_id``（str 化以兼容现有 KAP 字符串 user_id）
    - ``username`` → ``display_name``
    - ``roles``（ISS Set<String>）→ ``roles``（list[str]，由 KAP normalize_roles 进一步规范化）
    - ``permissions`` → ``permissions``（set[str]）
    - ``sys_user.dept_id`` → ``dept_id``（int）
    - ``data_scope_level`` 暂取最严（5=SELF），M1 批 3 引入角色级 dataScope 后由
      ``iss_remote_client`` 拉角色 dataScope 再合并取最宽
    - ``access_level`` 不在 ISS 模型里，沿用 KAP 默认 INTERNAL
    - ``source = "jwt"`` 标记来源便于审计
    """
    from packages.common.auth import UserContext

    sys_user = iss_user.sys_user
    return UserContext(
        user_id=str(iss_user.userid) if iss_user.userid is not None else "anonymous",
        display_name=iss_user.username or "",
        roles=sorted(iss_user.roles),
        permissions=set(iss_user.permissions),
        dept_id=sys_user.dept_id if sys_user else None,
        data_scope_level=5,  # 批 3 起由 iss_remote_client 拉角色 dataScope 取最宽
        source="jwt",
    )


async def reset_iss_redis_for_test() -> None:
    """测试用：清掉单例，让下次读 settings 重建客户端。"""
    global _async_redis
    if _async_redis is not None:
        try:
            await _async_redis.close()
        except Exception:
            pass
    _async_redis = None
