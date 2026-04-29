"""行业模板注册表 — 管理所有预置行业的四级知识体系 + Facet schema。

V15: 仅 taxonomy（四级目录）。
M1: 加 Facet schema（PRD §10.4 1129 行 — 设备故障 / 工艺标准 / SOP / 质量记录 4 套）
    用于 W3 切块时抽取必填属性 + W4 抽取实体关系时验证。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from packages.common.types import KnowledgeDomain


class TaxonomyNode(BaseModel):
    """知识体系节点（支持四级嵌套）。"""
    id: str
    name: str
    level: int
    description: str = ""
    children: list[TaxonomyNode] = []


# ════════════════════════════════════════════════════════════════════════
#  Facet schema（M1 #2）
# ════════════════════════════════════════════════════════════════════════

FacetFieldType = Literal[
    "str",        # 自由文本
    "int",        # 整数
    "numeric",    # 浮点带单位（含 unit 字段）
    "date",       # ISO 日期
    "enum",       # 枚举（含 enum_values）
    "reference",  # 关联其他实体（含 ref_type）
]


class FacetField(BaseModel):
    """单个属性字段定义（决策书 §7 双层本体 L1 字段子集）。"""
    key: str                          # 英文键名（用于 metadata dict）
    name: str                         # 中文显示名
    type: FacetFieldType
    required: bool = False
    sensitive: bool = False           # 敏感字段（人名 / 工艺参数等，触发脱敏管线 §5.4）
    description: str = ""
    unit: str = ""                    # numeric 类型的单位（如 "MPa" / "℃"）
    enum_values: list[str] = Field(default_factory=list)  # enum 类型的合法值
    ref_type: str = ""                # reference 类型指向的实体类型（如 "Equipment" / "Person"）


class FacetSchema(BaseModel):
    """文档类型的元数据 schema（W3 切块抽取 + W4 抽取实体时校验）。"""
    doc_type: str                     # 文档类型 code，如 "equipment_fault"
    name: str                         # 中文名（如 "设备故障"）
    description: str = ""
    fields: list[FacetField] = Field(default_factory=list)
    primary_role: str = "SME"         # W4 主审角色（决策书 §5.2 矩阵 R）

    def required_keys(self) -> list[str]:
        return [f.key for f in self.fields if f.required]

    def sensitive_keys(self) -> list[str]:
        return [f.key for f in self.fields if f.sensitive]


class IndustryTemplate(BaseModel):
    """行业模板定义（M1 加 facets 子项）。"""
    code: str
    name: str
    name_en: str
    icon: str
    description: str
    taxonomy: list[TaxonomyNode]
    facets: dict[str, FacetSchema] = Field(default_factory=dict)  # doc_type → schema


# ── 注册表 ────────────────────────────────────────────

INDUSTRY_REGISTRY: dict[str, IndustryTemplate] = {}


def register(template: IndustryTemplate) -> None:
    """注册一个行业模板。"""
    INDUSTRY_REGISTRY[template.code] = template


def list_industries() -> list[dict]:
    """返回所有行业的摘要列表。"""
    result = []
    for t in INDUSTRY_REGISTRY.values():
        dept_count = len(t.taxonomy)
        domain_count = _count_nodes(t.taxonomy)
        result.append({
            "code": t.code,
            "name": t.name,
            "name_en": t.name_en,
            "icon": t.icon,
            "description": t.description,
            "department_count": dept_count,
            "domain_count": domain_count,
        })
    return result


def get_template(code: str) -> IndustryTemplate | None:
    """根据 code 获取行业模板。"""
    return INDUSTRY_REGISTRY.get(code)


def get_facet_schema(industry_code: str, doc_type: str) -> FacetSchema | None:
    """按行业 code + 文档类型查 Facet schema（W3/W4 工位用）。"""
    template = INDUSTRY_REGISTRY.get(industry_code)
    if not template:
        return None
    return template.facets.get(doc_type)


def validate_facet_metadata(
    schema: FacetSchema, metadata: dict
) -> list[str]:
    """轻量校验：返回缺失的 required 字段列表（空表示全通过）。

    M1 lite — 仅检查 required 字段是否提供；类型校验留给 Pydantic / W4 抽取阶段。
    """
    missing = []
    for f in schema.fields:
        if f.required:
            val = metadata.get(f.key)
            if val is None or val == "":
                missing.append(f.key)
    return missing


def template_to_domains(
    template: IndustryTemplate, project_id: str
) -> list[KnowledgeDomain]:
    """将行业模板展平为 KnowledgeDomain 列表，带 project_id 前缀。"""
    domains: list[KnowledgeDomain] = []
    # L1: 行业根节点
    root_id = template.code
    domains.append(KnowledgeDomain(
        domain_id=root_id,
        name=template.name,
        parent_id="",
        description=template.description,
        is_system=True,
    ))
    # 递归展开子节点
    for node in template.taxonomy:
        _flatten_node(node, parent_id=root_id, domains=domains)
    return domains


def _flatten_node(
    node: TaxonomyNode,
    parent_id: str,
    domains: list[KnowledgeDomain],
) -> None:
    """递归展平节点树。"""
    full_id = f"{parent_id}/{node.id}" if parent_id else node.id
    domains.append(KnowledgeDomain(
        domain_id=full_id,
        name=node.name,
        parent_id=parent_id,
        description=node.description,
        is_system=True,
    ))
    for child in node.children:
        _flatten_node(child, parent_id=full_id, domains=domains)


def _count_nodes(nodes: list[TaxonomyNode]) -> int:
    """递归计算节点总数。"""
    count = 0
    for n in nodes:
        count += 1 + _count_nodes(n.children)
    return count


# ── 自动注册所有行业模板 ──────────────────────────────

def _auto_register() -> None:
    from packages.templates.energy import ENERGY_TEMPLATE
    from packages.templates.manufacturing import MANUFACTURING_TEMPLATE
    from packages.templates.it import IT_TEMPLATE
    from packages.templates.finance import FINANCE_TEMPLATE
    from packages.templates.healthcare import HEALTHCARE_TEMPLATE

    for t in [ENERGY_TEMPLATE, MANUFACTURING_TEMPLATE, IT_TEMPLATE,
              FINANCE_TEMPLATE, HEALTHCARE_TEMPLATE]:
        register(t)


_auto_register()
