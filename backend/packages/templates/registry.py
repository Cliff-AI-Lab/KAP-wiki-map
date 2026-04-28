"""行业模板注册表 — 管理所有预置行业的四级知识体系。"""

from __future__ import annotations

from pydantic import BaseModel

from packages.common.types import KnowledgeDomain


class TaxonomyNode(BaseModel):
    """知识体系节点（支持四级嵌套）。"""
    id: str
    name: str
    level: int
    description: str = ""
    children: list[TaxonomyNode] = []


class IndustryTemplate(BaseModel):
    """行业模板定义。"""
    code: str
    name: str
    name_en: str
    icon: str
    description: str
    taxonomy: list[TaxonomyNode]


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
