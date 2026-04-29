"""KAP M1 · ISS 集成认证包（决策书 §9.1 / PRD §10.4）。

KAP 是 Python 后端，ISS 是 Java 后端，两者通过**协议层**对接（不 import Java 二方包）：

- ``iss_jwt``      — HS512 JWT 验签，提取 user_key UUID（与 ISS-Auth `JwtUtils` 对齐）
- ``iss_session``  — 共享 ISS Redis 读 ``login_tokens:{user_key}``，反序列化为 ``ISSLoginUser``
- ``iss_models``   — Pydantic 镜像 ISS 的 LoginUser / SysUser / SysDept 字段
- ``iss_remote_client`` — httpx.AsyncClient 调 ISS-System 的部门/用户 HTTP 接口（批 2）
- ``data_scope``   — 5 级数据权限的 Python 等价实现（批 3）

设计原则（feedback memory · ISS 零侵入）：
- 不改 ISS Java 源码 / 数据库 schema / 二方包
- 只通过 ISS 公开协议接入：JWT / Redis / HTTP
"""

from packages.auth.iss_jwt import (
    ISSJWTError,
    decode_iss_jwt,
    extract_user_key,
)
from packages.auth.iss_models import ISSDept, ISSLoginUser, ISSSysUser
from packages.auth.iss_session import (
    ISSSessionError,
    fetch_iss_login_user,
    iss_login_user_to_kap_context,
)

__all__ = [
    "ISSDept",
    "ISSJWTError",
    "ISSLoginUser",
    "ISSSessionError",
    "ISSSysUser",
    "decode_iss_jwt",
    "extract_user_key",
    "fetch_iss_login_user",
    "iss_login_user_to_kap_context",
]
