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
from packages.distillation.llm_client import call_llm_json
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


def run_conflict_auditor(
    category: str,
    docs: list[RawDocument],
    meta: dict[str, LibrarianResult],
) -> AuditResult:
    """对同一类目下的文档组运行冲突审计，检测重叠和矛盾。

    处理流程：
      1. 若文档数 < 2，直接返回空结果（无需对比）
      2. 构建文档摘要文本并调用 LLM 进行横向分析
      3. 解析 LLM 返回的重叠组和冲突项
      4. 根据重叠类型和涉及文档数计算 max_overlap_score

    Args:
        category: 知识类目名称（如"电力安全规程"），用于 LLM 上下文。
        docs: 该类目下的原始文档列表。
        meta: 文档 ID 到 LibrarianResult 的映射字典。

    Returns:
        AuditResult: 审计结果，包含重叠组列表、冲突项列表、摘要和最大重叠分数。
    """
    # 仅一篇文档时无需冲突审计
    if len(docs) < 2:
        return AuditResult(summary="仅一篇文档，无需冲突审计。")

    log.info("auditor_start", category=category, doc_count=len(docs))

    # 构建文档摘要文本并组装提示词
    documents_text = _build_documents_text(docs, meta)
    user_prompt = AUDITOR_USER.format(
        knowledge_category=category,
        doc_count=len(docs),
        documents_text=documents_text,
    )

    # 调用 LLM 获取 JSON 格式的审计结果
    data = call_llm_json(AUDITOR_SYSTEM, user_prompt)

    # 解析 LLM 返回的重叠组和冲突项
    result = AuditResult(
        overlap_groups=[OverlapGroup(**g) for g in data.get("overlap_groups", [])],
        conflicts=[ConflictItem(**c) for c in data.get("conflicts", [])],
        summary=data.get("summary", ""),
    )

    # ---- 计算最大重叠分数（供 KPI_retain 使用）----
    # 根据 overlap_type 分级加权：完全重复 > 版本迭代 > 部分重复 > 内容矛盾
    if result.overlap_groups:
        type_weight = {
            "完全重复": 1.0,
            "版本迭代": 0.8,
            "部分重复": 0.5,
            "内容矛盾": 0.3,
        }
        group_scores = []
        for group in result.overlap_groups:
            base = type_weight.get(group.overlap_type, 0.4)  # 未知类型默认 0.4
            # 涉及文档越多，冗余度越高（最多 5 篇封顶）
            doc_factor = min(len(group.doc_ids) / 5.0, 1.0)
            # 基础权重占 60%，文档数量因子占 40%
            group_scores.append(base * (0.6 + 0.4 * doc_factor))
        result.max_overlap_score = max(group_scores)
    else:
        result.max_overlap_score = 0.0  # 无重叠组时冗余度为零

    log.info(
        "auditor_done",
        category=category,
        overlap_count=len(result.overlap_groups),
        conflict_count=len(result.conflicts),
    )
    return result
