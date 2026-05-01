"""Wiki 编译质量评分（M17 #3 · 决策书 §6 三层 Wiki + 6 维 LLM-Critic）。

每个 Wiki 页（source_summary / domain_overview / index）跑 6 维评分：
1. consistency（一致性）— 与源文档不矛盾
2. completeness（完整性）— 关键事实未缺失
3. evidence（证据强度）— 引用是否充分
4. repetition（去重）— 信息是否冗余
5. freshness（时效性）— 是否含过期信息
6. cross_domain（跨域）— 与其他 domain 的关联是否合理

每维 0-1 分；总分加权平均。低于阈值 → quality_alert。
不实际改 Wiki 内容；仅记录评分给 SME 审。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from packages.common import get_logger
from packages.distillation.llm_client import acall_llm_json

log = get_logger("observability.wiki_quality")


CRITIC_DIMENSIONS = (
    "consistency", "completeness", "evidence",
    "repetition", "freshness", "cross_domain",
)
DimensionName = Literal[
    "consistency", "completeness", "evidence",
    "repetition", "freshness", "cross_domain",
]

# 每维权重（合计 1.0）
DIMENSION_WEIGHTS: dict[DimensionName, float] = {
    "consistency": 0.20,
    "completeness": 0.20,
    "evidence": 0.20,
    "repetition": 0.10,
    "freshness": 0.15,
    "cross_domain": 0.15,
}

_QUALITY_ALERT_THRESHOLD = 0.6


WIKI_CRITIC_SYSTEM = """你是一名资深知识库审查员，对 Wiki 页的编译质量做 6 维打分。

每维输出 0.0-1.0 分（保留 2 位小数）+ 一句话理由。

维度定义：
1. consistency（一致性）：内容是否与引用源不矛盾
2. completeness（完整性）：关键事实是否覆盖完整
3. evidence（证据强度）：引用源 / cross_refs 是否充分
4. repetition（去重）：是否有冗余重复（高分 = 无冗余）
5. freshness（时效性）：是否含明显过期 / 已废止信息（高分 = 时效新）
6. cross_domain（跨域关联）：与其他领域的关联是否合理（高分 = 关联自然）

严格按 JSON 格式输出，每维含 score + reason。"""

WIKI_CRITIC_USER = """## Wiki 页元数据
- page_id: {page_id}
- page_type: {page_type}
- title: {title}
- 引用源数量: {source_doc_count}
- cross_refs 数量: {cross_ref_count}
- 编译版本: v{version}

## Wiki 内容（前 2000 字）
{content}

## 请按以下 JSON 格式打分：
{{
  "consistency": {{"score": 0.0-1.0, "reason": "一句话理由"}},
  "completeness": {{...}},
  "evidence": {{...}},
  "repetition": {{...}},
  "freshness": {{...}},
  "cross_domain": {{...}}
}}"""


# ════════════════════════════════════════════════════════════════════════
#  数据模型
# ════════════════════════════════════════════════════════════════════════


class DimensionScore(BaseModel):
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""


class WikiQualityScore(BaseModel):
    """单 Wiki 页的 6 维评分（M17 #3）。"""
    page_id: str
    page_type: str = ""
    project_id: str = ""
    consistency: DimensionScore = Field(default_factory=DimensionScore)
    completeness: DimensionScore = Field(default_factory=DimensionScore)
    evidence: DimensionScore = Field(default_factory=DimensionScore)
    repetition: DimensionScore = Field(default_factory=DimensionScore)
    freshness: DimensionScore = Field(default_factory=DimensionScore)
    cross_domain: DimensionScore = Field(default_factory=DimensionScore)
    overall: float = 0.0       # 加权平均
    quality_alert: bool = False  # overall < threshold
    error: str = ""             # LLM 失败时填写
    scored_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))


# ════════════════════════════════════════════════════════════════════════
#  内存存储 + sink
# ════════════════════════════════════════════════════════════════════════

_scores: dict[str, WikiQualityScore] = {}    # page_id → 最新评分


def reset_wiki_quality_for_test() -> None:
    _scores.clear()


def get_wiki_quality_score(page_id: str) -> WikiQualityScore | None:
    return _scores.get(page_id)


def list_wiki_quality_scores(
    *,
    project_id: str | None = None,
    only_alerting: bool = False,
) -> list[WikiQualityScore]:
    out = list(_scores.values())
    if project_id is not None:
        out = [s for s in out if s.project_id == project_id]
    if only_alerting:
        out = [s for s in out if s.quality_alert]
    out.sort(key=lambda s: (s.overall, s.scored_at), reverse=False)
    return out


# ════════════════════════════════════════════════════════════════════════
#  LLM 评分
# ════════════════════════════════════════════════════════════════════════


def _compute_overall(score: WikiQualityScore) -> float:
    """按 DIMENSION_WEIGHTS 加权平均。"""
    total = (
        score.consistency.score * DIMENSION_WEIGHTS["consistency"]
        + score.completeness.score * DIMENSION_WEIGHTS["completeness"]
        + score.evidence.score * DIMENSION_WEIGHTS["evidence"]
        + score.repetition.score * DIMENSION_WEIGHTS["repetition"]
        + score.freshness.score * DIMENSION_WEIGHTS["freshness"]
        + score.cross_domain.score * DIMENSION_WEIGHTS["cross_domain"]
    )
    return round(total, 4)


def _parse_dimension(data: dict, key: str) -> DimensionScore:
    raw = data.get(key) or {}
    if not isinstance(raw, dict):
        return DimensionScore()
    try:
        score = float(raw.get("score", 0.0))
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(1.0, score))
    reason = str(raw.get("reason", ""))[:200]
    return DimensionScore(score=score, reason=reason)


async def score_wiki_page(
    *,
    page_id: str,
    page_type: str,
    title: str,
    content: str,
    source_doc_count: int = 0,
    cross_ref_count: int = 0,
    version: int = 1,
    project_id: str = "",
    content_chars_limit: int = 2000,
) -> WikiQualityScore:
    """对单个 Wiki 页打 6 维分（M17 #3）。

    成功 → 返回完整 WikiQualityScore + 入 _scores 字典
    LLM 失败 → 返回带 error 字段的 score（默认 0 分；不入字典）
    """
    user_prompt = WIKI_CRITIC_USER.format(
        page_id=page_id,
        page_type=page_type,
        title=title,
        source_doc_count=source_doc_count,
        cross_ref_count=cross_ref_count,
        version=version,
        content=(content or "")[:content_chars_limit],
    )

    try:
        data = await acall_llm_json(WIKI_CRITIC_SYSTEM, user_prompt)
    except Exception as e:
        log.warning("wiki_quality_llm_failed",
                    page_id=page_id, error=str(e))
        return WikiQualityScore(
            page_id=page_id, page_type=page_type, project_id=project_id,
            error=str(e)[:200],
        )

    score = WikiQualityScore(
        page_id=page_id, page_type=page_type, project_id=project_id,
        consistency=_parse_dimension(data, "consistency"),
        completeness=_parse_dimension(data, "completeness"),
        evidence=_parse_dimension(data, "evidence"),
        repetition=_parse_dimension(data, "repetition"),
        freshness=_parse_dimension(data, "freshness"),
        cross_domain=_parse_dimension(data, "cross_domain"),
    )
    score.overall = _compute_overall(score)
    score.quality_alert = score.overall < _QUALITY_ALERT_THRESHOLD

    _scores[page_id] = score
    log.info(
        "wiki_quality_scored",
        page_id=page_id, page_type=page_type,
        overall=score.overall, alert=score.quality_alert,
    )
    return score


def aggregate_wiki_quality(
    *, project_id: str | None = None,
) -> dict:
    """按 project / 全局聚合 Wiki 评分。

    Returns:
        {
            "total_scored": int,
            "alerting_count": int,
            "avg_overall": float,
            "avg_dimensions": {dim: avg_score, ...},
        }
    """
    scores = list_wiki_quality_scores(project_id=project_id)
    n = len(scores)
    if n == 0:
        return {
            "total_scored": 0, "alerting_count": 0,
            "avg_overall": 0.0,
            "avg_dimensions": {dim: 0.0 for dim in CRITIC_DIMENSIONS},
        }
    avg_overall = round(sum(s.overall for s in scores) / n, 4)
    avg_dims: dict[str, float] = {}
    for dim in CRITIC_DIMENSIONS:
        avg_dims[dim] = round(
            sum(getattr(s, dim).score for s in scores) / n, 4,
        )
    alerting = sum(1 for s in scores if s.quality_alert)
    return {
        "total_scored": n,
        "alerting_count": alerting,
        "avg_overall": avg_overall,
        "avg_dimensions": avg_dims,
    }
