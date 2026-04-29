"""LLM-Critic Agent — 6 维质疑机制（决策书 §5.5 D13）。

设计原则（feedback memory · AI native + 轻量化）：
- M2 lite：单 LLM 调用做 6 维质疑（核心机制对齐决策书）
- 双 Agent 互审完整版（抽取 LLM-A + 质疑 LLM-B 独立提示词）作为 M3 高级治理批
- 函数式 sync/async 双轨（与 librarian/judge 同款，M0 坑 1 模式）

输入：Librarian + Auditor + Judge 产出 + 文档原文
输出：CriticResult（6 维 findings + overall_severity + summary）

调用方：pipeline 在 judge 之后调用 critic；
- has_blocking_issue() 时升级 needs_review 标记（即使 judge.confidence 高）
- summary 与 findings 摘要写入审核台工单 description（喂给人审）
"""

from __future__ import annotations

from packages.common import get_logger, settings
from packages.common.types import (
    AuditResult,
    CriticDimension,
    CriticFinding,
    CriticResult,
    JudgeResult,
    LibrarianResult,
    RawDocument,
)
from packages.distillation.llm_client import acall_llm_json, call_llm_json
from packages.distillation.prompts.templates import CRITIC_SYSTEM, CRITIC_USER

log = get_logger("agent.critic")

_VALID_DIMENSIONS: tuple[CriticDimension, ...] = (
    "consistency", "completeness", "evidence",
    "duplication", "timeliness", "cross_domain",
)


def _build_user_prompt(
    doc: RawDocument,
    librarian: LibrarianResult,
    audit: AuditResult | None,
    judge: JudgeResult,
) -> str:
    """组装 critic 用户提示词（纯函数，sync/async 共用）。"""
    entities_text = "（无）"
    if librarian.mentioned_entities:
        entities_text = "\n".join(
            f"- {e.name} ({e.type})" for e in librarian.mentioned_entities[:20]
        )

    audit_summary = "无同类目对比信息。"
    if audit and audit.summary:
        audit_summary = audit.summary

    return CRITIC_USER.format(
        title=doc.title,
        doc_type=librarian.doc_type.value if librarian.doc_type else "其他",
        source_system=doc.source_system.value,
        entities=entities_text,
        audit_summary=audit_summary,
        decision=judge.decision.value,
        confidence=f"{judge.confidence:.2f}",
        judge_summary=judge.summary or "（无）",
        content_excerpt=doc.content[:1500],
    )


def _parse_critic_response(data: dict) -> CriticResult:
    """从 LLM JSON 输出解析为 CriticResult（容错：维度缺失时填默认）。"""
    findings_raw = data.get("findings", [])
    findings: list[CriticFinding] = []
    seen_dims: set[str] = set()

    for item in findings_raw:
        if not isinstance(item, dict):
            continue
        dim = item.get("dimension", "").strip()
        if dim not in _VALID_DIMENSIONS or dim in seen_dims:
            continue
        seen_dims.add(dim)
        try:
            severity = max(0.0, min(1.0, float(item.get("severity", 0.0))))
        except (TypeError, ValueError):
            severity = 0.0
        findings.append(CriticFinding(
            dimension=dim,  # type: ignore[arg-type]
            severity=severity,
            finding=str(item.get("finding", "") or "")[:500],
            evidence=str(item.get("evidence", "") or "")[:300],
            suggestion=str(item.get("suggestion", "") or "")[:300],
        ))

    # 兜底：未提到的维度补 0 severity 占位（确保 6 维齐全）
    for dim in _VALID_DIMENSIONS:
        if dim not in seen_dims:
            findings.append(CriticFinding(
                dimension=dim,
                severity=0.0,
                finding="（LLM 未提及此维度）",
            ))

    overall = max((f.severity for f in findings), default=0.0)
    return CriticResult(
        findings=findings,
        overall_severity=overall,
        summary=str(data.get("summary", "") or "")[:200],
    )


def run_critic(
    doc: RawDocument,
    librarian: LibrarianResult,
    audit: AuditResult | None,
    judge: JudgeResult,
) -> CriticResult:
    """对单文档跑 6 维 LLM-Critic（**同步版**，M0 双轨兼容）。"""
    log.info("critic_start", doc_id=doc.doc_id)
    user_prompt = _build_user_prompt(doc, librarian, audit, judge)
    try:
        data = call_llm_json(CRITIC_SYSTEM, user_prompt)
    except Exception as e:
        # mock fallback 由 settings.allow_mock_llm 门控（坑 F）；这里捕获
        # 失败时返回空 critic，让 pipeline 不阻断（feedback · 轻量化兜底）
        log.warning("critic_failed_fallback_empty", doc_id=doc.doc_id, error=str(e))
        return CriticResult(summary=f"Critic 调用失败: {e}")
    result = _parse_critic_response(data)
    log.info(
        "critic_done", doc_id=doc.doc_id,
        overall_severity=result.overall_severity,
        blocking=result.has_blocking_issue(),
    )
    return result


async def arun_critic(
    doc: RawDocument,
    librarian: LibrarianResult,
    audit: AuditResult | None,
    judge: JudgeResult,
) -> CriticResult:
    """异步版 critic（M0 坑 1 模式）。"""
    log.info("critic_start_async", doc_id=doc.doc_id)
    user_prompt = _build_user_prompt(doc, librarian, audit, judge)
    try:
        data = await acall_llm_json(CRITIC_SYSTEM, user_prompt)
    except Exception as e:
        log.warning("critic_failed_fallback_empty_async", doc_id=doc.doc_id, error=str(e))
        return CriticResult(summary=f"Critic 调用失败: {e}")
    result = _parse_critic_response(data)
    log.info(
        "critic_done_async", doc_id=doc.doc_id,
        overall_severity=result.overall_severity,
        blocking=result.has_blocking_issue(),
    )
    return result


def critic_to_review_description(critic: CriticResult, base_desc: str = "") -> str:
    """把 6 维 critic 摘要拼到审核台工单 description（W4 写入侧 hook 调用）。

    只列 severity ≥ 0.3 的维度（避免噪音）。
    """
    parts = [base_desc] if base_desc else []
    if critic.summary:
        parts.append(f"[Critic] {critic.summary}")
    salient = [f for f in critic.findings if f.severity >= 0.3]
    for f in salient:
        parts.append(f"· {f.dimension}({f.severity:.2f}): {f.finding[:80]}")
    return " | ".join(parts)
