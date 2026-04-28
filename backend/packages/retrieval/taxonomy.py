"""知识体系分类框架 — 从组织 Skills 文件动态加载。

优先从 skills/ 目录的 YAML 文件加载组织定义的知识域，
若无 Skills 文件则回退到内置的通用企业模板。
"""

from __future__ import annotations

from packages.common import get_logger
from packages.common.types import KnowledgeDomain

log = get_logger("retrieval.taxonomy")

# ── 内置通用模板（fallback） ───────────────────────────

_GENERIC_TAXONOMY: list[KnowledgeDomain] = [
    KnowledgeDomain(domain_id="product", name="产品管理",
                    description="产品需求文档(PRD)、产品路线图、用户故事、原型说明、功能规格、竞品分析。"),
    KnowledgeDomain(domain_id="tech", name="技术文档",
                    description="系统架构设计、API接口文档、部署运维手册、技术方案、选型讨论。"),
    KnowledgeDomain(domain_id="project", name="项目管理",
                    description="项目计划、里程碑、Sprint评审、会议纪要、OKR目标、进度跟踪。"),
    KnowledgeDomain(domain_id="quality", name="测试与质量",
                    description="测试计划、测试报告、Bug跟踪清单、验收标准、质量指标。"),
    KnowledgeDomain(domain_id="customer", name="客户与市场",
                    description="客户需求、客户反馈、验收意见、销售报告、市场分析、竞品情报。"),
    KnowledgeDomain(domain_id="regulation", name="制度规范",
                    description="企业规章制度、管理办法、报销制度、人事制度。"),
]


def _load_from_skills() -> list[KnowledgeDomain] | None:
    """尝试从 Skills YAML 加载知识域，失败则返回 None。"""
    try:
        from packages.retrieval.skills_loader import load_skills
        skills = load_skills()
        taxonomy = skills.to_taxonomy()
        if taxonomy:
            log.info("taxonomy_from_skills", company=skills.company_alias, count=len(taxonomy))
            return taxonomy
    except Exception as e:
        log.warning("taxonomy_skills_load_failed", error=str(e))
    return None


# ── 对外接口 ──────────────────────────────────────────

_cached_taxonomy: list[KnowledgeDomain] | None = None


def get_default_taxonomy() -> list[KnowledgeDomain]:
    """获取默认知识域列表。

    V6: 不再从 Skills YAML 加载。知识体系由项目的行业模板驱动。
    此函数仅作为 fallback（向后兼容），实际知识域在项目创建时写入 DomainStore。
    """
    global _cached_taxonomy
    if _cached_taxonomy is not None:
        return _cached_taxonomy

    _cached_taxonomy = _GENERIC_TAXONOMY
    return _cached_taxonomy


# 保持向后兼容
DEFAULT_TAXONOMY = get_default_taxonomy()


def get_taxonomy_dict() -> dict[str, KnowledgeDomain]:
    """返回 domain_id -> KnowledgeDomain 的字典。"""
    return {d.domain_id: d for d in get_default_taxonomy()}


def get_domain_name_map() -> dict[str, str]:
    """返回 domain_id -> 中文名 的映射。"""
    return {d.domain_id: d.name for d in get_default_taxonomy()}


def get_domain_description_map() -> dict[str, str]:
    """返回 domain_id -> description 的映射。"""
    return {d.domain_id: d.description for d in get_default_taxonomy()}
