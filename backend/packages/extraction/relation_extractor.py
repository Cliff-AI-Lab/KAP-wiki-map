"""W4 关系抽取 — 独立模块（M22 #5）。

entity_extractor 在一次 LLM 调用里同时抽实体 + 关系是高效路径, 但当
chunk 已经有外部确定的实体集合时（如 ISS bypass 入口 + M22 #5 实体消歧后）,
仅抽关系会更稳更便宜。本模块提供 standalone API:

    extract_relations(content, entities, industry_code, project_id) → list[ExtractedRelation]

LLM 提议的关系**不直接落图**, 由 governance 4×6 矩阵审核（决策书 D12 人工兜底）。
"""

from __future__ import annotations

from typing import Any

from packages.common import get_logger
from packages.common.types import ExtractedEntity, ExtractedRelation
from packages.distillation.llm_client import acall_llm_json
from packages.ontology.base import get_current_l1, get_current_l2

log = get_logger("extraction.relation_extractor")


W4_REL_SYSTEM = """你是企业知识图谱关系抽取工程师。
任务：根据已确定的实体列表和文档片段, 抽取实体间关系, 严格按本体定义的允许关系类型输出。

约束：
1. relation_type_id 必须在「允许关系类型」内
2. source/target 必须在「已确定的实体」列表内（按 name 引用）
3. 关系的 source_types/target_types 必须符合 relation 定义
4. 给出 confidence (0-1) + evidence（原文 ≤30 字）
5. 严格 JSON 输出"""


W4_REL_USER = """## 已确定的实体（按 entity_id 引用，**严禁用 name**）
{entities}

## 允许关系类型
{relation_types}

## 文档片段
{content}

## 请输出 JSON（entity_id 必须完整原样复制，含前缀 ent_）：
{{
  "relations": [
    {{
      "source_entity_id": "entity_id（必须从上方实体列表的 [ent_xxx] 复制）",
      "target_entity_id": "entity_id",
      "relation_type_id": "关系类型 id",
      "confidence": 0.0-1.0,
      "evidence": "原文短句"
    }}
  ]
}}"""


def _format_entities(entities: list[ExtractedEntity], max_entities: int = 50) -> str:
    """格式化实体列表给 LLM, **id 在前**让模型直接复制 entity_id。

    重名实体（同 name 不同 entity_id）必须靠 entity_id 区分,
    M22 #9 修 codex review HIGH #2: 之前用 name 引用, dict[name] 会覆盖。
    """
    if not entities:
        return "（无）"
    return "\n".join(
        f"- [{e.entity_id}] {e.name} ({e.type_id})"
        for e in entities[:max_entities]
    )


def _format_relations(relations_list: list[Any]) -> str:
    if not relations_list:
        return "（无）"
    lines: list[str] = []
    for r in relations_list:
        constraint = ""
        if r.source_types and r.target_types:
            constraint = (f" [源: {','.join(r.source_types[:3])} | "
                          f"目标: {','.join(r.target_types[:3])}]")
        lines.append(f"- {r.type_id} ({r.type_name}){constraint}")
    return "\n".join(lines)


async def extract_relations(
    *,
    content: str,
    entities: list[ExtractedEntity],
    industry_code: str = "",
    project_id: str = "",
    content_chars_limit: int = 3000,
    max_entities_in_prompt: int = 50,
    max_relations_in_prompt: int = 100,
) -> list[ExtractedRelation]:
    """从给定实体集合中抽取关系（不抽新实体）。

    Args:
        content: 文档片段
        entities: 已确定的实体（来自上游 entity_extractor 或外部 KG）
        industry_code: 行业 code（查 L1 关系类型）
        project_id: 项目 id（查 L2 关系类型）

    Returns:
        list[ExtractedRelation] — LLM 失败或无候选时返回空
    """
    if not content.strip() or not entities:
        return []

    # 合并 L1 + L2 关系类型
    relations_list: list[Any] = []
    valid_rids: set[str] = set()
    relation_by_id: dict[str, Any] = {}
    l1 = get_current_l1(industry_code) if industry_code else None
    if l1:
        relations_list.extend(l1.relation_types)
    l2 = get_current_l2(project_id) if project_id else None
    if l2:
        relations_list.extend(l2.relation_types)
    for r in relations_list:
        valid_rids.add(r.type_id)
        relation_by_id[r.type_id] = r

    if not valid_rids:
        log.info("relation_extract_no_relation_types",
                 industry=industry_code, project=project_id)
        return []

    # M22 #9 修 codex HIGH #2: 用 entity_id 引用 (重名 name dict 会覆盖)
    eid_to_entity: dict[str, ExtractedEntity] = {e.entity_id: e for e in entities}

    user_prompt = W4_REL_USER.format(
        entities=_format_entities(entities, max_entities=max_entities_in_prompt),
        relation_types=_format_relations(relations_list),
        content=content[:content_chars_limit],
    )

    try:
        data = await acall_llm_json(W4_REL_SYSTEM, user_prompt)
    except Exception as e:
        log.warning("relation_extract_llm_failed", error=str(e))
        return []

    out: list[ExtractedRelation] = []
    # M22 #9: 兼容老 LLM 返回 source_name/target_name (回退到按 name 查, 但只有
    # 唯一同名匹配时才接受, 多个同名直接丢弃 — 不再静默挂错 entity_id)
    name_to_entities: dict[str, list[ExtractedEntity]] = {}
    for e in entities:
        name_to_entities.setdefault(e.name, []).append(e)

    # M22 #9 codex MED: 关系类型上限 (避免 L1+L2 关系大时 prompt 膨胀)
    if len(relations_list) > max_relations_in_prompt:
        relations_list = relations_list[:max_relations_in_prompt]

    for r in data.get("relations", []) or []:
        if not isinstance(r, dict):
            continue
        rel_id = (r.get("relation_type_id") or "").strip()
        if rel_id not in valid_rids:
            continue

        src_eid = (r.get("source_entity_id") or "").strip()
        tgt_eid = (r.get("target_entity_id") or "").strip()
        src = eid_to_entity.get(src_eid) if src_eid else None
        tgt = eid_to_entity.get(tgt_eid) if tgt_eid else None

        # 兼容旧 schema: 只在按 name 唯一匹配时接受, 否则跳过 (避免重名误连)
        if src is None and "source_name" in r:
            cands = name_to_entities.get((r.get("source_name") or "").strip(), [])
            if len(cands) == 1:
                src = cands[0]
        if tgt is None and "target_name" in r:
            cands = name_to_entities.get((r.get("target_name") or "").strip(), [])
            if len(cands) == 1:
                tgt = cands[0]

        if not src or not tgt:
            log.debug("relation_dropped_unknown_or_ambiguous",
                      rel_id=rel_id, src_eid=src_eid, tgt_eid=tgt_eid)
            continue

        rel_meta = relation_by_id.get(rel_id)
        if rel_meta and rel_meta.source_types \
                and src.type_id not in rel_meta.source_types:
            continue
        if rel_meta and rel_meta.target_types \
                and tgt.type_id not in rel_meta.target_types:
            continue

        try:
            conf = max(0.0, min(1.0, float(r.get("confidence", 0.5))))
        except (TypeError, ValueError):
            conf = 0.5

        out.append(ExtractedRelation(
            source_entity_id=src.entity_id,
            target_entity_id=tgt.entity_id,
            relation_type_id=rel_id,
            confidence=conf,
            evidence=str(r.get("evidence", ""))[:120],
        ))

    log.info("relation_extract_done",
             entities=len(entities), relations=len(out))
    return out
