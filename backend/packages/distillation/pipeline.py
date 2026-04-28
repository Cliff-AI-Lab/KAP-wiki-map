"""知识蒸馏管线 — 编排三级 Agent 协同处理。

流程：noise_filter → librarian → (分组) → conflict_auditor → judge → refiner → 入库

OPT-11: 每个 Agent step 内使用 ThreadPoolExecutor 并行处理多篇文档，
        step 间依赖顺序不变。
"""

from __future__ import annotations

import time
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from packages.common import get_logger, settings
from packages.common.exceptions import DistillationError, LLMCallError
from packages.common.types import (
    AuditResult,
    Decision,
    DocStatus,
    JudgeResult,
    LibrarianResult,
    RawDocument,
    RefinedResult,
)
from packages.storage.metadata_store import REVIEW_CONFIDENCE_THRESHOLD
from packages.distillation.agents.conflict_auditor import run_conflict_auditor
from packages.distillation.agents.judge import run_judge
from packages.distillation.agents.librarian import run_librarian
from packages.distillation.agents.refiner import run_refiner
from packages.distillation.classifiers.noise_filter import is_noise_document

log = get_logger("pipeline")


@dataclass
class PipelineResult:
    """单个文档的管线处理结果。"""
    doc_id: str
    title: str
    is_noise: bool = False
    librarian_result: LibrarianResult | None = None
    audit_result: AuditResult | None = None
    judge_result: JudgeResult | None = None
    refined_result: RefinedResult | None = None
    decision: Decision | None = None
    needs_review: bool = False
    error: str | None = None


@dataclass
class BatchPipelineResult:
    """批量处理结果。"""
    results: list[PipelineResult] = field(default_factory=list)
    total: int = 0
    kept: int = 0
    archived: int = 0
    discarded: int = 0
    pending_review: int = 0
    noise_filtered: int = 0
    errors: int = 0


# ── 并行 wrapper 函数 ──────────────────────────────────
# 每个 wrapper 捕获异常，返回 (doc_id, result, error) 三元组，
# 不会因单篇文档失败导致整批中断。


def _run_librarian_safe(doc: RawDocument) -> tuple[str, LibrarianResult | None, str | None]:
    """线程安全的 Librarian 调用。"""
    try:
        result = run_librarian(doc)
        return (doc.doc_id, result, None)
    except LLMCallError as e:
        return (doc.doc_id, None, f"Librarian LLM 调用失败: {e}")
    except (ValueError, KeyError) as e:
        return (doc.doc_id, None, f"Librarian 数据解析失败: {e}")
    except Exception as e:
        return (doc.doc_id, None, f"Librarian 未知错误: {e}")


def _run_auditor_safe(
    topic: str, group_docs: list[RawDocument], librarian_meta: dict[str, LibrarianResult]
) -> tuple[str, AuditResult | None, str | None]:
    """线程安全的 Conflict Auditor 调用。"""
    try:
        audit = run_conflict_auditor(topic, group_docs, librarian_meta)
        return (topic, audit, None)
    except LLMCallError as e:
        return (topic, None, f"Auditor LLM 失败: {e}")
    except Exception as e:
        return (topic, None, f"Auditor 未知错误: {e}")


def _run_judge_safe(
    doc: RawDocument,
    librarian_result: LibrarianResult,
    audit_result: AuditResult | None,
) -> tuple[str, JudgeResult | None, str | None]:
    """线程安全的 Judge 调用。"""
    try:
        result = run_judge(doc, librarian_result, audit_result)
        return (doc.doc_id, result, None)
    except LLMCallError as e:
        return (doc.doc_id, None, f"Judge LLM 调用失败: {e}")
    except Exception as e:
        return (doc.doc_id, None, f"Judge 未知错误: {e}")


def _run_refiner_safe(
    doc: RawDocument,
    librarian_result: LibrarianResult,
    domain_list_text: str = "",
) -> tuple[str, RefinedResult | None, str | None]:
    """线程安全的 Refiner 调用。"""
    try:
        result = run_refiner(doc, librarian_result, domain_list_text=domain_list_text)
        return (doc.doc_id, result, None)
    except LLMCallError as e:
        return (doc.doc_id, None, f"Refiner LLM 调用失败 (非致命): {e}")
    except Exception as e:
        return (doc.doc_id, None, f"Refiner 未知错误 (非致命): {e}")


# ── 主管线 ──────────────────────────────────────────────


def run_pipeline(
    documents: list[RawDocument],
    domain_list_text: str = "",
) -> BatchPipelineResult:
    """
    运行完整的知识蒸馏管线。

    Args:
        domain_list_text: 项目级知识域列表文本，传给 Refiner 做 domain_id 匹配。

    流程：
    1. 噪音过滤（规则引擎，快速前置）
    2. Librarian Agent（元数据提取）— 并行
    3. 按主题分组
    4. Conflict Auditor（组内冲突检测）— 并行
    5. Judge Agent（价值评估决策）— 并行
    6. Refiner Agent（仅对 KEEP 的文档提炼）— 并行

    OPT-11: Step 2/4/5/6 使用 ThreadPoolExecutor 并行化。
    """
    t_start = time.monotonic()
    max_workers = settings.pipeline_max_workers
    batch = BatchPipelineResult(total=len(documents))
    pipeline_results: dict[str, PipelineResult] = {}
    librarian_meta: dict[str, LibrarianResult] = {}
    surviving_docs: list[RawDocument] = []

    log.info("pipeline_start", total_docs=len(documents), max_workers=max_workers)

    # ── Step 1: 噪音过滤 ─────────────────────────────
    t_step = time.monotonic()
    log.info("pipeline_step", step="noise_filter")
    for doc in documents:
        pr = PipelineResult(doc_id=doc.doc_id, title=doc.title)
        if is_noise_document(doc):
            pr.is_noise = True
            pr.decision = Decision.DISCARD
            batch.noise_filtered += 1
            batch.discarded += 1
            log.info("noise_filtered", doc_id=doc.doc_id, title=doc.title)
        else:
            surviving_docs.append(doc)
        pipeline_results[doc.doc_id] = pr

    log.info(
        "noise_filter_done",
        filtered=batch.noise_filtered,
        surviving=len(surviving_docs),
        elapsed_ms=_elapsed_ms(t_step),
    )

    # ── Step 2: Librarian Agent（并行）──────────────────
    t_step = time.monotonic()
    log.info("pipeline_step", step="librarian", doc_count=len(surviving_docs))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_run_librarian_safe, doc): doc
            for doc in surviving_docs
        }
        for future in as_completed(futures):
            doc_id, result, error = future.result()
            pr = pipeline_results[doc_id]
            if error:
                pr.error = error
                batch.errors += 1
                log.error("librarian_failed", doc_id=doc_id, error=error)
            else:
                pr.librarian_result = result
                librarian_meta[doc_id] = result

    log.info(
        "librarian_done",
        success=len(librarian_meta),
        errors=batch.errors,
        elapsed_ms=_elapsed_ms(t_step),
    )

    # ── Step 3: 按主题分组 ───────────────────────────
    topic_groups: dict[str, list[RawDocument]] = defaultdict(list)
    for doc in surviving_docs:
        meta = librarian_meta.get(doc.doc_id)
        if meta and meta.key_topics:
            primary_topic = meta.key_topics[0]
        else:
            primary_topic = "__ungrouped__"
        topic_groups[primary_topic].append(doc)

    log.info("topic_grouping_done", group_count=len(topic_groups))

    # ── Step 4: Conflict Auditor（并行）─────────────────
    # 仅对同主题且 >= 2 篇文档的组触发审计；跳过无法分组的文档
    t_step = time.monotonic()
    log.info("pipeline_step", step="conflict_auditor")
    audit_results: dict[str, AuditResult] = {}

    auditable_groups = [
        (topic, group_docs)
        for topic, group_docs in topic_groups.items()
        if topic != "__ungrouped__" and len(group_docs) >= 2
    ]

    skipped_groups = len(topic_groups) - len(auditable_groups)
    if skipped_groups:
        log.info("auditor_groups_skipped", count=skipped_groups)

    if auditable_groups:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    _run_auditor_safe, topic, group_docs, librarian_meta
                ): (topic, group_docs)
                for topic, group_docs in auditable_groups
            }
            for future in as_completed(futures):
                topic, audit, error = future.result()
                if error:
                    log.warning("auditor_failed", topic=topic, error=error)
                elif audit:
                    _, group_docs = futures[future]
                    for gd in group_docs:
                        audit_results[gd.doc_id] = audit

    log.info(
        "auditor_done",
        audited_groups=len(auditable_groups),
        elapsed_ms=_elapsed_ms(t_step),
    )

    # ── Step 5: Judge Agent（并行）──────────────────────
    t_step = time.monotonic()
    log.info("pipeline_step", step="judge")

    judgeable_docs = [
        doc for doc in surviving_docs
        if not pipeline_results[doc.doc_id].error
        and pipeline_results[doc.doc_id].librarian_result is not None
    ]

    keep_docs: list[RawDocument] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _run_judge_safe,
                doc,
                pipeline_results[doc.doc_id].librarian_result,
                audit_results.get(doc.doc_id),
            ): doc
            for doc in judgeable_docs
        }
        for future in as_completed(futures):
            doc = futures[future]
            doc_id, judge, error = future.result()
            pr = pipeline_results[doc_id]

            if error:
                pr.error = error
                # 降级处理：Judge 失败时保守保留
                pr.decision = Decision.KEEP
                batch.kept += 1
                keep_docs.append(doc)
                batch.errors += 1
                log.error("judge_failed", doc_id=doc_id, error=error)
                continue

            pr.judge_result = judge
            pr.audit_result = audit_results.get(doc_id)

            # M0-tech-debt 坑 3：优先用新 decide() 标记的 needs_review；
            # 兼容旧路径：若 needs_review 未标记，回退到置信度阈值判断
            should_review = judge.needs_review or (
                judge.confidence < REVIEW_CONFIDENCE_THRESHOLD
            )
            if should_review:
                pr.decision = judge.decision
                pr.needs_review = True
                batch.pending_review += 1
                keep_docs.append(doc)
                log.info(
                    "judge_needs_review",
                    doc_id=doc_id,
                    confidence=judge.confidence,
                    proposed_decision=judge.decision.value,
                    rule_hit=judge.rule_hit,
                    reason=judge.decision_reason,
                )
            elif judge.decision == Decision.KEEP:
                pr.decision = judge.decision
                batch.kept += 1
                keep_docs.append(doc)
            elif judge.decision == Decision.ARCHIVE:
                pr.decision = judge.decision
                batch.archived += 1
            else:
                pr.decision = judge.decision
                batch.discarded += 1

    log.info(
        "judge_done",
        judged=len(judgeable_docs),
        kept=batch.kept,
        elapsed_ms=_elapsed_ms(t_step),
    )

    # ── Step 6: Refiner Agent（仅 KEEP，并行）────────────
    t_step = time.monotonic()
    refineable_docs = [
        doc for doc in keep_docs
        if pipeline_results[doc.doc_id].librarian_result is not None
    ]
    log.info("pipeline_step", step="refiner", keep_count=len(refineable_docs))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _run_refiner_safe,
                doc,
                pipeline_results[doc.doc_id].librarian_result,
                domain_list_text,
            ): doc
            for doc in refineable_docs
        }
        for future in as_completed(futures):
            doc_id, refined, error = future.result()
            pr = pipeline_results[doc_id]
            if error:
                pr.error = error
                batch.errors += 1
                log.warning("refiner_failed", doc_id=doc_id, error=error)
            else:
                pr.refined_result = refined

    log.info(
        "refiner_done",
        refined=len(refineable_docs),
        elapsed_ms=_elapsed_ms(t_step),
    )

    batch.results = list(pipeline_results.values())

    total_ms = _elapsed_ms(t_start)
    log.info(
        "pipeline_done",
        total=batch.total,
        kept=batch.kept,
        archived=batch.archived,
        discarded=batch.discarded,
        pending_review=batch.pending_review,
        noise_filtered=batch.noise_filtered,
        errors=batch.errors,
        total_elapsed_ms=total_ms,
    )
    return batch


def _elapsed_ms(start: float) -> int:
    """计算自 start 以来的耗时（毫秒）。"""
    return int((time.monotonic() - start) * 1000)
