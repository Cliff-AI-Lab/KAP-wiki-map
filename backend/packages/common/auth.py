"""用户认证上下文模型。

本模块定义了用户认证后的上下文数据结构，贯穿整个 HTTP 请求生命周期。
在 FastAPI 的依赖注入体系中，UserContext 由认证中间件解析后注入到各路由函数，
用于实现多租户数据隔离和基于角色/部门的权限控制。

典型使用场景：
- 知识检索时根据 org_id 隔离不同组织的数据
- 根据 access_level 过滤用户可见的文档
- 根据 department_id 实现部门级数据权限
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class UserContext(BaseModel):
    """认证后的用户上下文，贯穿整个请求生命周期。

    M0-tech-debt 坑 7+8 改造：
    - 新增 ``max_access_level: int``（0-3 整数密级），与 Milvus schema 对齐
    - 召回路径直接传 ``user.max_access_level`` 给 ``vector_store.search()``
    - V15 ``access_level`` 字符串保留兼容，由 ``model_post_init`` 同步到 int

    Attributes:
        user_id: 用户唯一标识，匿名用户默认为 "anonymous"
        org_id: 组织/租户 ID，用于多租户数据隔离，默认为 "default"
        access_level: 访问级别字符串（V15 兼容，如 PUBLIC / INTERNAL / CONFIDENTIAL）
        max_access_level: 密级整数（0=公开 / 1=内部 / 2=秘密 / 3=机密），
            **召回阶段 Milvus expr 直接用此字段（坑 8）**
        department_id: 用户所属部门 ID，用于部门级权限过滤
        roles: 用户角色列表（KAP: DG/SME/SEC/AIOps/READER，含 V15 admin/editor 别名兼容）
        display_name: 用户显示名称，用于前端展示和审计日志
    """

    user_id: str = "anonymous"
    org_id: str = "default"
    access_level: str = "INTERNAL"
    max_access_level: int = 1  # 默认 INTERNAL=1，由 model_post_init 同步
    department_id: str = ""
    roles: list[str] = Field(default_factory=list)
    display_name: str = ""

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
