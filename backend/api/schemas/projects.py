"""
项目管理 API 的请求/响应模型模块。

定义项目管理相关的 Pydantic 数据模型，包括：
- 行业分类体系（TaxonomyNodeOut）：树形知识目录结构
- 行业模板（IndustryListItem / IndustryTemplateOut）：预定义的行业知识框架
- 项目 CRUD（ProjectCreate / ProjectUpdate / ProjectSummary / ProjectDetail）
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TaxonomyNodeOut(BaseModel):
    """知识分类体系节点（树形结构）。

    每个节点代表知识目录中的一个分类层级，通过 children 字段
    形成递归树结构，用于展示行业知识的层次化分类。
    """
    id: str                                    # 节点唯一标识
    name: str                                  # 节点名称（如"发电技术"）
    level: int                                 # 层级深度（0=根节点）
    description: str = ""                      # 节点描述
    children: list[TaxonomyNodeOut] = []       # 子节点列表


class IndustryListItem(BaseModel):
    """行业列表项，用于行业选择页面展示。

    包含行业的基本信息和统计数据，供用户创建项目时选择行业模板。
    """
    code: str              # 行业编码（如 "energy"）
    name: str              # 行业中文名称
    name_en: str           # 行业英文名称
    icon: str              # 行业图标标识
    description: str       # 行业描述
    department_count: int  # 该行业预设的部门数量
    domain_count: int      # 该行业预设的知识域数量


class IndustryTemplateOut(BaseModel):
    """行业模板详情，包含完整的知识分类体系。

    在用户选定行业后返回，提供该行业预定义的完整知识目录树，
    作为项目知识管理的初始框架。
    """
    code: str                          # 行业编码
    name: str                          # 行业中文名称
    name_en: str                       # 行业英文名称
    icon: str                          # 行业图标标识
    description: str                   # 行业描述
    taxonomy: list[TaxonomyNodeOut]    # 知识分类体系（树形结构）


class ProjectCreate(BaseModel):
    """创建项目的请求模型。"""
    name: str = Field(..., min_length=1, max_length=256)       # 项目名称
    industry_code: str = Field(..., min_length=1, max_length=32)  # 行业编码
    description: str = ""                                       # 项目描述（可选）


class ProjectUpdate(BaseModel):
    """更新项目的请求模型（部分更新，仅传入需修改的字段）。"""
    name: Optional[str] = None          # 新项目名称
    description: Optional[str] = None   # 新项目描述
    status: Optional[str] = None        # 新项目状态（如 ACTIVE / ARCHIVED）


class ProjectSummary(BaseModel):
    """项目摘要信息，用于项目列表展示。"""
    id: str                            # 项目唯一标识
    name: str                          # 项目名称
    industry_code: str                 # 所属行业编码
    industry_name: str = ""            # 所属行业名称
    description: str = ""              # 项目描述
    status: str = "ACTIVE"             # 项目状态
    doc_count: int = 0                 # 已导入文档数量
    domain_count: int = 0              # 知识域数量
    created_at: Optional[str] = None   # 创建时间（ISO 格式）


class ProjectDetail(ProjectSummary):
    """项目详情信息，继承摘要字段并扩展完整信息。"""
    taxonomy_snapshot: Optional[list] = None  # 知识分类体系快照（创建时冻结）
    updated_at: Optional[str] = None          # 最后更新时间（ISO 格式）
