"""Refiner Agent — 语义提炼。

将通过质量审核的文档转化为结构化知识资产：摘要、目录、关键词、实体关系。

M0-tech-debt 改造（坑 4b + 额外坑 B + 额外坑 E）：

- ``_get_domain_list`` 由全局单例缓存改为按 ``(org_id, project_id)`` 维度缓存
  → 修复多租户污染（决策书 §1.4 单实例多业务单元逻辑隔离）
- ``_clean_domain_id`` 迁移至 ``packages.distillation.domain_inference`` 共享模块
  → 与 ``_mock_infer_domain_id`` 共用统一净化逻辑
- 兜底域名从 ``"regulation"`` 改为 ``ROUTING_PENDING_DOMAIN_ID``
  → 未识别文档进入 W2 工位 DG 主审队列（决策书 §5.2）
"""

from __future__ import annotations

from functools import lru_cache

from packages.common import get_logger
from packages.common.types import (
    CatalogSection,
    EntityRelation,
    LibrarianResult,
    MentionedEntity,
    RawDocument,
    RefinedResult,
)
from packages.distillation.domain_inference import (
    ROUTING_PENDING_DOMAIN_ID,
    clean_domain_id as _clean_domain_id,
)
from packages.distillation.llm_client import call_llm_json
from packages.distillation.prompts.templates import REFINER_SYSTEM, REFINER_USER

log = get_logger("agent.refiner")


@lru_cache(maxsize=128)
def _get_domain_list(org_id: str = "default", project_id: str = "default") -> str:
    """按 (org_id, project_id) 维度获取 Skills 定义的知识域列表文本。

    M0-tech-debt 修复：原 V15 用模块级单例缓存（``_domain_list_cache``），
    多租户场景下第一个加载的 Skills 永久污染所有后续请求。改为 lru_cache
    以 (org_id, project_id) 为键。

    Args:
        org_id: 组织 ID，对应 ``RawDocument.org_id``
        project_id: 项目 ID（暂用 "default"，待 M1 项目维度扩展）

    Returns:
        知识域列表文本（fallback 到 taxonomy 时不为空）。

    Notes:
        - 缓存大小 128 项足够覆盖中等规模多租户场景
        - 配置变更后调用 ``_get_domain_list.cache_clear()`` 强制重读
    """
    try:
        from packages.retrieval.skills_loader import load_skills
        # 注：skills_loader 当前不感知 (org_id, project_id)，是后续扩展位
        skills = load_skills()
        text = skills.to_refiner_domain_list()
        if text:
            log.info(
                "refiner_domain_list_from_skills",
                org_id=org_id,
                project_id=project_id,
                company=skills.company_alias,
            )
            return text
    except Exception as e:  # noqa: BLE001 — Skills 加载失败不应阻塞 Refiner
        log.warning(
            "refiner_skills_load_failed",
            org_id=org_id,
            project_id=project_id,
            error=str(e),
        )

    # fallback: 从 taxonomy 生成
    from packages.retrieval.taxonomy import get_default_taxonomy
    lines = []
    for d in get_default_taxonomy():
        prefix = "  - " if d.parent_id else "- "
        lines.append(f"{prefix}{d.domain_id}: {d.name} — {d.description[:80]}")
    return "\n".join(lines)


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
    *,
    project_id: str = "default",
) -> RefinedResult:
    """对 KEEP 的文档运行 Refiner Agent，提炼结构化知识。

    Args:
        doc: 待精炼文档（含 ``org_id`` 用于多租户路由）
        librarian_result: Librarian 阶段产出
        domain_list_text: 项目级知识域列表文本。为空时按 ``doc.org_id`` + ``project_id`` 加载
        project_id: 项目 ID（M1 扩展位，M0 保持 "default"）
    """
    log.info("refiner_start", doc_id=doc.doc_id, org_id=doc.org_id, project_id=project_id)

    effective_domain_list = domain_list_text or _get_domain_list(
        org_id=doc.org_id,
        project_id=project_id,
    )

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
    # 兜底改 routing_pending（M0-tech-debt 坑 4b）：未识别 → 进 W2 DG 主审队列
    domain_id = _clean_domain_id(data.get("domain_id", "")) or ROUTING_PENDING_DOMAIN_ID
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
