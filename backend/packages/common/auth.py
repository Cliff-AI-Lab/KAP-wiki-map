"""用户认证上下文模型。

本模块定义了用户认证后的上下文数据结构，贯穿整个 HTTP 请求生命周期。
在 FastAPI 的依赖注入体系中，UserContext 由认证中间件解析后注入到各路由函数，
用于实现多租户数据隔离和基于角色/部门的权限控制。

典型使用场景：
- 知识检索时根据 org_id 隔离不同组织的数据
- 根据 access_level 过滤用户可见的文档
- 根据 department_id / dept_id 实现部门级数据权限
- 根据 data_scope_level 应用 ISS 5 级数据权限（M1 批 3）
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# 数据权限默认值（M1 ISS 集成 · 决策书 §8.1）
# 5 = SELF (最严)，匿名用户默认仅能看自己创建的；ISS LoginUser 同步过来按真实角色取最宽
DATA_SCOPE_DEFAULT = 5

UserContextSource = Literal["api_key", "jwt", "gateway", "anonymous"]


class UserContext(BaseModel):
    """认证后的用户上下文，贯穿整个请求生命周期。

    M0-tech-debt 坑 7+8 改造：
    - 新增 ``max_access_level: int``（0-3 整数密级），与 Milvus schema 对齐
    - 召回路径直接传 ``user.max_access_level`` 给 ``vector_store.search()``
    - V15 ``access_level`` 字符串保留兼容，由 ``model_post_init`` 同步到 int

    M1 ISS 集成（批 1）：
    - ``dept_id``：与 ISS sys_user.dept_id 对齐的整型部门 ID（数据权限根）
    - ``data_scope_level``：ISS DataScope 1-5（1=ALL / 2=CUSTOM / 3=DEPT /
      4=DEPT_AND_CHILD / 5=SELF）。多角色取并集后由调用方计算最宽值
    - ``custom_dept_ids``：dataScope=2 自定义模式下的部门白名单
    - ``permissions``：ISS LoginUser.permissions（如 ``system:user:list``）
    - ``source``：UserContext 来源，便于审计与降级判断

    Attributes:
        user_id: 用户唯一标识，匿名用户默认为 "anonymous"
        org_id: 组织/租户 ID，用于多租户数据隔离，默认为 "default"
        access_level: 访问级别字符串（V15 兼容，如 PUBLIC / INTERNAL / CONFIDENTIAL）
        max_access_level: 密级整数（0=公开 / 1=内部 / 2=秘密 / 3=机密），
            **召回阶段 Milvus expr 直接用此字段（坑 8）**
        department_id: 用户所属部门 ID 字符串（V15 兼容，与 metadata_store
            documents.department_id VARCHAR 对齐）
        dept_id: ISS sys_user.dept_id 整型（M1 批 3 DataScope 用），
            可与 department_id 共存（前者对接 ISS、后者保留 V15 兼容）
        data_scope_level: ISS 5 级数据权限（默认 5=SELF 最严）
        custom_dept_ids: dataScope=2 模式的自定义部门白名单
        roles: 用户角色列表（KAP: DG/SME/SEC/AIOps/READER，含 V15 admin/editor 别名兼容）
        permissions: 细粒度权限集合（与 ISS LoginUser.permissions 对齐）
        display_name: 用户显示名称，用于前端展示和审计日志
        source: UserContext 来源（api_key/jwt/gateway/anonymous）
    """

    user_id: str = "anonymous"
    org_id: str = "default"
    access_level: str = "INTERNAL"
    max_access_level: int = 1  # 默认 INTERNAL=1，由 model_post_init 同步
    department_id: str = ""
    dept_id: int | None = None
    data_scope_level: int = DATA_SCOPE_DEFAULT
    custom_dept_ids: list[int] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    permissions: set[str] = Field(default_factory=set)
    display_name: str = ""
    source: UserContextSource = "anonymous"

    def model_post_init(self, __context: object) -> None:
        """同步 access_level 字符串到 max_access_level int（坑 7+8 联动）。"""
        from packages.common.roles import access_level_to_int
        # 仅在 max_access_level 是默认值（1）且 access_level 非默认时才同步
        # 显式传 max_access_level 的 case 优先
        if self.max_access_level == 1 and self.access_level != "INTERNAL":
            object.__setattr__(
                self,
                "max_access_level",
                access_level_to_int(self.access_level, default=1),
            )
