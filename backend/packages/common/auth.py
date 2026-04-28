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

    该模型在认证中间件中构建，通过 FastAPI 依赖注入传递给下游处理函数，
    承载用户身份、组织归属和权限信息。

    Attributes:
        user_id: 用户唯一标识，匿名用户默认为 "anonymous"
        org_id: 组织/租户 ID，用于多租户数据隔离，默认为 "default"
        access_level: 访问级别（如 PUBLIC / INTERNAL / CONFIDENTIAL），
            控制用户可访问的文档密级范围
        department_id: 用户所属部门 ID，用于部门级权限过滤
        roles: 用户角色列表（如 admin / editor / viewer），用于功能级权限控制
        display_name: 用户显示名称，用于前端展示和审计日志
    """

    user_id: str = "anonymous"
    org_id: str = "default"
    access_level: str = "INTERNAL"
    department_id: str = ""
    roles: list[str] = Field(default_factory=list)
    display_name: str = ""
