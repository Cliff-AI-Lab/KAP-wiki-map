"""文档分片器 — 支持固定长度、父子分段、语义切片三种策略。"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Optional

from packages.common import get_logger, settings
from packages.common.types import ChunkStrategy, KnowledgeChunk

log = get_logger("storage.chunker")


def chunk_document(
    doc_id: str,
    content: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
    category_path: str = "",
    doc_type: str = "",
    source_system: str = "",
    updated_at: datetime | None = None,
    strategy: str | None = None,
    org_id: str = "default",
    domain_id: str = "",
) -> list[KnowledgeChunk]:
    """
    将文档内容切分为知识切片。

    strategy 可选值: "fixed", "parent_child", "semantic"。
    默认从 settings.chunk_strategy 获取。
    """
    if not content.strip():
        return []

    effective_strategy = strategy or settings.chunk_strategy

    common_kwargs = dict(
        doc_id=doc_id,
        category_path=category_path,
        doc_type=doc_type,
        source_system=source_system,
        updated_at=updated_at,
        org_id=org_id,
        domain_id=domain_id,
    )

    if effective_strategy == ChunkStrategy.PARENT_CHILD.value:
        return _chunk_parent_child(content, **common_kwargs)
    elif effective_strategy == ChunkStrategy.SEMANTIC.value:
        return _chunk_semantic(content, **common_kwargs)
    else:
        return _chunk_fixed(
            content,
            chunk_size=chunk_size or settings.chunk_size,
            overlap=overlap or settings.chunk_overlap,
            **common_kwargs,
        )


# ── 固定长度切片 ──────────────────────────────────────


def _chunk_fixed(
    content: str,
    doc_id: str,
    chunk_size: int,
    overlap: int,
    **kwargs,
) -> list[KnowledgeChunk]:
    """固定长度滑动窗口切片 — 增强了句子边界感知。"""
    chunks = []
    start = 0
    idx = 0

    while start < len(content):
        end = start + chunk_size

        # 句子边界感知：尝试在句号/问号等位置切分
        if end < len(content):
            end = _find_sentence_boundary(content, end, chunk_size)

        text = content[start:end]

        if not text.strip():
            start = end - overlap
            continue

        chunk_id = _make_chunk_id(doc_id, idx)
        chunks.append(
            KnowledgeChunk(
                chunk_id=chunk_id,
                doc_id=doc_id,
                chunk_index=idx,
                content=text,
                chunk_strategy=ChunkStrategy.FIXED.value,
                **kwargs,
            )
        )
        idx += 1
        start = end - overlap
        if start >= len(content):
            break

    return chunks


# ── 父子分段切片 ──────────────────────────────────────


def _chunk_parent_child(
    content: str,
    doc_id: str,
    **kwargs,
) -> list[KnowledgeChunk]:
    """
    父子分段策略:
    1. 按标题/分隔符切分为 parent chunks
    2. 每个 parent chunk 再切分为 child chunks
    3. 双层结构，child 携带 parent_chunk_id
    """
    parent_size = settings.parent_chunk_size
    child_size = settings.child_chunk_size
    chunks = []
    idx = 0

    sections = _split_by_sections(content, parent_size)

    for sec_idx, section_text in enumerate(sections):
        if not section_text.strip():
            continue

        parent_id = _make_chunk_id(doc_id, f"p{sec_idx}")

        # 发出父切片
        chunks.append(
            KnowledgeChunk(
                chunk_id=parent_id,
                doc_id=doc_id,
                chunk_index=idx,
                content=section_text,
                chunk_strategy=ChunkStrategy.PARENT_CHILD.value,
                is_parent=True,
                **kwargs,
            )
        )
        idx += 1

        # 在父切片内细分为子切片
        child_start = 0
        child_idx = 0
        while child_start < len(section_text):
            child_end = min(child_start + child_size, len(section_text))
            if child_end < len(section_text):
                child_end = _find_sentence_boundary(
                    section_text, child_end, child_size
                )
            child_text = section_text[child_start:child_end]

            if child_text.strip():
                child_chunk_id = _make_chunk_id(doc_id, f"p{sec_idx}c{child_idx}")
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=child_chunk_id,
                        doc_id=doc_id,
                        chunk_index=idx,
                        content=child_text,
                        parent_chunk_id=parent_id,
                        chunk_strategy=ChunkStrategy.PARENT_CHILD.value,
                        is_parent=False,
                        **kwargs,
                    )
                )
                idx += 1
                child_idx += 1

            child_start = child_end

    return chunks


# ── 语义切片 ──────────────────────────────────────────


def _chunk_semantic(
    content: str,
    doc_id: str,
    **kwargs,
) -> list[KnowledgeChunk]:
    """
    语义切片: 按语义段落切分，基于 embedding 相似度检测边界。
    当相邻句子的相似度低于阈值时切分。
    """
    from packages.storage.embedder import embed_texts

    threshold = settings.semantic_threshold
    min_size = settings.semantic_min_chunk_size
    max_size = settings.semantic_max_chunk_size

    sentences = _split_sentences(content)
    if len(sentences) <= 1:
        return _chunk_fixed(
            content,
            doc_id=doc_id,
            chunk_size=settings.chunk_size,
            overlap=settings.chunk_overlap,
            **kwargs,
        )

    # 获取所有句子的 embedding
    embeddings = embed_texts(sentences)

    # 计算相邻句子的余弦相似度
    import numpy as np

    similarities = []
    for i in range(len(embeddings) - 1):
        a = np.array(embeddings[i])
        b = np.array(embeddings[i + 1])
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            similarities.append(0.0)
        else:
            similarities.append(float(np.dot(a, b) / (norm_a * norm_b)))

    # 基于相似度分组句子
    chunks = []
    current_sentences = [sentences[0]]
    current_len = len(sentences[0])
    idx = 0

    for i, sim in enumerate(similarities):
        next_sentence = sentences[i + 1]

        # 切分条件：相似度低于阈值且当前块 >= 最小值，或当前块将超过最大值
        if (sim < threshold and current_len >= min_size) or \
           (current_len + len(next_sentence) > max_size):
            chunk_text = "".join(current_sentences)
            if chunk_text.strip():
                chunk_id = _make_chunk_id(doc_id, f"s{idx}")
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=chunk_id,
                        doc_id=doc_id,
                        chunk_index=idx,
                        content=chunk_text,
                        chunk_strategy=ChunkStrategy.SEMANTIC.value,
                        **kwargs,
                    )
                )
                idx += 1
            current_sentences = [next_sentence]
            current_len = len(next_sentence)
        else:
            current_sentences.append(next_sentence)
            current_len += len(next_sentence)

    # 发出最后一个切片
    if current_sentences:
        chunk_text = "".join(current_sentences)
        if chunk_text.strip():
            chunk_id = _make_chunk_id(doc_id, f"s{idx}")
            chunks.append(
                KnowledgeChunk(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    chunk_index=idx,
                    content=chunk_text,
                    chunk_strategy=ChunkStrategy.SEMANTIC.value,
                    **kwargs,
                )
            )

    return chunks


# ── 辅助函数 ──────────────────────────────────────────


def _make_chunk_id(doc_id: str, index: int | str) -> str:
    raw = f"{doc_id}::{index}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _find_sentence_boundary(text: str, pos: int, chunk_size: int) -> int:
    """在 pos 附近向前回溯查找最近的句子边界。"""
    search_window = min(int(chunk_size * 0.2), 100)
    search_start = max(pos - search_window, 0)

    for boundary_char in ["。", "！", "？", ".", "!", "?", "\n"]:
        last_idx = text.rfind(boundary_char, search_start, pos)
        if last_idx > search_start:
            return last_idx + 1

    return pos  # 未找到边界，使用原始位置


def _split_sentences(text: str) -> list[str]:
    """按中英文标点将文本分割为句子，保留分隔符。"""
    pattern = r"((?:[^。！？.!?\n]+[。！？.!?\n])|(?:[^。！？.!?\n]+$))"
    parts = re.findall(pattern, text)
    return [p for p in parts if p.strip()]


def _split_by_sections(text: str, max_section_size: int) -> list[str]:
    """按 markdown 标题或双换行分段。超长段落按段落拆分。"""
    # 尝试按 markdown 标题分段
    heading_pattern = r"(?=^#{1,4}\s)"
    sections = re.split(heading_pattern, text, flags=re.MULTILINE)

    if len(sections) <= 1:
        # Fallback: 按双换行分段
        sections = re.split(r"\n\n+", text)

    result = []
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        if len(sec) <= max_section_size:
            result.append(sec)
        else:
            # 超长段落按行拆分
            paras = sec.split("\n")
            current = ""
            for para in paras:
                if len(current) + len(para) > max_section_size and current:
                    result.append(current.strip())
                    current = para + "\n"
                else:
                    current += para + "\n"
            if current.strip():
                result.append(current.strip())

    return result


# ── 上下文窗口（M22 #3）─────────────────────────────────


def build_context_window(
    chunks: list[KnowledgeChunk],
    target_chunk_id: str,
    window_size: int | None = None,
    max_chars: int = 1500,
) -> str:
    """构造目标 chunk 的"上下文窗口" — 前后各 N 个 chunk 的内容拼接。

    给 LLM 抽实体 / 关系时附加, 让模型看到表/图/公式周围的文字, 大幅减少
    "孤立 chunk 推不出实体类型" 的误抽。

    Args:
        chunks: 同文档所有 chunks（已按 chunk_index 排序）
        target_chunk_id: 目标 chunk 的 chunk_id
        window_size: 前后各取 N 个 chunk; None 时读 settings.context_window_size
        max_chars: 上下文总字符上限, 超长截断（防 prompt 爆掉）

    Returns:
        拼好的上下文文本; 找不到目标 chunk 或 window_size=0 时返回空串
    """
    if window_size is None:
        window_size = settings.context_window_size
    if window_size <= 0:
        return ""

    # 找目标 chunk 在列表中的位置（按 chunk_index 而非 chunk_id 排序后查 id）
    sorted_chunks = sorted(chunks, key=lambda c: c.chunk_index)
    target_idx = next(
        (i for i, c in enumerate(sorted_chunks) if c.chunk_id == target_chunk_id),
        -1,
    )
    if target_idx < 0:
        return ""

    lo = max(0, target_idx - window_size)
    hi = min(len(sorted_chunks), target_idx + window_size + 1)

    parts: list[str] = []
    for i in range(lo, hi):
        if i == target_idx:
            continue  # 目标自身不算 context
        c = sorted_chunks[i]
        marker = "前文" if i < target_idx else "后文"
        parts.append(f"[{marker} chunk_index={c.chunk_index}]\n{c.content}")

    ctx = "\n\n".join(parts)
    if len(ctx) > max_chars:
        ctx = ctx[:max_chars] + " …(截断)"
    return ctx
