"""冲突检测预演（PRD F1.6 lite）— 用上传材料预演归类，找冲突 / 重复 / 孤立。

设计原则（feedback memory · AI native + 轻量化）：
- 函数式实现，单文件
- LLM 失败时降级关键词命中（不引入 embedding 依赖）
- M3 lite 不做完整 500 份预演（PRD F1.6.1 性能要求 ≤5min），聚焦 ≤50 份小批
- 重复检测用简单 title 标准化匹配（避免 Levenshtein 等额外依赖）

输出 PreviewReport：
- conflicts：同一文档落入 2+ 节点（双归争议）
- duplicates：高相似度文档对
- orphans：无法归入任一节点
- node_coverage：每节点关联文档数
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from packages.architect.prompts import (
    CLASSIFY_TO_NODE_SYSTEM,
    CLASSIFY_TO_NODE_USER,
)
from packages.common import get_logger
from packages.distillation.llm_client import acall_llm_json
from packages.templates.registry import TaxonomyNode

log = get_logger("architect.conflict_detector")


# ════════════════════════════════════════════════════════════════════════
#  Domain Types
# ════════════════════════════════════════════════════════════════════════


@dataclass
class DocSample:
    """一份待归类的文档样本。"""
    doc_id: str
    title: str
    summary: str = ""


@dataclass
class ClassifyResult:
    """单文档归类结果。"""
    doc_id: str
    primary_node_id: str = ""
    primary_confidence: float = 0.0
    secondary_node_id: str = ""
    secondary_confidence: float = 0.0
    unmatched: bool = False
    reasoning: str = ""


@dataclass
class ConflictItem:
    """同一文档落入 2+ 节点（双归争议）。"""
    doc_id: str
    doc_title: str
    nodes: list[tuple[str, float]]  # [(node_id, confidence), ...]


@dataclass
class DuplicateItem:
    """高相似度文档对。"""
    doc_id_a: str
    doc_id_b: str
    title_a: str
    title_b: str
    similarity_reason: str


@dataclass
class PreviewReport:
    """冲突预演完整报告（PRD F1.6 输出）。"""
    total_docs: int = 0
    classified_docs: int = 0          # 成功归类的文档数（含冲突）
    orphans: list[DocSample] = field(default_factory=list)
    conflicts: list[ConflictItem] = field(default_factory=list)
    duplicates: list[DuplicateItem] = field(default_factory=list)
    node_coverage: dict[str, int] = field(default_factory=dict)  # node_id → 文档数
    classify_results: list[ClassifyResult] = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════════
#  classify_doc — 单文档归类（LLM + 关键词降级）
# ════════════════════════════════════════════════════════════════════════


async def classify_doc(
    doc: DocSample,
    taxonomy: list[TaxonomyNode],
) -> ClassifyResult:
    """归类单文档到主树节点。LLM 失败降级关键词命中。"""
    nodes_text = "\n".join(
        f"- {n.id} ({n.name}): {n.description[:50]}"
        for n in taxonomy
    )
    user_prompt = CLASSIFY_TO_NODE_USER.format(
        taxonomy_nodes=nodes_text,
        doc_title=doc.title[:120],
        doc_summary=doc.summary[:300] or doc.title,
    )

    try:
        data = await acall_llm_json(CLASSIFY_TO_NODE_SYSTEM, user_prompt)
    except Exception as e:
        log.warning("classify_llm_failed_fallback", doc_id=doc.doc_id, error=str(e))
        return _fallback_keyword_classify(doc, taxonomy)

    valid_ids = {n.id for n in taxonomy}
    primary = (data.get("primary_node_id") or "").strip()
    if primary and primary not in valid_ids:
        primary = ""
    secondary = (data.get("secondary_node_id") or "").strip()
    if secondary and secondary not in valid_ids:
        secondary = ""

    try:
        p_conf = max(0.0, min(1.0, float(data.get("primary_confidence", 0))))
    except (TypeError, ValueError):
        p_conf = 0.0
    try:
        s_conf = max(0.0, min(1.0, float(data.get("secondary_confidence", 0))))
    except (TypeError, ValueError):
        s_conf = 0.0

    unmatched = bool(data.get("unmatched", False)) or (
        not primary and not secondary
    )

    return ClassifyResult(
        doc_id=doc.doc_id,
        primary_node_id=primary,
        primary_confidence=p_conf,
        secondary_node_id=secondary,
        secondary_confidence=s_conf,
        unmatched=unmatched,
        reasoning=str(data.get("reasoning", ""))[:200],
    )


def _fallback_keyword_classify(
    doc: DocSample,
    taxonomy: list[TaxonomyNode],
) -> ClassifyResult:
    """关键词命中降级（LLM 失败时用）。子串匹配 doc.title + doc.summary。"""
    text = f"{doc.title} {doc.summary}"
    best: tuple[str, int] = ("", 0)
    second: tuple[str, int] = ("", 0)

    for n in taxonomy:
        # 关键词命中度 = 节点名字 + 描述出现在 text 的次数
        score = 0
        if n.name and n.name in text:
            score += 2
        for w in (n.description or "").split():
            if len(w) >= 2 and w in text:
                score += 1
        if score > best[1]:
            second = best
            best = (n.id, score)
        elif score > second[1]:
            second = (n.id, score)

    if best[1] == 0:
        return ClassifyResult(doc_id=doc.doc_id, unmatched=True,
                              reasoning="关键词降级：无任何节点命中")

    p_conf = min(1.0, best[1] / 6.0)  # 6 命中点视为高置信
    return ClassifyResult(
        doc_id=doc.doc_id,
        primary_node_id=best[0],
        primary_confidence=p_conf,
        secondary_node_id=second[0] if second[1] >= 2 else "",
        secondary_confidence=min(1.0, second[1] / 6.0) if second[1] >= 2 else 0.0,
        reasoning=f"关键词降级 hit={best[1]}",
    )


# ════════════════════════════════════════════════════════════════════════
#  detect_duplicates — 简单标题标准化匹配
# ════════════════════════════════════════════════════════════════════════


_TITLE_NORMALIZE = re.compile(r"[\s_\-\(\)（）\[\]【】v\d\.]+")


def _normalize_title(title: str) -> str:
    """标题标准化（去版本号、去特殊符号、去空白）便于重复检测。"""
    return _TITLE_NORMALIZE.sub("", title.lower())


def detect_duplicates(docs: list[DocSample]) -> list[DuplicateItem]:
    """简单标题标准化匹配（M3 lite；M4 接 embedding 相似度）。

    标准化后相同的文档对视为可能重复。
    """
    if len(docs) < 2:
        return []
    by_normalized: dict[str, list[DocSample]] = {}
    for doc in docs:
        norm = _normalize_title(doc.title)
        if not norm:
            continue
        by_normalized.setdefault(norm, []).append(doc)

    out: list[DuplicateItem] = []
    for norm, group in by_normalized.items():
        if len(group) < 2:
            continue
        # 把同组内的两两配对（lite：仅与第一份对比，避免 N² 爆炸）
        head = group[0]
        for other in group[1:]:
            out.append(DuplicateItem(
                doc_id_a=head.doc_id,
                doc_id_b=other.doc_id,
                title_a=head.title,
                title_b=other.title,
                similarity_reason=f"标题标准化后相同（norm={norm}）",
            ))
    return out


# ════════════════════════════════════════════════════════════════════════
#  preview_classification — 完整预演（PRD F1.6.1）
# ════════════════════════════════════════════════════════════════════════


_CONFLICT_THRESHOLD = 0.5


async def preview_classification(
    docs: list[DocSample],
    taxonomy: list[TaxonomyNode],
) -> PreviewReport:
    """对一批样本预演归类，输出 PreviewReport（PRD F1.6 输出）。

    M3 lite：顺序归类（避免 LLM 限流）。M4 加 asyncio.gather 限并发。
    """
    report = PreviewReport(total_docs=len(docs))

    if not taxonomy:
        report.orphans = list(docs)
        return report

    for doc in docs:
        result = await classify_doc(doc, taxonomy)
        report.classify_results.append(result)

        if result.unmatched or (
            not result.primary_node_id
            and not result.secondary_node_id
        ):
            report.orphans.append(doc)
            continue

        report.classified_docs += 1

        # 节点覆盖度
        if result.primary_node_id:
            report.node_coverage[result.primary_node_id] = (
                report.node_coverage.get(result.primary_node_id, 0) + 1
            )

        # 双归冲突
        if (
            result.primary_node_id
            and result.secondary_node_id
            and result.primary_confidence >= _CONFLICT_THRESHOLD
            and result.secondary_confidence >= _CONFLICT_THRESHOLD
        ):
            report.conflicts.append(ConflictItem(
                doc_id=doc.doc_id,
                doc_title=doc.title,
                nodes=[
                    (result.primary_node_id, result.primary_confidence),
                    (result.secondary_node_id, result.secondary_confidence),
                ],
            ))
            # secondary 也记入 coverage
            report.node_coverage[result.secondary_node_id] = (
                report.node_coverage.get(result.secondary_node_id, 0) + 1
            )

    # 重复检测
    report.duplicates = detect_duplicates(docs)

    log.info(
        "conflict_preview_done",
        total=report.total_docs,
        classified=report.classified_docs,
        orphans=len(report.orphans),
        conflicts=len(report.conflicts),
        duplicates=len(report.duplicates),
    )
    return report
