"""Judge Agent — 价值评估与决策。

结合 LLM 多维度评分与 KPI_retain 数学公式，做出 KEEP/ARCHIVE/DISCARD 决策。

本模块是蒸馏流水线的核心决策环节。它接收 Librarian 提取的元数据和
Conflict Auditor 的冲突审计结果，通过 LLM 对文档进行多维度评分
（时效性、信息密度、完整性、冗余度），再结合 KPI_retain 数学公式
进行二次校验，最终输出三档决策：KEEP（保留）、ARCHIVE（归档）、DISCARD（丢弃）。

决策规则与阈值：
  - 阈值通过行业模板包外置（``templates/<industry>/judge-thresholds.yaml``），
    见 ``packages.distillation.scoring.judge_thresholds.load_thresholds()``
  - 决策规则函数化为纯函数 ``decide()``，见
    ``packages.distillation.agents.judge_decision``
  - 决策结果含 ``needs_review`` 标记：KPI 居中 + 低置信度时挂起待 SME 复核

M0-tech-debt 坑 3 改造：
  - 移除模块级 ``DISCARD_THRESHOLD`` / ``ARCHIVE_THRESHOLD`` 硬编码引用
  - 决策逻辑剥离到 ``judge_decision.decide()`` 纯函数，独立可单测
"""

from __future__ import annotations

from packages.common import get_logger, settings
from packages.common.types import (
    AuditResult,
    Decision,
    JudgeReasoning,
    JudgeResult,
    RawDocument,
    LibrarianResult,
)
from packages.distillation.agents.judge_decision import decide
from packages.distillation.llm_client import acall_llm_json, call_llm_json
from packages.distillation.prompts.templates import JUDGE_SYSTEM, JUDGE_USER
from packages.distillation.scoring.judge_thresholds import (
    JudgeThresholds,
    load_thresholds,
)
from packages.distillation.scoring.kpi_retain import compute_kpi_retain

log = get_logger("agent.judge")


def _build_user_prompt(
    doc: RawDocument,
    librarian_result: LibrarianResult,
    audit_result: AuditResult | None,
) -> str:
    """组装 Judge 用户提示词（纯函数，sync/async 共用）。"""
    audit_context = "无同类目文档对比信息。"
    if audit_result and audit_result.summary:
        audit_context = audit_result.summary
    return JUDGE_USER.format(
        doc_id=doc.doc_id,
        title=doc.title,
        source_system=doc.source_system.value,
        doc_type=librarian_result.doc_type.value,
        created_at=str(doc.created_at or "未知"),
        updated_at=str(doc.updated_at or "未知"),
        content_excerpt=doc.content[:settings.judge_content_chars],
        audit_context=audit_context,
    )


def _build_judge_result(
    data: dict,
    doc: RawDocument,
    audit_result: AuditResult | None,
    industry: str | None,
    thresholds: JudgeThresholds | None,
) -> tuple[JudgeResult, Decision, float]:
    """从 LLM 返回 JSON + KPI 计算 + 决策规则，构造 JudgeResult（纯函数）。

    Returns:
        (result, llm_decision, kpi)：第二三项供日志记录。
    """
    reasoning_data = data.get("reasoning", {})
    reasoning = JudgeReasoning(
        recency_analysis=reasoning_data.get("recency_analysis", ""),
        recency_score=float(reasoning_data.get("recency_score", 5)),
        density_analysis=reasoning_data.get("density_analysis", ""),
        density_score=float(reasoning_data.get("density_score", 5)),
        completeness_analysis=reasoning_data.get("completeness_analysis", ""),
        completeness_score=float(reasoning_data.get("completeness_score", 5)),
        redundancy_analysis=reasoning_data.get("redundancy_analysis", ""),
        redundancy_score=float(reasoning_data.get("redundancy_score", 5)),
    )

    llm_decision_str = data.get("decision", "KEEP").upper()
    llm_decision = (
        Decision(llm_decision_str)
        if llm_decision_str in Decision.__members__
        else Decision.KEEP
    )
    confidence = float(data.get("confidence", 0.5))

    # 冗余度取 Auditor 的重叠分数与 LLM 冗余评分中的较大值
    redundancy = audit_result.max_overlap_score if audit_result else 0.0
    llm_redundancy = reasoning.redundancy_score / 10.0
    effective_redundancy = max(redundancy, llm_redundancy)

    kpi = compute_kpi_retain(
        density_score=reasoning.density_score,
        updated_at=doc.updated_at,
        redundancy_score=effective_redundancy,
    )

    active_thresholds = thresholds if thresholds is not None else load_thresholds(industry)
    outcome = decide(
        kpi=kpi,
        llm_decision=llm_decision,
        confidence=confidence,
        thresholds=active_thresholds,
    )

    result = JudgeResult(
        reasoning=reasoning,
        decision=outcome.decision,
        confidence=confidence,
        kpi_retain=kpi,
        summary=data.get("summary", ""),
        key_entities=data.get("key_entities", []),
        needs_review=outcome.needs_review,
        rule_hit=outcome.rule_hit,
        decision_reason=outcome.reason,
        thresholds_source=outcome.thresholds_source,
    )
    return result, llm_decision, kpi


def run_judge(
    doc: RawDocument,
    librarian_result: LibrarianResult,
    audit_result: AuditResult | None = None,
    *,
    industry: str | None = None,
    thresholds: JudgeThresholds | None = None,
) -> JudgeResult:
    """对单个文档运行 Judge Agent（**同步版**，M0 兼容入口）。"""
    log.info("judge_start", doc_id=doc.doc_id)
    user_prompt = _build_user_prompt(doc, librarian_result, audit_result)
    data = call_llm_json(JUDGE_SYSTEM, user_prompt)
    result, llm_decision, kpi = _build_judge_result(
        data, doc, audit_result, industry, thresholds
    )
    log.info(
        "judge_done",
        doc_id=doc.doc_id,
        llm_decision=llm_decision.value,
        kpi_retain=kpi,
        final_decision=result.decision.value,
        confidence=result.confidence,
        rule_hit=result.rule_hit,
        needs_review=result.needs_review,
        thresholds_source=result.thresholds_source,
    )
    return result


async def arun_judge(
    doc: RawDocument,
    librarian_result: LibrarianResult,
    audit_result: AuditResult | None = None,
    *,
    industry: str | None = None,
    thresholds: JudgeThresholds | None = None,
) -> JudgeResult:
    """对单个文档运行 Judge Agent（**异步版**，坑 1 批 2 主要交付物）。"""
    log.info("judge_start_async", doc_id=doc.doc_id)
    user_prompt = _build_user_prompt(doc, librarian_result, audit_result)
    data = await acall_llm_json(JUDGE_SYSTEM, user_prompt)
    result, llm_decision, kpi = _build_judge_result(
        data, doc, audit_result, industry, thresholds
    )
    log.info(
        "judge_done_async",
        doc_id=doc.doc_id,
        llm_decision=llm_decision.value,
        kpi_retain=kpi,
        final_decision=result.decision.value,
        confidence=result.confidence,
        rule_hit=result.rule_hit,
        needs_review=result.needs_review,
        thresholds_source=result.thresholds_source,
    )
    return result
