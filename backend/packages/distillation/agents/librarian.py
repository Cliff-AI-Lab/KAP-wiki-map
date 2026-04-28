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
from packages.distillation.llm_client import call_llm_json
from packages.distillation.prompts.templates import LIBRARIAN_SYSTEM, LIBRARIAN_USER

log = get_logger("agent.librarian")

# 文档类型映射：将 LLM 返回的字符串值映射为 DocType 枚举
_DOC_TYPE_MAP = {v.value: v for v in DocType}
# 价值等级映射：将 LLM 返回的字符串值映射为 EstimatedValue 枚举
_VALUE_MAP = {v.value: v for v in EstimatedValue}


def run_librarian(doc: RawDocument) -> LibrarianResult:
    """对单个文档运行 Librarian Agent，提取结构化元数据。

    处理流程：
      1. 使用文档的来源系统、标题、时间、正文预览等信息组装提示词
      2. 调用 LLM 返回 JSON 格式的元数据
      3. 解析并校验 doc_type 和 estimated_value，无效值降级为默认值
      4. 构造 MentionedEntity 列表

    Args:
        doc: 原始文档对象，包含 doc_id、标题、正文、来源系统、时间戳等。

    Returns:
        LibrarianResult: 结构化元数据结果，包含文档类型、主题、实体、价值评估等。
    """
    log.info("librarian_start", doc_id=doc.doc_id, title=doc.title)

    # 组装用户提示词，截取正文前 N 个字符作为预览
    user_prompt = LIBRARIAN_USER.format(
        source_system=doc.source_system.value,
        title=doc.title,
        created_at=str(doc.created_at or "未知"),
        updated_at=str(doc.updated_at or "未知"),
        last_modifier=doc.last_modifier or "未知",
        content_preview=doc.content[:settings.librarian_preview_chars],
    )

    # 调用 LLM 获取 JSON 格式的元数据提取结果
    data = call_llm_json(LIBRARIAN_SYSTEM, user_prompt)

    # 解析 doc_type，若 LLM 返回值不在合法枚举中则降级为 OTHER 并记录警告
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

    # 解析 estimated_value，若 LLM 返回值不在合法枚举中则降级为 MEDIUM
    raw_value = data.get("estimated_value", "MEDIUM")
    estimated_value = _VALUE_MAP.get(raw_value)
    if estimated_value is None:
        log.warning(
            "librarian_value_fallback",
            doc_id=doc.doc_id,
            raw_value=raw_value,
        )
        estimated_value = EstimatedValue.MEDIUM

    # 组装最终结果，将实体列表中的每个 dict 转为 MentionedEntity 对象
    result = LibrarianResult(
        doc_type=doc_type,
        version_id=data.get("version_id"),
        key_topics=data.get("key_topics", []),
        mentioned_entities=[
            MentionedEntity(**e) for e in data.get("mentioned_entities", [])
        ],
        is_conversational=data.get("is_conversational", False),
        estimated_value=estimated_value,
    )

    log.info(
        "librarian_done",
        doc_id=doc.doc_id,
        doc_type=result.doc_type.value,
        topics=result.key_topics,
        entity_count=len(result.mentioned_entities),
    )
    return result
