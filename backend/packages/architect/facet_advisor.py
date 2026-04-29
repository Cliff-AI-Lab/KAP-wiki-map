"""Facet 提议器（PRD F1.4 lite）— LLM 自动归纳元数据 schema。

设计原则（feedback memory · AI native + 轻量化）：
- 函数式实现，单文件
- 复用 M1 packages/templates/registry.FacetField/FacetSchema 数据模型
- 复用 M2 块① ArchitectAgent 模式（LLM 失败静默降级）
- 提议结果写到 TaxonomyDraft.facets dict（key=doc_type）

调用链：
  block ① 在 propose_taxonomy 之后 → propose_facets_for_doc_type → 挂到 draft.facets
  exporter 把 draft.facets 转 IndustryTemplate.facets
"""

from __future__ import annotations

from packages.architect.prompts import (
    FACET_PROPOSE_SYSTEM,
    FACET_PROPOSE_USER,
)
from packages.common import get_logger
from packages.distillation.llm_client import acall_llm_json
from packages.ontology.base import get_current_l1
from packages.templates.registry import FacetField, FacetSchema

log = get_logger("architect.facet_advisor")


# 合法字段类型枚举
_VALID_FIELD_TYPES = {"str", "int", "numeric", "date", "enum", "reference"}
_VALID_PRIMARY_ROLES = {"DG", "SME", "SEC", "AIOps"}


def _format_l1_types(industry_code: str) -> str:
    """组装 L1 实体类型列表（供 LLM reference 字段引用）。"""
    l1 = get_current_l1(industry_code)
    if not l1:
        return "（L1 本体未注册）"
    return "\n".join(
        f"- {et.type_id} ({et.type_name})"
        for et in l1.entity_types
    )


_INDUSTRY_NAME_MAP = {
    "manufacturing": "制造业", "energy": "能源",
    "finance": "金融", "healthcare": "医疗", "it": "IT",
}


async def propose_facets_for_doc_type(
    industry_code: str,
    doc_type: str,
    sample_texts: list[str],
) -> FacetSchema | None:
    """LLM 提议某文档类型的 Facet schema。

    Args:
        industry_code: 客户行业 code（用于查 L1 引用）
        doc_type: 文档类型 code（如 equipment_fault / sop）
        sample_texts: 该类型文档的样本片段（≥3 份效果最好）

    Returns:
        FacetSchema 或 None（LLM 失败 / 返回非法）
    """
    if not doc_type or not sample_texts:
        return None

    industry_name = _INDUSTRY_NAME_MAP.get(industry_code, industry_code)
    samples_text = "\n".join(f"- {s[:200]}" for s in sample_texts[:8])

    user_prompt = FACET_PROPOSE_USER.format(
        industry_code=industry_code,
        industry_name=industry_name,
        doc_type=doc_type,
        sample_texts=samples_text,
        l1_types=_format_l1_types(industry_code),
    )

    try:
        data = await acall_llm_json(FACET_PROPOSE_SYSTEM, user_prompt)
    except Exception as e:
        log.warning("facet_propose_llm_failed", doc_type=doc_type, error=str(e))
        return None

    return _parse_facet_response(data, doc_type)


def _parse_facet_response(data: dict, expected_doc_type: str) -> FacetSchema | None:
    """从 LLM JSON 解析 FacetSchema（容错：非法字段 type 默认 str；漏 key 跳过）。"""
    if not isinstance(data, dict):
        return None

    raw_fields = data.get("fields", [])
    if not isinstance(raw_fields, list) or not raw_fields:
        return None

    parsed_fields: list[FacetField] = []
    for f in raw_fields:
        if not isinstance(f, dict):
            continue
        key = (f.get("key") or "").strip()
        name = (f.get("name") or "").strip()
        if not key or not name:
            continue
        field_type = (f.get("type") or "str").strip()
        if field_type not in _VALID_FIELD_TYPES:
            field_type = "str"

        try:
            parsed_fields.append(FacetField(
                key=key,
                name=name,
                type=field_type,  # type: ignore[arg-type]
                required=bool(f.get("required", False)),
                sensitive=bool(f.get("sensitive", False)),
                description=str(f.get("description", ""))[:200],
                unit=str(f.get("unit", ""))[:32],
                enum_values=[str(v)[:40] for v in (f.get("enum_values") or [])
                             if isinstance(v, (str, int, float))][:20],
                ref_type=str(f.get("ref_type", ""))[:64],
            ))
        except Exception as e:
            log.warning("facet_field_parse_failed", field=key, error=str(e))
            continue

    if not parsed_fields:
        return None

    primary_role = (data.get("primary_role") or "SME").strip()
    if primary_role not in _VALID_PRIMARY_ROLES:
        primary_role = "SME"

    doc_type_returned = (data.get("doc_type") or expected_doc_type).strip()

    return FacetSchema(
        doc_type=doc_type_returned,
        name=str(data.get("name", doc_type_returned))[:80],
        description=str(data.get("description", ""))[:200],
        primary_role=primary_role,
        fields=parsed_fields,
    )


async def propose_facets_for_taxonomy(
    industry_code: str,
    doc_types: list[str],
    sample_texts_by_type: dict[str, list[str]],
) -> dict[str, FacetSchema]:
    """批量为多个 doc_type 提议 facet（顺序调，避免 LLM 并发限流）。

    Args:
        industry_code: 客户行业
        doc_types: 待提议的文档类型列表
        sample_texts_by_type: doc_type → 样本片段列表

    Returns:
        doc_type → FacetSchema 映射；失败的 doc_type 不在结果中
    """
    out: dict[str, FacetSchema] = {}
    for dt in doc_types:
        samples = sample_texts_by_type.get(dt, [])
        if not samples:
            log.info("facet_propose_no_samples_skipped", doc_type=dt)
            continue
        schema = await propose_facets_for_doc_type(industry_code, dt, samples)
        if schema is not None:
            out[dt] = schema
            log.info("facet_propose_done", doc_type=dt,
                     field_count=len(schema.fields))
    return out
