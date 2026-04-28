"""Librarian Agent — 扫描与元数据提取。

从原始文档中提取结构化元数据：文档类型、版本号、关键主题、提及实体等。

本模块是蒸馏流水线的第一环节，负责对每篇原始文档进行"编目"处理。
通过调用 LLM 分析文档内容，自动提取以下元数据：
  - doc_type: 文档类型（如技术规范、会议纪要、培训材料等）
  - version_id: 文档版本标识
  - key_topics: 关键主题列表
  - mentioned_entities: 文档中提及的实体（人、组织、系统等）
  - is_conversational: 是否为对话体文档（如聊天记录）
  - estimated_value: 预估知识价值（HIGH/MEDIUM/LOW）

提取结果将传递给下游的 Conflict Auditor 和 Judge Agent 作为决策依据。
"""

from __future__ import annotations

from packages.common import get_logger, settings
from packages.common.types import (
    DocType,
    EstimatedValue,
    LibrarianResult,
    MentionedEntity,
    RawDocument,
)
from packages.distillation.llm_client import acall_llm_json, call_llm_json
from packages.distillation.prompts.templates import LIBRARIAN_SYSTEM, LIBRARIAN_USER

log = get_logger("agent.librarian")

# 文档类型映射：将 LLM 返回的字符串值映射为 DocType 枚举
_DOC_TYPE_MAP = {v.value: v for v in DocType}
# 价值等级映射：将 LLM 返回的字符串值映射为 EstimatedValue 枚举
_VALUE_MAP = {v.value: v for v in EstimatedValue}


def _build_user_prompt(doc: RawDocument) -> str:
    """组装 Librarian 用户提示词（纯函数，sync/async 共用）。"""
    return LIBRARIAN_USER.format(
        source_system=doc.source_system.value,
        title=doc.title,
        created_at=str(doc.created_at or "未知"),
        updated_at=str(doc.updated_at or "未知"),
        last_modifier=doc.last_modifier or "未知",
        content_preview=doc.content[:settings.librarian_preview_chars],
    )


def _parse_librarian_response(data: dict, doc: RawDocument) -> LibrarianResult:
    """解析 LLM 返回的 JSON 为 LibrarianResult（纯函数，sync/async 共用）。

    无效枚举值降级为默认（DocType.OTHER / EstimatedValue.MEDIUM），并记录警告。
    """
    raw_doc_type = data.get("doc_type", "")
    doc_type = _DOC_TYPE_MAP.get(raw_doc_type)
    if doc_type is None:
        log.warning(
            "librarian_doc_type_fallback",
            doc_id=doc.doc_id,
            raw_doc_type=raw_doc_type,
            valid_types=list(_DOC_TYPE_MAP.keys()),
        )
        doc_type = DocType.OTHER

    raw_value = data.get("estimated_value", "MEDIUM")
    estimated_value = _VALUE_MAP.get(raw_value)
    if estimated_value is None:
        log.warning(
            "librarian_value_fallback",
            doc_id=doc.doc_id,
            raw_value=raw_value,
        )
        estimated_value = EstimatedValue.MEDIUM

    return LibrarianResult(
        doc_type=doc_type,
        version_id=data.get("version_id"),
        key_topics=data.get("key_topics", []),
        mentioned_entities=[
            MentionedEntity(**e) for e in data.get("mentioned_entities", [])
        ],
        is_conversational=data.get("is_conversational", False),
        estimated_value=estimated_value,
    )


def run_librarian(doc: RawDocument) -> LibrarianResult:
    """对单个文档运行 Librarian Agent，提取结构化元数据（**同步版**，M0 兼容入口）。"""
    log.info("librarian_start", doc_id=doc.doc_id, title=doc.title)
    user_prompt = _build_user_prompt(doc)
    data = call_llm_json(LIBRARIAN_SYSTEM, user_prompt)
    result = _parse_librarian_response(data, doc)
    log.info(
        "librarian_done",
        doc_id=doc.doc_id,
        doc_type=result.doc_type.value,
        topics=result.key_topics,
        entity_count=len(result.mentioned_entities),
    )
    return result


async def arun_librarian(doc: RawDocument) -> LibrarianResult:
    """对单个文档运行 Librarian Agent（**异步版**，坑 1 批 2 主要交付物）。

    与 ``run_librarian`` 行为一致，区别：调 ``acall_llm_json`` 不阻塞 event loop。
    """
    log.info("librarian_start_async", doc_id=doc.doc_id, title=doc.title)
    user_prompt = _build_user_prompt(doc)
    data = await acall_llm_json(LIBRARIAN_SYSTEM, user_prompt)
    result = _parse_librarian_response(data, doc)
    log.info(
        "librarian_done_async",
        doc_id=doc.doc_id,
        doc_type=result.doc_type.value,
        topics=result.key_topics,
        entity_count=len(result.mentioned_entities),
    )
    return result
