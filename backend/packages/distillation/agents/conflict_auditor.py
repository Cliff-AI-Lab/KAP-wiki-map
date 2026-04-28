"""Conflict Auditor Agent — 语义对齐与冲突检测。

在同一知识类目下的文档组中，识别重叠、版本冲突和语义矛盾。

本模块是蒸馏流水线的第二环节，负责在同一知识类目内对多篇文档进行
横向对比分析。通过 LLM 识别以下问题：
  - overlap_groups: 重叠文档组（完全重复、版本迭代、部分重复、内容矛盾）
  - conflicts: 具体的事实冲突或数据矛盾
  - max_overlap_score: 最大重叠分数（0-1），供 KPI_retain 计算使用

审计结果将传递给 Judge Agent，作为文档保留/归档/丢弃决策的输入依据。
单篇文档无需审计，直接返回空结果。
"""

from __future__ import annotations

from packages.common import get_logger
from packages.common.types import (
    AuditResult,
    ConflictItem,
    OverlapGroup,
    RawDocument,
    LibrarianResult,
)
from packages.distillation.llm_client import acall_llm_json, call_llm_json
from packages.distillation.prompts.templates import AUDITOR_SYSTEM, AUDITOR_USER

log = get_logger("agent.auditor")


def _build_documents_text(
    docs: list[RawDocument], meta: dict[str, LibrarianResult]
) -> str:
    """构建审计用的文档摘要文本，将多篇文档拼接为结构化的 Markdown 格式。

    每篇文档包含 ID、标题、来源系统、更新时间、版本号和正文前 800 字的摘要，
    供 LLM 进行横向对比分析。

    Args:
        docs: 同一知识类目下的原始文档列表。
        meta: 文档 ID 到 LibrarianResult 的映射，用于获取版本号等元数据。

    Returns:
        拼接后的 Markdown 格式文档摘要文本。
    """
    parts = []
    for i, doc in enumerate(docs, 1):
        m = meta.get(doc.doc_id)
        version = m.version_id if m else "未标注"
        parts.append(
            f"### 文档 {i}\n"
            f"- ID: {doc.doc_id}\n"
            f"- 标题: {doc.title}\n"
            f"- 来源: {doc.source_system.value}\n"
            f"- 时间: {doc.updated_at}\n"
            f"- 版本: {version}\n"
            f"- 正文摘要:\n{doc.content[:800]}\n"
        )
    return "\n".join(parts)


def _build_user_prompt(
    category: str,
    docs: list[RawDocument],
    meta: dict[str, LibrarianResult],
) -> str:
    """组装 Auditor 用户提示词（纯函数，sync/async 共用）。"""
    documents_text = _build_documents_text(docs, meta)
    return AUDITOR_USER.format(
        knowledge_category=category,
        doc_count=len(docs),
        documents_text=documents_text,
    )


# 重叠类型权重（pure constant，sync/async 共用）
_TYPE_WEIGHT = {
    "完全重复": 1.0,
    "版本迭代": 0.8,
    "部分重复": 0.5,
    "内容矛盾": 0.3,
}


def _build_audit_result(data: dict) -> AuditResult:
    """从 LLM 返回 JSON 构造 AuditResult 并计算 max_overlap_score（纯函数）。"""
    result = AuditResult(
        overlap_groups=[OverlapGroup(**g) for g in data.get("overlap_groups", [])],
        conflicts=[ConflictItem(**c) for c in data.get("conflicts", [])],
        summary=data.get("summary", ""),
    )

    if result.overlap_groups:
        group_scores = []
        for group in result.overlap_groups:
            base = _TYPE_WEIGHT.get(group.overlap_type, 0.4)
            doc_factor = min(len(group.doc_ids) / 5.0, 1.0)
            group_scores.append(base * (0.6 + 0.4 * doc_factor))
        result.max_overlap_score = max(group_scores)
    else:
        result.max_overlap_score = 0.0
    return result


def run_conflict_auditor(
    category: str,
    docs: list[RawDocument],
    meta: dict[str, LibrarianResult],
) -> AuditResult:
    """对同一类目下的文档组运行冲突审计（**同步版**，M0 兼容入口）。"""
    if len(docs) < 2:
        return AuditResult(summary="仅一篇文档，无需冲突审计。")

    log.info("auditor_start", category=category, doc_count=len(docs))
    user_prompt = _build_user_prompt(category, docs, meta)
    data = call_llm_json(AUDITOR_SYSTEM, user_prompt)
    result = _build_audit_result(data)
    log.info(
        "auditor_done",
        category=category,
        overlap_count=len(result.overlap_groups),
        conflict_count=len(result.conflicts),
    )
    return result


async def arun_conflict_auditor(
    category: str,
    docs: list[RawDocument],
    meta: dict[str, LibrarianResult],
) -> AuditResult:
    """对同一类目下的文档组运行冲突审计（**异步版**，坑 1 批 2 主要交付物）。"""
    # 仅一篇文档时无需调用 LLM，立即同步返回（不浪费 await）
    if len(docs) < 2:
        return AuditResult(summary="仅一篇文档，无需冲突审计。")

    log.info("auditor_start_async", category=category, doc_count=len(docs))
    user_prompt = _build_user_prompt(category, docs, meta)
    data = await acall_llm_json(AUDITOR_SYSTEM, user_prompt)
    result = _build_audit_result(data)
    log.info(
        "auditor_done_async",
        category=category,
        overlap_count=len(result.overlap_groups),
        conflict_count=len(result.conflicts),
    )
    return result
