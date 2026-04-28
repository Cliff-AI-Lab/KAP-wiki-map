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
from packages.distillation.llm_client import call_llm_json
from packages.distillation.prompts.templates import JUDGE_SYSTEM, JUDGE_USER
from packages.distillation.scoring.judge_thresholds import (
    JudgeThresholds,
    load_thresholds,
)
from packages.distillation.scoring.kpi_retain import compute_kpi_retain

log = get_logger("agent.judge")


def run_judge(
    doc: RawDocument,
    librarian_result: LibrarianResult,
    audit_result: AuditResult | None = None,
    *,
    industry: str | None = None,
    thresholds: JudgeThresholds | None = None,
) -> JudgeResult:
    """对单个文档运行 Judge Agent，输出保留/归档/丢弃决策。

    处理流程：
      1. 组装 LLM 提示词（含文档正文摘要 + 冲突审计上下文）
      2. 调用 LLM 获取四维度评分（时效性、密度、完整性、冗余度）及初步决策
      3. 计算 KPI_retain 量化指标
      4. 综合 LLM 判定与 KPI 阈值，输出最终决策

    Args:
        doc: 原始文档对象，包含 doc_id、标题、正文、时间戳等信息。
        librarian_result: Librarian Agent 提取的元数据，包含文档类型等。
        audit_result: Conflict Auditor 的审计结果（可选），包含重叠分数和冲突摘要。
            若为 None 表示该文档未参与同类目冲突审计。
        industry: 行业模板名（如 ``"energy"`` / ``"manufacturing"``）。指定后从
            ``templates/<industry>/judge-thresholds.yaml`` 加载阈值；为 None 走默认。
        thresholds: 直接传入的阈值集（覆盖 ``industry`` 参数），主要给单测用。

    Returns:
        JudgeResult: 包含推理过程、最终决策、置信度、KPI 值、摘要和关键实体。
    """
    log.info("judge_start", doc_id=doc.doc_id)

    # 准备冲突审计上下文：若有审计摘要则注入，否则使用默认占位文本
    audit_context = "无同类目文档对比信息。"
    if audit_result and audit_result.summary:
        audit_context = audit_result.summary

    # 组装用户提示词，填充文档基本信息和正文摘要
    user_prompt = JUDGE_USER.format(
        doc_id=doc.doc_id,
        title=doc.title,
        source_system=doc.source_system.value,
        doc_type=librarian_result.doc_type.value,
        created_at=str(doc.created_at or "未知"),
        updated_at=str(doc.updated_at or "未知"),
        content_excerpt=doc.content[:settings.judge_content_chars],
        audit_context=audit_context,
    )

    # 调用 LLM 获取 JSON 格式的评分与决策
    data = call_llm_json(JUDGE_SYSTEM, user_prompt)

    # 解析 LLM 输出：提取四维度评分（各维度 0-10 分），缺失字段默认 5 分
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

    # 解析 LLM 的初步决策和置信度；无效决策值降级为 KEEP
    llm_decision_str = data.get("decision", "KEEP").upper()
    llm_decision = Decision(llm_decision_str) if llm_decision_str in Decision.__members__ else Decision.KEEP
    confidence = float(data.get("confidence", 0.5))

    # ---- 计算 KPI_retain ----
    # 冗余度取 Auditor 的重叠分数与 LLM 冗余评分中的较大值
    redundancy = audit_result.max_overlap_score if audit_result else 0.0
    # LLM redundancy_score 越高 → 冗余度越高 → KPI 惩罚越大
    llm_redundancy = reasoning.redundancy_score / 10.0  # 归一化到 0-1
    effective_redundancy = max(redundancy, llm_redundancy)

    kpi = compute_kpi_retain(
        density_score=reasoning.density_score,
        updated_at=doc.updated_at,
        redundancy_score=effective_redundancy,
    )

    # ---- 综合决策（外置阈值 + 纯函数）----
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
        # ── M0-tech-debt 坑 3：决策追溯字段 ──
        needs_review=outcome.needs_review,
        rule_hit=outcome.rule_hit,
        decision_reason=outcome.reason,
        thresholds_source=outcome.thresholds_source,
    )

    log.info(
        "judge_done",
        doc_id=doc.doc_id,
        llm_decision=llm_decision.value,
        kpi_retain=kpi,
        final_decision=outcome.decision.value,
        confidence=confidence,
        rule_hit=outcome.rule_hit,
        needs_review=outcome.needs_review,
        thresholds_source=outcome.thresholds_source,
        industry=active_thresholds.industry,
    )

    return result
