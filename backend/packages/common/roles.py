"""KAP 角色枚举 + 密级整数映射（M0-tech-debt 坑 7 + 坑 8 主要交付物）。

决策书 §1.5 / §5.2 锁定的 5 角色 + 4 级密级体系：

角色（roles）：

- ``DG``    数据治理员（Data Governor）— 分类、命名、版本
- ``SME``   业务专家（Subject Matter Expert）— W4 实体审核、本体演化
- ``SEC``   安全审计员（Security & Compliance）— 密级、脱敏、合规
- ``AIOps`` AI 运营员（AI Operations）— 命中率、Prompt 调优
- ``READER`` 终端业务用户 — 消费知识、提反馈

密级（access_level，与 Milvus schema int8 字段对齐）：

- ``0`` PUBLIC       公开
- ``1`` INTERNAL     内部（KAP 默认）
- ``2`` CONFIDENTIAL 秘密
- ``3`` TOP_SECRET   机密

M0 实现范围：
- 角色 / 密级常量与映射函数
- Require* FastAPI Dependency 用于 endpoint 装饰
- ``UserContext.max_access_level`` int 字段，召回路径直接传给 ``vector_store.search()``

M1 后续：
- ISS-Auth JWT claims 完整对接（roles / data_scope_level / access_level）
- 完整 4 级密级映射规则（按 Owner 角色 + Facet 推断）
"""

from __future__ import annotations

from typing import Iterable

from fastapi import Depends, HTTPException, Request


# ──────── 角色枚举（决策书 §1.5）────────

ROLE_DG = "DG"
ROLE_SME = "SME"
ROLE_SEC = "SEC"
ROLE_AIOPS = "AIOps"
ROLE_READER = "READER"

# Wiki-map V15 兼容别名（避免一刀切破坏旧 API Key 配置）
LEGACY_ROLE_ADMIN = "admin"     # ≈ DG
LEGACY_ROLE_EDITOR = "editor"   # ≈ SME（V15 双模式 Editor）

ALL_ROLES = (ROLE_DG, ROLE_SME, ROLE_SEC, ROLE_AIOPS, ROLE_READER)

# 角色提权：admin → 含 DG + SME + AIOps（开发期便利，私有化部署应禁用）
ADMIN_ROLES_EXPANDED = (ROLE_DG, ROLE_SME, ROLE_AIOPS, ROLE_READER)


# ──────── 密级（决策书 §8.1）────────

ACCESS_PUBLIC = 0
ACCESS_INTERNAL = 1
ACCESS_CONFIDENTIAL = 2
ACCESS_TOP_SECRET = 3

# 字符串 → int 映射（兼容 V15 字符串密级）
_ACCESS_STR_TO_INT = {
    "PUBLIC": ACCESS_PUBLIC,
    "INTERNAL": ACCESS_INTERNAL,
    "CONFIDENTIAL": ACCESS_CONFIDENTIAL,
    "SECRET": ACCESS_CONFIDENTIAL,    # V15 用 SECRET，对齐为秘密级
    "TOP_SECRET": ACCESS_TOP_SECRET,
    "公开": ACCESS_PUBLIC,
    "内部": ACCESS_INTERNAL,
    "秘密": ACCESS_CONFIDENTIAL,
    "机密": ACCESS_TOP_SECRET,
}

# int → 字符串展示（用于审计日志 / 前端展示）
_ACCESS_INT_TO_LABEL = {
    ACCESS_PUBLIC: "公开",
    ACCESS_INTERNAL: "内部",
    ACCESS_CONFIDENTIAL: "秘密",
    ACCESS_TOP_SECRET: "机密",
}


def access_level_to_int(level: str | int | None, default: int = ACCESS_INTERNAL) -> int:
    """将密级字符串规范为 int。

    >>> access_level_to_int("SECRET")
    2
    >>> access_level_to_int("公开")
    0
    >>> access_level_to_int(None)
    1  # 默认 INTERNAL
    """
    if level is None or level == "":
        return default
    if isinstance(level, int):
        return level if 0 <= level <= 3 else default
    return _ACCESS_STR_TO_INT.get(str(level).strip().upper(), default)


def access_level_label(level: int) -> str:
    return _ACCESS_INT_TO_LABEL.get(level, "内部")


# ──────── 角色规范化（兼容 V15 别名）────────


def normalize_roles(roles: Iterable[str]) -> list[str]:
    """把角色列表规范化为 KAP 5 角色枚举。

    V15 旧别名映射：admin → DG + SME + AIOps + READER；editor → SME + READER。
    所有非匿名用户至少含 READER。
    """
    out: set[str] = set()
    for r in roles:
        if not r:
            continue
        rl = str(r).strip()
        if rl in ALL_ROLES:
            out.add(rl)
        elif rl == LEGACY_ROLE_ADMIN:
            out.update(ADMIN_ROLES_EXPANDED)
        elif rl == LEGACY_ROLE_EDITOR:
            out.update((ROLE_SME, ROLE_READER))
        elif rl == "reader":
            out.add(ROLE_READER)
        else:
            # 未知角色保留原值（便于排查）但不参与权限决策
            out.add(rl)
    return sorted(out)


# ──────── FastAPI Dependency（坑 7 主要交付物）────────


def get_current_user(request: Request):
    """读取 request.state.user（由 AuthMiddleware 注入）。

    返回 UserContext。匿名请求返回带默认值的实例。
    """
    from packages.common.auth import UserContext
    return getattr(request.state, "user", UserContext(user_id="anonymous"))


def RequireRole(*allowed_roles: str):
    """要求用户至少持有 ``allowed_roles`` 中的一个角色。

    用法（FastAPI 路由参数）::

        @router.post("/review")
        async def review_endpoint(
            user = Depends(RequireRole(ROLE_SME, ROLE_DG)),
        ):
            ...
    """
    allowed = set(allowed_roles)

    async def _checker(request: Request):
        user = get_current_user(request)
        user_roles = set(normalize_roles(user.roles))
        if not (allowed & user_roles):
            raise HTTPException(
                status_code=403,
                detail=f"需要角色 {sorted(allowed)} 之一，当前 {sorted(user_roles) or ['匿名']}",
            )
        return user

    return _checker


def RequireAccessLevel(min_level: int):
    """要求用户密级 ≥ min_level。

    用法（高密文档原文访问端点）::

        @router.get("/docs/{doc_id}/raw")
        async def raw_doc(
            user = Depends(RequireAccessLevel(ACCESS_CONFIDENTIAL)),
        ):
            ...
    """
    async def _checker(request: Request):
        user = get_current_user(request)
        if user.max_access_level < min_level:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"需要密级 ≥ {access_level_label(min_level)}（{min_level}），"
                    f"当前 {access_level_label(user.max_access_level)}（{user.max_access_level}）"
                ),
            )
        return user

    return _checker
