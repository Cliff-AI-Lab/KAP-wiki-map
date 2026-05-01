"""W4 LLM 实体 + 关系抽取（决策书 §5.2 W4 工位 lite）。

设计原则（feedback memory · AI native + 轻量化）：
- 函数式实现，单文件
- 提示词强制约束实体 type_id 在 L1+L2 注册集合内（防 LLM 幻觉）
- 关系约束 source_type/target_type 必须在 OntologyRelationType 定义域内
- 敏感实体识别：复用 packages/sensitive NER（人名/工艺参数/客户名）
- LLM 失败静默降级返回空 ExtractionResult（不阻断 pipeline）
- 不接入主 pipeline（M2 #4 块① 已经有 librarian.mentioned_entities，本批是新增可选 W4 步骤）

W4 后置：M1 governance W4 SME 必审 hook 已在；本批输出可直接喂给 hook。
"""

from __future__ import annotations

import hashlib
from typing import Any

from packages.common import get_logger
from packages.common.types import (
    ExtractedEntity,
    ExtractedRelation,
    ExtractionResult,
)
from packages.distillation.llm_client import acall_llm_json
from packages.ontology.base import get_current_l1, get_current_l2
from packages.sensitive.ner import detect_sensitive_spans

log = get_logger("extraction.entity_extractor")


# ════════════════════════════════════════════════════════════════════════
#  Prompt
# ════════════════════════════════════════════════════════════════════════

W4_EXTRACT_SYSTEM = """你是一名企业知识图谱构建工程师。

任务：从给定文档抽取**实体**和**实体间关系**，严格按本体约束输出。

约束：
1. 实体 type_id 必须在「允许实体类型」列表内（不在则不抽这个实体）
2. 关系 relation_type_id 必须在「允许关系类型」列表内
3. 关系的 source/target 实体类型必须符合该 relation 的 source_types/target_types
4. 每个实体给出 confidence (0-1)
5. 给出 evidence（原文短句引用，≤30 字）
6. 实体属性（properties）只填确定的，不确定的省略

严格按 JSON 格式输出。"""

W4_EXTRACT_USER = """## 允许实体类型
{entity_types}

## 允许关系类型
{relation_types}

## 文档片段
{content}

## 请输出 JSON：
{{
  "entities": [
    {{
      "name": "实体名",
      "type_id": "实体类型 id",
      "confidence": 0.0-1.0,
      "properties": {{}},
      "evidence": "原文短句"
    }}
  ],
  "relations": [
    {{
      "source_name": "源实体名（必须在 entities 中）",
      "target_name": "目标实体名",
      "relation_type_id": "关系类型 id",
      "confidence": 0.0-1.0,
      "evidence": "原文短句"
    }}
  ]
}}"""


# ════════════════════════════════════════════════════════════════════════
#  辅助
# ════════════════════════════════════════════════════════════════════════


def _stable_entity_id(doc_id: str, name: str, type_id: str) -> str:
    """同一文档内同名同类型实体共用一个 stable id。"""
    h = hashlib.sha256(f"{doc_id}|{name}|{type_id}".encode("utf-8")).hexdigest()[:12]
    return f"ent_{h}"


def _format_types(types_list: list[Any], max_examples: int = 3) -> str:
    if not types_list:
        return "（无）"
    lines: list[str] = []
    for t in types_list:
        examples = ""
        if hasattr(t, "examples") and t.examples:
            examples = f"，例：{', '.join(t.examples[:max_examples])}"
        lines.append(f"- {t.type_id} ({t.type_name}){examples}")
    return "\n".join(lines)


def _format_relations(relations_list: list[Any]) -> str:
    if not relations_list:
        return "（无）"
    lines: list[str] = []
    for r in relations_list:
        constraint = ""
        if r.source_types and r.target_types:
            constraint = (
                f" [源: {','.join(r.source_types[:3])} | "
                f"目标: {','.join(r.target_types[:3])}]"
            )
        lines.append(f"- {r.type_id} ({r.type_name}){constraint}")
    return "\n".join(lines)


def _collect_ontology_types(industry_code: str, project_id: str):
    """合并 L1 + L2 的 entity / relation 类型。"""
    entity_types: list[Any] = []
    relation_types: list[Any] = []
    valid_entity_ids: set[str] = set()
    valid_relation_ids: set[str] = set()
    relation_by_id: dict[str, Any] = {}

    l1 = get_current_l1(industry_code) if industry_code else None
    if l1:
        entity_types.extend(l1.entity_types)
        relation_types.extend(l1.relation_types)

    l2 = get_current_l2(project_id) if project_id else None
    if l2:
        entity_types.extend(l2.entity_types)
        relation_types.extend(l2.relation_types)

    for et in entity_types:
        valid_entity_ids.add(et.type_id)
    for rt in relation_types:
        valid_relation_ids.add(rt.type_id)
        relation_by_id[rt.type_id] = rt

    return (
        entity_types, relation_types,
        valid_entity_ids, valid_relation_ids, relation_by_id,
    )


# ════════════════════════════════════════════════════════════════════════
#  入口
# ════════════════════════════════════════════════════════════════════════


async def extract_entities_and_relations(
    *,
    doc_id: str,
    content: str,
    industry_code: str,
    project_id: str = "",
    content_chars_limit: int = 3000,
) -> ExtractionResult:
    """从文档抽取实体 + 关系（决策书 §5.2 W4 工位）。

    Args:
        doc_id: 文档 id（用于实体 stable id）
        content: 文档原文
        industry_code: 行业 code（查 L1）
        project_id: 项目 id（查 L2）
        content_chars_limit: prompt 截断长度（默认 3000，防 LLM 上下文超）

    Returns:
        ExtractionResult — LLM 失败时返回空（含 error 字段）
    """
    if not content or not content.strip():
        return ExtractionResult(doc_id=doc_id)

    (
        entity_types_list, relation_types_list,
        valid_eids, valid_rids, relation_by_id,
    ) = _collect_ontology_types(industry_code, project_id)

    if not valid_eids:
        log.warning("w4_extract_no_ontology",
                    industry=industry_code, project=project_id)
        return ExtractionResult(
            doc_id=doc_id,
            error=f"未找到 L1 (industry={industry_code}) 或 L2 (project={project_id}) 本体",
        )

    user_prompt = W4_EXTRACT_USER.format(
        entity_types=_format_types(entity_types_list),
        relation_types=_format_relations(relation_types_list),
        content=content[:content_chars_limit],
    )

    try:
        data = await acall_llm_json(W4_EXTRACT_SYSTEM, user_prompt)
    except Exception as e:
        log.warning("w4_extract_llm_failed", doc_id=doc_id, error=str(e))
        err_result = ExtractionResult(
            doc_id=doc_id, error=f"LLM 调用失败: {e}",
        )
        # M19 #2 · 失败也记录诊断
        try:
            from packages.observability.extraction_quality import (
                record_extraction_metric,
            )
            record_extraction_metric(
                result=err_result, industry_code=industry_code,
                project_id=project_id,
                content_chars=min(len(content), content_chars_limit),
            )
        except Exception:
            pass
        return err_result

    # ── 解析实体 ──
    entities: list[ExtractedEntity] = []
    name_to_eid: dict[str, str] = {}      # 实体名 → stable id（关系引用用）
    sensitive_count = 0

    sensitive_spans = detect_sensitive_spans(content[:content_chars_limit])
    sensitive_text_set = {s.text for s in sensitive_spans}

    raw_entities = data.get("entities", []) or []
    for e in raw_entities:
        if not isinstance(e, dict):
            continue
        name = (e.get("name") or "").strip()
        type_id = (e.get("type_id") or "").strip()
        if not name or type_id not in valid_eids:
            continue
        try:
            confidence = max(0.0, min(1.0, float(e.get("confidence", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5

        eid = _stable_entity_id(doc_id, name, type_id)
        name_to_eid[name] = eid

        is_sensitive = name in sensitive_text_set or any(
            s in name for s in sensitive_text_set
        )
        if is_sensitive:
            sensitive_count += 1

        entities.append(ExtractedEntity(
            entity_id=eid,
            name=name[:100],
            type_id=type_id,
            confidence=confidence,
            is_sensitive=is_sensitive,
            properties=dict(e.get("properties") or {}),
            evidence=str(e.get("evidence", ""))[:120],
        ))

    # ── 解析关系（必须在已抽取实体集合内 + 满足 source/target 类型约束）──
    relations: list[ExtractedRelation] = []
    raw_relations = data.get("relations", []) or []
    for r in raw_relations:
        if not isinstance(r, dict):
            continue
        src_name = (r.get("source_name") or "").strip()
        tgt_name = (r.get("target_name") or "").strip()
        rel_id = (r.get("relation_type_id") or "").strip()
        if rel_id not in valid_rids:
            continue
        src_eid = name_to_eid.get(src_name)
        tgt_eid = name_to_eid.get(tgt_name)
        if not src_eid or not tgt_eid:
            continue

        # 校验定义域 / 值域（如本体定义了 source_types / target_types 列表）
        rel_meta = relation_by_id.get(rel_id)
        if rel_meta and rel_meta.source_types:
            src_entity = next((x for x in entities if x.entity_id == src_eid), None)
            if src_entity and src_entity.type_id not in rel_meta.source_types:
                log.info("w4_relation_source_type_mismatch",
                         relation=rel_id, src_type=src_entity.type_id)
                continue
        if rel_meta and rel_meta.target_types:
            tgt_entity = next((x for x in entities if x.entity_id == tgt_eid), None)
            if tgt_entity and tgt_entity.type_id not in rel_meta.target_types:
                continue

        try:
            r_conf = max(0.0, min(1.0, float(r.get("confidence", 0.5))))
        except (TypeError, ValueError):
            r_conf = 0.5

        relations.append(ExtractedRelation(
            source_entity_id=src_eid,
            target_entity_id=tgt_eid,
            relation_type_id=rel_id,
            confidence=r_conf,
            evidence=str(r.get("evidence", ""))[:120],
        ))

    # 整体置信度 = 实体平均（无实体时 0）
    overall = (
        sum(e.confidence for e in entities) / len(entities)
        if entities else 0.0
    )

    log.info(
        "w4_extract_done", doc_id=doc_id,
        entities=len(entities), relations=len(relations),
        sensitive=sensitive_count, overall=round(overall, 3),
    )

    result = ExtractionResult(
        doc_id=doc_id,
        entities=entities,
        relations=relations,
        overall_confidence=overall,
        sensitive_entity_count=sensitive_count,
    )

    # M19 #2 · W4 链式自动评分（规则化，不调 LLM）
    try:
        from packages.observability.extraction_quality import (
            record_extraction_metric,
        )
        record_extraction_metric(
            result=result,
            industry_code=industry_code,
            project_id=project_id,
            content_chars=min(len(content), content_chars_limit),
        )
    except Exception as e:  # 兜底：诊断失败不影响抽取流程
        log.warning("w4_quality_record_failed", doc_id=doc_id, error=str(e))

    return result
