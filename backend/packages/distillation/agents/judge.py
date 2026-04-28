"""Judge Agent — 价值评估与决策。

结合 LLM 多维度评分与 KPI_retain 数学公式，做出 KEEP/ARCHIVE/DISCARD 决策。

本模块是蒸馏流水线的核心决策环节。它接收 Librarian 提取的元数据和
Conflict Auditor 的冲突审计结果，通过 LLM 对文档进行多维度评分
（时效性、信息密度、完整性、冗余度），再结合 KPI_retain 数学公式
进行二次校验，最终输出三档决策：KEEP（保留）、ARCHIVE（归档）、DISCARD（丢弃）。

决策优先级逻辑：
  1. KPI 低于丢弃阈值 且 LLM 也判定丢弃 → DISCARD
  2. KPI 低于归档阈值 或 LLM 判定归档 → ARCHIVE
  3. LLM 高置信度判定丢弃（>0.8）→ DISCARD
  4. 其他情况 → 采用 LLM 原始判定
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
from packages.distillation.llm_client import call_llm_json
from packages.distillation.prompts.templates import JUDGE_SYSTEM, JUDGE_USER
from packages.distillation.scoring.kpi_retain import (
    ARCHIVE_THRESHOLD,
    DISCARD_THRESHOLD,
    compute_kpi_retain,
)

log = get_logger("agent.judge")


def run_judge(
    doc: RawDocument,
    librarian_result: LibrarianResult,
    audit_result: AuditResult | None = None,
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

    # ---- 综合决策：LLM 判定与 KPI 公式判定结合 ----
    # 规则1：KPI 极低 + LLM 也判丢弃 → 确认丢弃
    if kpi < DISCARD_THRESHOLD and llm_decision == Decision.DISCARD:
        final_decision = Decision.DISCARD
    # 规则2：KPI 低于归档线 或 LLM 建议归档 → 归档
    elif kpi < ARCHIVE_THRESHOLD or llm_decision == Decision.ARCHIVE:
        final_decision = Decision.ARCHIVE
    # 规则3：LLM 高置信度丢弃（>0.8）→ 尊重 LLM 判断
    elif llm_decision == Decision.DISCARD and confidence > 0.8:
        final_decision = Decision.DISCARD
    # 规则4：默认采用 LLM 的原始判定
    else:
        final_decision = llm_decision

    result = JudgeResult(
        reasoning=reasoning,
        decision=final_decision,
        confidence=confidence,
        kpi_retain=kpi,
        summary=data.get("summary", ""),
        key_entities=data.get("key_entities", []),
    )

    log.info(
        "judge_done",
        doc_id=doc.doc_id,
        llm_decision=llm_decision.value,
        kpi_retain=kpi,
        final_decision=final_decision.value,
        confidence=confidence,
    )
    return result
