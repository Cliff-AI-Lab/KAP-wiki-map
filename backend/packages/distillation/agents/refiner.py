"""Refiner Agent — 语义提炼。

将通过质量审核的文档转化为结构化知识资产：摘要、目录、关键词、实体关系。
"""

from __future__ import annotations

import re

from packages.common import get_logger
from packages.common.types import (
    CatalogSection,
    EntityRelation,
    LibrarianResult,
    MentionedEntity,
    RawDocument,
    RefinedResult,
)
from packages.distillation.llm_client import call_llm_json
from packages.distillation.prompts.templates import REFINER_SYSTEM, REFINER_USER

log = get_logger("agent.refiner")

# 从 Skills 动态生成知识域列表（只加载一次）
_domain_list_cache: str | None = None


def _get_domain_list() -> str:
    """获取当前组织 Skills 定义的知识域列表文本。"""
    global _domain_list_cache
    if _domain_list_cache is not None:
        return _domain_list_cache

    try:
        from packages.retrieval.skills_loader import load_skills
        skills = load_skills()
        _domain_list_cache = skills.to_refiner_domain_list()
        if _domain_list_cache:
            log.info("refiner_domain_list_from_skills", company=skills.company_alias)
            return _domain_list_cache
    except Exception as e:
        log.warning("refiner_skills_load_failed", error=str(e))

    # fallback: 从 taxonomy 生成
    from packages.retrieval.taxonomy import get_default_taxonomy
    lines = []
    for d in get_default_taxonomy():
        prefix = "  - " if d.parent_id else "- "
        lines.append(f"{prefix}{d.domain_id}: {d.name} — {d.description[:80]}")
    _domain_list_cache = "\n".join(lines)
    return _domain_list_cache


def _clean_domain_id(raw: str) -> str:
    """清洗 LLM 返回的 domain_id，提取纯净的域路径。

    LLM 可能返回:
      - 正确: "tech/architecture"
      - 带标注: "L1 [tech]: 技术文档 — ..."
      - 多级拼接: "L1 [product]/L2 [product/roadmap]"
      - 带引号: "'L1 [quality]'"
    统一提取方括号中最具体（最长）的 domain_id。
    """
    if not raw:
        return ""
    raw = raw.strip().strip("'\"")

    # 提取所有 [xxx] 中的内容
    brackets = re.findall(r"\[([^\]]+)\]", raw)
    if brackets:
        # 取最长的（最具体的子域），如 [product] 和 [product/roadmap] 取后者
        return max(brackets, key=len)

    # 无方括号：可能是 "L1/product" 或 "tech/architecture" 格式
    # 去掉 "L1 ", "L2 " 等前缀
    cleaned = re.sub(r"^L\d+\s*", "", raw)
    # 去掉 "L1/" 等前缀（如 "L1/product" → "product"）
    cleaned = re.sub(r"^L\d+/", "", cleaned)
    # 取冒号前的部分
    if ":" in cleaned:
        cleaned = cleaned.split(":")[0].strip()
    # 取逗号前的部分
    if "," in cleaned:
        cleaned = cleaned.split(",")[0].strip()
    # 去掉开头的斜杠
    cleaned = cleaned.lstrip("/")

    return cleaned


def _validate_and_fix_relations(
    entities: list[MentionedEntity],
    relations: list[EntityRelation],
) -> list[EntityRelation]:
    """V8: 确保关系端点都在实体列表中，过滤无效关系。

    对齐核心理念：图谱沿体系分支生长，关系质量决定图谱可视化效果。
    """
    entity_names = {e.name for e in entities}
    valid = []
    for r in relations:
        src = _fuzzy_match_entity(r.source, entity_names)
        tgt = _fuzzy_match_entity(r.target, entity_names)
        if src and tgt and src != tgt:
            valid.append(EntityRelation(source=src, target=tgt, relation=r.relation))
    return valid


def _fuzzy_match_entity(name: str, entity_names: set[str]) -> str | None:
    """模糊匹配：精确匹配 > 包含匹配 > None。"""
    name = name.strip()
    if name in entity_names:
        return name
    # 尝试包含匹配（短名包含于长名，或长名包含短名）
    for ent in entity_names:
        if name in ent or ent in name:
            return ent
    return None


def _build_index_text(doc_title: str, summary: str, catalog: list[CatalogSection], keywords: list[str]) -> str:
    """从摘要+目录+关键词自动拼接 index_text（当 LLM 未生成时的 fallback）。"""
    parts = [f"文档《{doc_title}》"]
    if summary:
        parts.append(summary)
    for sec in catalog:
        line = f"{sec.title}：{sec.brief}"
        if sec.key_terms:
            line += f"（{', '.join(sec.key_terms)}）"
        parts.append(line)
    if keywords:
        parts.append(f"关键词：{'、'.join(keywords)}")
    return " ".join(parts)


def run_refiner(
    doc: RawDocument,
    librarian_result: LibrarianResult,
    domain_list_text: str = "",
) -> RefinedResult:
    """对 KEEP 的文档运行 Refiner Agent，提炼结构化知识。

    Args:
        domain_list_text: 项目级知识域列表文本。为空时 fallback 到全局。
    """
    log.info("refiner_start", doc_id=doc.doc_id)

    effective_domain_list = domain_list_text or _get_domain_list()

    user_prompt = REFINER_USER.format(
        title=doc.title,
        doc_type=librarian_result.doc_type.value,
        full_content=doc.content[:8000],
        domain_list=effective_domain_list,
    )

    data = call_llm_json(REFINER_SYSTEM, user_prompt)

    # 解析 catalog — 兼容旧格式（plain dict）和新格式（含 key_terms）
    catalog_raw = data.get("catalog", [])
    catalog = []
    for item in catalog_raw:
        if isinstance(item, dict):
            catalog.append(CatalogSection(
                level=item.get("level", 1),
                title=item.get("title", ""),
                brief=item.get("brief", ""),
                key_terms=item.get("key_terms", []),
            ))

    keywords = data.get("keywords", [])
    summary = data.get("summary", "")

    # index_text: 优先用 LLM 生成的，否则自动拼接
    index_text = data.get("index_text", "")
    if not index_text:
        index_text = _build_index_text(doc.title, summary, catalog, keywords)

    # 知识域匹配 + 文档描述（给 LLM 路由用的）
    domain_id = _clean_domain_id(data.get("domain_id", ""))
    doc_description = data.get("doc_description", "")
    key_elements = data.get("key_elements", [])

    if not doc_description:
        # fallback: 从 summary 生成
        doc_description = f"本文档《{doc.title}》{summary[:200]}"

    # 解析实体（V8: 兼容新增的8种类型）
    raw_entities = [MentionedEntity(**e) for e in data.get("entities", [])]
    raw_relations = [EntityRelation(**r) for r in data.get("relations", [])]

    # V8: 后置校验 — 过滤无效关系（source/target 必须在 entities 中）
    validated_relations = _validate_and_fix_relations(raw_entities, raw_relations)

    if len(validated_relations) < len(raw_relations):
        log.info(
            "refiner_relations_filtered",
            doc_id=doc.doc_id,
            raw=len(raw_relations),
            valid=len(validated_relations),
        )

    result = RefinedResult(
        summary=summary,
        catalog=catalog,
        keywords=keywords,
        entities=raw_entities,
        relations=validated_relations,
        index_text=index_text,
        domain_id=domain_id,
        doc_description=doc_description,
        key_elements=key_elements,
    )

    log.info(
        "refiner_done",
        doc_id=doc.doc_id,
        domain_id=result.domain_id,
        summary_len=len(result.summary),
        catalog_count=len(result.catalog),
        keyword_count=len(result.keywords),
        entity_count=len(result.entities),
        relation_count=len(result.relations),
    )
    return result
