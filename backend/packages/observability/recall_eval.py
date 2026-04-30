"""召回率评估管线（M8 #2 · 决策书 §5.3 准确率/召回率维度）。

工作流：
1. SME 上传 GroundTruthQuery 集（query_text + 期望 doc_ids）
2. 调 ``run_recall_eval`` 注入 qa_callable，遍历 ground truth：
   对每个 gt_query 调 qa → 取 top_k → 计算 recall@k / precision@k / F1
3. 聚合 RecallEvalReport（avg_recall / avg_precision / avg_f1 + per-query 详情）
4. 报告快照保存（按 project + version 索引），dashboard / 趋势分析用

设计（feedback memory · 轻量化 + AI native）：
- 函数式实现，注入式 qa_callable 便于 mock + 解耦真实引擎
- 内存模式（M9 PG 持久化）
- 单 query 失败不阻断（最多 0 召回，不抛异常）
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Awaitable, Callable

from pydantic import BaseModel, Field

from packages.common import get_logger

log = get_logger("observability.recall_eval")


# ════════════════════════════════════════════════════════════════════════
#  数据模型
# ════════════════════════════════════════════════════════════════════════


class GroundTruthQuery(BaseModel):
    """SME 标注的 ground truth 查询（query_text + 期望返回的 doc_ids）。"""
    gt_id: str
    project_id: str = ""
    query_text: str
    expected_doc_ids: list[str] = Field(default_factory=list)
    note: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))


class RecallEvalDetail(BaseModel):
    """单条 ground truth 评估明细。"""
    gt_id: str
    query_text: str
    expected_count: int
    retrieved_count: int       # 实际返回的 top_k 数量
    matched_count: int         # 期望 ∩ 实际
    recall: float              # matched / expected
    precision: float           # matched / retrieved
    f1: float


class RecallEvalReport(BaseModel):
    report_id: str
    project_id: str = ""
    version: str = ""          # 关联本体版本（M3+M5 演化语境）
    k: int = 5
    total_queries: int = 0
    avg_recall: float = 0.0
    avg_precision: float = 0.0
    avg_f1: float = 0.0
    details: list[RecallEvalDetail] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))


# ════════════════════════════════════════════════════════════════════════
#  内存存储
# ════════════════════════════════════════════════════════════════════════

_ground_truth: dict[str, GroundTruthQuery] = {}
_reports: list[RecallEvalReport] = []

# M9 #1 · PG 持久化 sinks（async；通过 set_*_sink 注入）
_gt_sink: Callable[[GroundTruthQuery], Awaitable[None]] | None = None
_gt_remove_sink: Callable[[str], Awaitable[None]] | None = None
_report_sink: Callable[[RecallEvalReport], Awaitable[None]] | None = None


def reset_recall_eval_for_test() -> None:
    global _gt_sink, _gt_remove_sink, _report_sink
    _ground_truth.clear()
    _reports.clear()
    _gt_sink = None
    _gt_remove_sink = None
    _report_sink = None


def set_recall_eval_pg_sinks(
    *,
    gt_sink: Callable[[GroundTruthQuery], Awaitable[None]] | None = None,
    gt_remove_sink: Callable[[str], Awaitable[None]] | None = None,
    report_sink: Callable[[RecallEvalReport], Awaitable[None]] | None = None,
) -> None:
    """注入三个 sink（pg_recall_eval.initialize 内部调用）。"""
    global _gt_sink, _gt_remove_sink, _report_sink
    _gt_sink = gt_sink
    _gt_remove_sink = gt_remove_sink
    _report_sink = report_sink


def _fire_and_forget(coro_factory) -> None:
    """通用 fire-and-forget 工具：有 loop 时 create_task，无则跳过。"""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro_factory())
    except RuntimeError:
        pass


# ── ground truth CRUD ──


def add_ground_truth(
    *,
    project_id: str = "",
    query_text: str,
    expected_doc_ids: list[str],
    note: str = "",
) -> GroundTruthQuery:
    gt = GroundTruthQuery(
        gt_id=f"gt_{uuid.uuid4().hex[:10]}",
        project_id=project_id,
        query_text=query_text[:500],
        expected_doc_ids=list(expected_doc_ids),
        note=note[:200],
    )
    _ground_truth[gt.gt_id] = gt
    log.info("ground_truth_added",
             gt_id=gt.gt_id, project_id=project_id,
             expected=len(expected_doc_ids))
    if _gt_sink is not None:
        _fire_and_forget(lambda: _gt_sink(gt))
    return gt


def list_ground_truth(
    *, project_id: str | None = None,
) -> list[GroundTruthQuery]:
    out = list(_ground_truth.values())
    if project_id is not None:
        out = [g for g in out if g.project_id == project_id]
    return sorted(out, key=lambda g: g.created_at, reverse=True)


def get_ground_truth(gt_id: str) -> GroundTruthQuery | None:
    return _ground_truth.get(gt_id)


def remove_ground_truth(gt_id: str) -> bool:
    removed = _ground_truth.pop(gt_id, None) is not None
    if removed and _gt_remove_sink is not None:
        _fire_and_forget(lambda: _gt_remove_sink(gt_id))
    return removed


# ── 评估 ──


# qa_callable 协议：接受 query_text + top_k，返回 doc_ids list
QaCallable = Callable[[str, int], Awaitable[list[str]]]


def _safe_div(num: float, den: float) -> float:
    return round(num / den, 4) if den > 0 else 0.0


async def run_recall_eval(
    *,
    qa_callable: QaCallable,
    project_id: str = "",
    version: str = "",
    k: int = 5,
) -> RecallEvalReport:
    """对当前 project 全部 ground truth 跑评估，返回报告（并 stash 入 _reports）。

    Args:
        qa_callable: async (query_text, k) -> [doc_id]，由调用方注入（生产传 qa_engine 包装；测试传 fake）
        project_id: 仅评估该 project 的 ground truth；"" = 全部
        version: 关联本体版本（仅记录，不影响 qa）
        k: top_k
    """
    targets = list_ground_truth(project_id=project_id or None)

    details: list[RecallEvalDetail] = []
    sum_recall = 0.0
    sum_precision = 0.0
    sum_f1 = 0.0

    for gt in targets:
        try:
            retrieved = await qa_callable(gt.query_text, k)
            if not isinstance(retrieved, list):
                retrieved = []
            retrieved = [str(d) for d in retrieved[:k]]
        except Exception as e:
            log.warning("recall_eval_qa_failed",
                        gt_id=gt.gt_id, error=str(e))
            retrieved = []

        expected_set = set(gt.expected_doc_ids)
        retrieved_set = set(retrieved)
        matched = expected_set & retrieved_set

        recall = _safe_div(len(matched), len(expected_set))
        precision = _safe_div(len(matched), len(retrieved_set))
        f1 = (
            _safe_div(2 * recall * precision, recall + precision)
            if (recall + precision) > 0 else 0.0
        )

        details.append(RecallEvalDetail(
            gt_id=gt.gt_id,
            query_text=gt.query_text,
            expected_count=len(expected_set),
            retrieved_count=len(retrieved_set),
            matched_count=len(matched),
            recall=recall, precision=precision, f1=f1,
        ))
        sum_recall += recall
        sum_precision += precision
        sum_f1 += f1

    n = len(details) or 1
    report = RecallEvalReport(
        report_id=f"reval_{uuid.uuid4().hex[:10]}",
        project_id=project_id, version=version, k=k,
        total_queries=len(details),
        avg_recall=round(sum_recall / n, 4),
        avg_precision=round(sum_precision / n, 4),
        avg_f1=round(sum_f1 / n, 4),
        details=details,
    )
    _reports.append(report)
    log.info("recall_eval_done",
             report_id=report.report_id,
             total=report.total_queries,
             avg_recall=report.avg_recall,
             avg_precision=report.avg_precision)
    if _report_sink is not None:
        try:
            await _report_sink(report)
        except Exception as e:
            log.warning("recall_eval_report_pg_write_failed", error=str(e))
    return report


# ── reports 查询 ──


def list_reports(
    *, project_id: str | None = None, limit: int = 50,
) -> list[RecallEvalReport]:
    # 按插入顺序倒序（datetime.now 分辨率不足时 sort 失序，参考 decision_log）
    out: list[RecallEvalReport] = []
    for r in reversed(_reports):
        if project_id is not None and r.project_id != project_id:
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return out


def get_latest_report(
    *, project_id: str | None = None,
) -> RecallEvalReport | None:
    reports = list_reports(project_id=project_id, limit=1)
    return reports[0] if reports else None
