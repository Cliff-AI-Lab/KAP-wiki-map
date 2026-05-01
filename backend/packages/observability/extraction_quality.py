"""W4 抽取质量诊断（M19 #2）。

每次 extract_entities_and_relations 完成后立即跑一次轻量规则化评分（不调 LLM，
开销可忽略）。4 维：

1. entity_density：实体密度（每千字符抽实体数；对比阈值评分）
2. relation_validity：关系有效率（实体已绑定 + 类型符合定义域 / 值域）
3. confidence_avg：实体平均置信度
4. sensitive_handled：是否检出敏感词（命中→高分，因为 W3 脱敏要识别它们）

LLM 6 维 wiki_quality 走 wiki_compiler；这里 W4 走规则化诊断。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from packages.common import get_logger

if TYPE_CHECKING:
    from packages.common.types import ExtractionResult

log = get_logger("observability.extraction_quality")


# 维度权重（合计 1.0）
_DIM_WEIGHTS = {
    "entity_density": 0.25,
    "relation_validity": 0.30,
    "confidence_avg": 0.30,
    "sensitive_handled": 0.15,
}

_QUALITY_ALERT_THRESHOLD = 0.5
# 实体密度参考：每 1000 字符 5-15 个实体算正常
_DENSITY_OPTIMAL_MIN = 5.0
_DENSITY_OPTIMAL_MAX = 15.0


class ExtractionMetric(BaseModel):
    """单文档 W4 抽取诊断（M19 #2）。"""
    doc_id: str
    project_id: str = ""
    industry_code: str = ""
    content_chars: int = 0
    entity_count: int = 0
    relation_count: int = 0
    sensitive_count: int = 0
    entity_density_per_kchars: float = 0.0
    confidence_avg: float = 0.0
    error: str = ""
    # 4 维评分（每维 0-1）
    score_entity_density: float = 0.0
    score_relation_validity: float = 0.0
    score_confidence_avg: float = 0.0
    score_sensitive_handled: float = 0.0
    overall: float = 0.0
    quality_alert: bool = False
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))


_metrics: list[ExtractionMetric] = []
_METRICS_MAX = 5000


def reset_extraction_quality_for_test() -> None:
    _metrics.clear()


def _score_density(density: float) -> float:
    """实体密度评分：5-15 区间为 1.0；过低线性降；过高小幅惩罚。"""
    if density <= 0:
        return 0.0
    if _DENSITY_OPTIMAL_MIN <= density <= _DENSITY_OPTIMAL_MAX:
        return 1.0
    if density < _DENSITY_OPTIMAL_MIN:
        return density / _DENSITY_OPTIMAL_MIN
    # 超过最大值：每超 5/k 字符扣 0.2，保留下限 0.4
    excess = (density - _DENSITY_OPTIMAL_MAX) / 5.0
    return max(0.4, 1.0 - excess * 0.2)


def _score_relation_validity(
    entity_count: int, relation_count: int,
) -> float:
    """关系有效率：抽到的关系都通过了类型校验（解析阶段已过滤）。

    无实体时为 0；有实体但无关系时为 0.5；relation/entity > 0.3 视为充分。
    """
    if entity_count == 0:
        return 0.0
    if relation_count == 0:
        return 0.5
    ratio = relation_count / entity_count
    if ratio >= 0.3:
        return 1.0
    return 0.5 + (ratio / 0.3) * 0.5


def _score_sensitive(content_chars: int, sensitive_count: int) -> float:
    """敏感词处理：检出 ≥ 1 → 1.0；无敏感词的常规文档 → 0.8（不确定是否真无）。

    注：高分代表"系统正常发现并标注敏感词"，不代表文档敏感程度。
    """
    if sensitive_count > 0:
        return 1.0
    # 短文档无敏感词正常；长文档无敏感词略可疑
    if content_chars < 500:
        return 0.9
    return 0.8


def record_extraction_metric(
    *,
    result: "ExtractionResult",
    industry_code: str = "",
    project_id: str = "",
    content_chars: int = 0,
) -> ExtractionMetric:
    """W4 抽取完成后记录诊断（在 entity_extractor 入口尾部调用）。

    LLM 失败时 result.error 非空，直接记录为低分但不阻塞。
    """
    entity_count = len(result.entities) if result.entities else 0
    relation_count = len(result.relations) if result.relations else 0
    sensitive_count = sum(1 for e in (result.entities or []) if e.is_sensitive)
    confidence_avg = (
        sum(e.confidence for e in result.entities) / entity_count
        if entity_count else 0.0
    )
    density = (
        entity_count / (content_chars / 1000.0)
        if content_chars > 0 else 0.0
    )

    metric = ExtractionMetric(
        doc_id=result.doc_id,
        project_id=project_id,
        industry_code=industry_code,
        content_chars=content_chars,
        entity_count=entity_count,
        relation_count=relation_count,
        sensitive_count=sensitive_count,
        entity_density_per_kchars=round(density, 3),
        confidence_avg=round(confidence_avg, 4),
        error=result.error or "",
    )

    if result.error:
        # 抽取失败：所有维度 0；overall 0；alert
        metric.overall = 0.0
        metric.quality_alert = True
    else:
        metric.score_entity_density = round(_score_density(density), 4)
        metric.score_relation_validity = round(
            _score_relation_validity(entity_count, relation_count), 4,
        )
        metric.score_confidence_avg = confidence_avg
        metric.score_sensitive_handled = round(
            _score_sensitive(content_chars, sensitive_count), 4,
        )
        metric.overall = round(
            metric.score_entity_density * _DIM_WEIGHTS["entity_density"]
            + metric.score_relation_validity * _DIM_WEIGHTS["relation_validity"]
            + metric.score_confidence_avg * _DIM_WEIGHTS["confidence_avg"]
            + metric.score_sensitive_handled * _DIM_WEIGHTS["sensitive_handled"],
            4,
        )
        metric.quality_alert = metric.overall < _QUALITY_ALERT_THRESHOLD

    _metrics.append(metric)
    if len(_metrics) > _METRICS_MAX:
        _metrics.pop(0)

    if metric.quality_alert:
        log.warning(
            "w4_quality_alert",
            doc_id=result.doc_id,
            overall=metric.overall,
            entity_count=entity_count,
            error=metric.error,
        )

    return metric


def list_extraction_metrics(
    *,
    project_id: str | None = None,
    only_alerting: bool = False,
    limit: int = 100,
) -> list[ExtractionMetric]:
    out = list(reversed(_metrics))   # 最新优先
    if project_id is not None:
        out = [m for m in out if m.project_id == project_id]
    if only_alerting:
        out = [m for m in out if m.quality_alert]
    return out[:limit]


def aggregate_extraction_metrics(
    *,
    project_id: str | None = None,
) -> dict:
    items = list(_metrics)
    if project_id is not None:
        items = [m for m in items if m.project_id == project_id]
    n = len(items)
    if n == 0:
        return {
            "total": 0, "alerting": 0, "avg_overall": 0.0,
            "avg_entity_count": 0.0, "avg_relation_count": 0.0,
            "avg_confidence": 0.0, "avg_density": 0.0,
        }
    return {
        "total": n,
        "alerting": sum(1 for m in items if m.quality_alert),
        "avg_overall": round(sum(m.overall for m in items) / n, 4),
        "avg_entity_count": round(sum(m.entity_count for m in items) / n, 2),
        "avg_relation_count": round(sum(m.relation_count for m in items) / n, 2),
        "avg_confidence": round(sum(m.confidence_avg for m in items) / n, 4),
        "avg_density": round(
            sum(m.entity_density_per_kchars for m in items) / n, 3,
        ),
    }
