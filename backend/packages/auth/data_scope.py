"""ISS DataScope 5 级数据权限的 Python 等价实现（轻量函数式）。

ISS Java 端 ``DataScopeAspect`` 用 MyBatis SQL 拼接（``OR dept_id IN (...)``），
KAP 不依赖 MyBatis，所以**只保留语义**，不复刻 SQL builder。

5 级语义（与 ISS DataScopeAspect 字段对齐）：

| 级别 | 含义                       | KAP 实现                                                |
|:---:|:---|:---|
| 1   | ALL — 全部数据             | 不加过滤                                                 |
| 2   | CUSTOM — 自定义部门集合    | dept_id ∈ user.custom_dept_ids                          |
| 3   | DEPT — 仅本部门            | dept_id == user.dept_id                                 |
| 4   | DEPT_AND_CHILD — 部门及子部门 | dept_id ∈ fetch_dept_descendants(user.dept_id)        |
| 5   | SELF — 仅本人              | created_by == user.user_id                              |

KAP 调用方式：
- ``await build_milvus_expr(user)`` → 给 retriever 召回时拼到 Milvus expr（与 max_access_level 用 && 串联）
- ``await matches(user, doc_dept_id, doc_owner_id)`` → 内存模式 / Neo4j 后过滤 / 单文档访问校验

设计选择：
- **超级管理员豁免**：`ALL` 通过设角色 dataScope=1 实现（决策书 §8.1 / ISS DataScopeAspect 同款）
- **多角色取并集**：UserContext.data_scope_level 已经是预先计算好的"最宽"级别，
  这里直接用，不再做角色循环（计算逻辑放在 iss_session 转换 + 批 4 角色 dataScope 拉取）
- **缺 dept_id 默认拒绝**：data_scope ∈ {3,4} 但 user.dept_id is None → 返回不可能匹配的 expr，
  防止权限旁路
"""

from __future__ import annotations

from packages.common.auth import UserContext

# 5 级常量（与 ISS DataScopeAspect 字段一致）
DATA_SCOPE_ALL = 1
DATA_SCOPE_CUSTOM = 2
DATA_SCOPE_DEPT = 3
DATA_SCOPE_DEPT_AND_CHILD = 4
DATA_SCOPE_SELF = 5


# Milvus expr 永真 / 永假占位（M0 坑 8 同款）
_EXPR_TRUE = ""           # 空串等价于无过滤
_EXPR_NEVER = "dept_id == -1"  # 永假，dept_id 不会是负数（int8 默认 0+）


async def build_milvus_expr(user: UserContext) -> str:
    """生成 Milvus expr 片段（不含 max_access_level，由 retriever 再 && 串联）。

    Args:
        user: 已认证用户上下文

    Returns:
        Milvus expr 字符串，空串表示无过滤（DataScope=ALL）
    """
    level = user.data_scope_level

    if level == DATA_SCOPE_ALL:
        return _EXPR_TRUE

    if level == DATA_SCOPE_CUSTOM:
        if not user.custom_dept_ids:
            return _EXPR_NEVER
        ids = ",".join(str(d) for d in user.custom_dept_ids)
        return f"dept_id in [{ids}]"

    if level == DATA_SCOPE_DEPT:
        if user.dept_id is None:
            return _EXPR_NEVER
        return f"dept_id == {user.dept_id}"

    if level == DATA_SCOPE_DEPT_AND_CHILD:
        if user.dept_id is None:
            return _EXPR_NEVER
        from packages.auth.iss_remote_client import fetch_dept_descendants
        descendants = await fetch_dept_descendants(user.dept_id)
        ids = ",".join(str(d) for d in descendants)
        return f"dept_id in [{ids}]"

    # DATA_SCOPE_SELF (5) 是默认值
    if user.user_id == "anonymous":
        return _EXPR_NEVER
    # 用 created_by 字段（W4 工位写入时挂上）；没用引号是因为 Milvus VARCHAR 需要 ""
    return f'created_by == "{user.user_id}"'


async def matches(
    user: UserContext,
    doc_dept_id: int | None,
    doc_owner_id: str | None,
) -> bool:
    """单文档级别的过滤（内存模式 / 单条详情访问校验用）。

    Args:
        user: 已认证用户
        doc_dept_id: 文档归属部门 ID（可能为 None，老数据/未分配）
        doc_owner_id: 文档创建者 user_id（可能为 None）
    """
    level = user.data_scope_level

    if level == DATA_SCOPE_ALL:
        return True

    if level == DATA_SCOPE_CUSTOM:
        return doc_dept_id is not None and doc_dept_id in user.custom_dept_ids

    if level == DATA_SCOPE_DEPT:
        return doc_dept_id is not None and user.dept_id is not None and doc_dept_id == user.dept_id

    if level == DATA_SCOPE_DEPT_AND_CHILD:
        if doc_dept_id is None or user.dept_id is None:
            return False
        from packages.auth.iss_remote_client import fetch_dept_descendants
        descendants = await fetch_dept_descendants(user.dept_id)
        return doc_dept_id in descendants

    # SELF
    return doc_owner_id is not None and doc_owner_id == user.user_id
