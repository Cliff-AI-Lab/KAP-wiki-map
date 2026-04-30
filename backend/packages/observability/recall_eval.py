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


# ════════════════════════════════════════════════════════════════════════
#  M9 #2 · 召回率趋势 + 告警阈值
# ════════════════════════════════════════════════════════════════════════


# 召回率跌破基线告警阈值（默认 -10pp）
_RECALL_DROP_ALERT_THRESHOLD = 0.10
# 精确率跌破基线告警阈值（默认 -10pp）
_PRECISION_DROP_ALERT_THRESHOLD = 0.10


def compute_recall_trend(
    *, project_id: str | None = None, lookback: int = 10,
) -> dict:
    """计算召回率趋势。

    Args:
        lookback: 回看最多 N 份 reports；baseline = 最早一份，current = 最新一份

    Returns:
        {
            "samples": int,
            "baseline": {report_id, avg_recall, avg_precision, avg_f1, created_at},
            "current": {...同上},
            "recall_delta": float,        # current - baseline (带符号)
            "precision_delta": float,
            "f1_delta": float,
            "recall_alert": bool,          # current 跌 > 阈值
            "precision_alert": bool,
            "alert_messages": list[str],
        }

    Notes:
        - reports < 2 份 → samples 字段返回，其它指标 0；alert 全部 False
    """
    reports = list_reports(project_id=project_id, limit=lookback)
    if len(reports) < 2:
        return {
            "samples": len(reports),
            "baseline": None, "current": None,
            "recall_delta": 0.0, "precision_delta": 0.0, "f1_delta": 0.0,
            "recall_alert": False, "precision_alert": False,
            "alert_messages": [],
        }

    # list_reports 倒序（newest first）→ baseline = 最早 = 末尾
    current = reports[0]
    baseline = reports[-1]

    recall_delta = round(current.avg_recall - baseline.avg_recall, 4)
    precision_delta = round(current.avg_precision - baseline.avg_precision, 4)
    f1_delta = round(current.avg_f1 - baseline.avg_f1, 4)

    alert_messages: list[str] = []
    recall_alert = recall_delta < -_RECALL_DROP_ALERT_THRESHOLD
    precision_alert = precision_delta < -_PRECISION_DROP_ALERT_THRESHOLD
    if recall_alert:
        alert_messages.append(
            f"召回率跌破基线 {abs(recall_delta):.1%} "
            f"(baseline={baseline.avg_recall:.2f} → current={current.avg_recall:.2f})"
        )
    if precision_alert:
        alert_messages.append(
            f"精确率跌破基线 {abs(precision_delta):.1%} "
            f"(baseline={baseline.avg_precision:.2f} → current={current.avg_precision:.2f})"
        )

    def _summary(r: RecallEvalReport) -> dict:
        return {
            "report_id": r.report_id,
            "avg_recall": r.avg_recall,
            "avg_precision": r.avg_precision,
            "avg_f1": r.avg_f1,
            "created_at": r.created_at.isoformat(),
        }

    return {
        "samples": len(reports),
        "baseline": _summary(baseline),
        "current": _summary(current),
        "recall_delta": recall_delta,
        "precision_delta": precision_delta,
        "f1_delta": f1_delta,
        "recall_alert": recall_alert,
        "precision_alert": precision_alert,
        "alert_messages": alert_messages,
    }


def list_projects_with_ground_truth() -> list[str]:
    """列出当前所有有 ground truth 集的 project_id（不含 ""）。"""
    seen: set[str] = set()
    for gt in _ground_truth.values():
        if gt.project_id:
            seen.add(gt.project_id)
    return sorted(seen)


class MultiKRecallReport(BaseModel):
    """多 K 召回曲线评估报告（M10 #1）。"""
    report_id: str
    project_id: str = ""
    version: str = ""
    ks: list[int]
    # k → avg_recall / avg_precision / avg_f1
    by_k: dict[int, dict[str, float]] = Field(default_factory=dict)
    total_queries: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))


async def run_multi_k_recall_eval(
    *,
    qa_callable: QaCallable,
    project_id: str = "",
    version: str = "",
    ks: list[int] | None = None,
) -> MultiKRecallReport:
    """对当前 project 全部 ground truth 跑多 K 评估，输出召回曲线。

    Args:
        ks: 要评估的 k 值列表，默认 [1, 3, 5, 10]

    Notes:
        - 单次拉最大 max(ks) 个结果，按 k 截断重算（节省 qa 调用次数）
        - 单 query 失败 → 该 query 各 K 都视为 0 召回
    """
    if not ks:
        ks = [1, 3, 5, 10]
    ks = sorted(set(int(x) for x in ks if int(x) > 0))
    max_k = max(ks)

    targets = list_ground_truth(project_id=project_id or None)
    by_k: dict[int, dict[str, float]] = {
        k: {"sum_recall": 0.0, "sum_precision": 0.0, "sum_f1": 0.0}
        for k in ks
    }

    for gt in targets:
        try:
            retrieved = await qa_callable(gt.query_text, max_k)
            if not isinstance(retrieved, list):
                retrieved = []
            retrieved = [str(d) for d in retrieved[:max_k]]
        except Exception as e:
            log.warning("multi_k_recall_qa_failed",
                        gt_id=gt.gt_id, error=str(e))
            retrieved = []

        expected_set = set(gt.expected_doc_ids)
        for k in ks:
            top_k = retrieved[:k]
            top_k_set = set(top_k)
            matched = expected_set & top_k_set
            r = _safe_div(len(matched), len(expected_set))
            p = _safe_div(len(matched), len(top_k_set))
            f = (
                _safe_div(2 * r * p, r + p)
                if (r + p) > 0 else 0.0
            )
            by_k[k]["sum_recall"] += r
            by_k[k]["sum_precision"] += p
            by_k[k]["sum_f1"] += f

    n = len(targets) or 1
    aggregated: dict[int, dict[str, float]] = {}
    for k in ks:
        aggregated[k] = {
            "avg_recall": round(by_k[k]["sum_recall"] / n, 4),
            "avg_precision": round(by_k[k]["sum_precision"] / n, 4),
            "avg_f1": round(by_k[k]["sum_f1"] / n, 4),
        }

    report = MultiKRecallReport(
        report_id=f"mreval_{uuid.uuid4().hex[:10]}",
        project_id=project_id, version=version,
        ks=ks, by_k=aggregated, total_queries=len(targets),
    )
    log.info("multi_k_recall_eval_done",
             report_id=report.report_id, ks=ks,
             total=report.total_queries)
    return report


# ════════════════════════════════════════════════════════════════════════
#  GroundTruth 自动构造（M10 #1）
# ════════════════════════════════════════════════════════════════════════


class GroundTruthCandidate(BaseModel):
    """从 query_log 反向构造的 gt 候选（待 SME 审批入库）。"""
    candidate_id: str
    project_id: str = ""
    query_text: str
    proposed_doc_ids: list[str] = Field(default_factory=list)
    sample_size: int = 0           # 满足条件的 query 实例数
    useful_rate: float = 0.0       # 该 query_text 的 useful 比例
    reasoning: str = ""


def _compute_proposed_doc_ids(
    useful_events: list,
    *, max_doc_ids: int,
    intersection_min_useful: int = 2,
) -> tuple[list[str], str]:
    """从 useful query 实例反向算 proposed doc_ids（M11 #1）。

    策略：
    1. 优先：≥ 2 个 useful 实例时取交集（每个实例都返回的 doc）
    2. 兜底：交集为空 / 仅 1 个 useful 实例 → 用频次降序的 union
    3. 都没有 retrieved_doc_ids → 返回空

    Returns:
        (proposed_doc_ids, strategy_label)
    """
    if not useful_events:
        return [], "no_useful"

    instance_doc_sets = [
        set(getattr(e, "retrieved_doc_ids", []) or []) for e in useful_events
    ]
    instance_doc_sets = [s for s in instance_doc_sets if s]
    if not instance_doc_sets:
        return [], "no_doc_ids"

    # 策略 1：交集
    if len(instance_doc_sets) >= intersection_min_useful:
        intersection = set.intersection(*instance_doc_sets)
        if intersection:
            return sorted(intersection)[:max_doc_ids], "intersection"

    # 策略 2：union 按频次降序
    freq: dict[str, int] = {}
    for s in instance_doc_sets:
        for d in s:
            freq[d] = freq.get(d, 0) + 1
    ranked = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)
    return [d for d, _ in ranked[:max_doc_ids]], "frequency_union"


def auto_construct_ground_truth_candidates(
    *,
    project_id: str = "",
    min_useful_rate: float = 0.8,
    min_samples: int = 2,
    max_doc_ids: int = 10,
) -> list[GroundTruthCandidate]:
    """从 query_log 反向构造 ground truth 候选。

    算法：
    1. 拉所有 query_text 出现 ≥ min_samples 次的查询
    2. 计算每组的 useful_rate（仅算有 feedback 的）
    3. useful_rate ≥ min_useful_rate → 候选
    4. proposed_doc_ids（M11 #1 完整化）：
       - 优先：useful=True 实例的 retrieved_doc_ids 交集
       - 兜底：union 按频次降序

    Returns:
        候选列表（待 SME 审批）；不直接入 ground_truth 集
    """
    from packages.observability.query_log import _queries  # type: ignore[reportPrivateUsage]

    # 按 (project_id, query_text) 分组
    groups: dict[tuple[str, str], list] = {}
    for q in _queries:
        if project_id and q.project_id != project_id:
            continue
        key = (q.project_id, q.query_text)
        groups.setdefault(key, []).append(q)

    candidates: list[GroundTruthCandidate] = []
    for (proj, text), events in groups.items():
        if len(events) < min_samples:
            continue
        feedbacked = [e for e in events if e.useful is not None]
        if not feedbacked:
            continue
        useful_count = sum(1 for e in feedbacked if e.useful is True)
        useful_rate = useful_count / len(feedbacked)
        if useful_rate < min_useful_rate:
            continue
        useful_events = [e for e in events if e.useful is True]
        proposed_docs, strategy = _compute_proposed_doc_ids(
            useful_events, max_doc_ids=max_doc_ids,
        )
        candidates.append(GroundTruthCandidate(
            candidate_id=f"gtc_{uuid.uuid4().hex[:10]}",
            project_id=proj,
            query_text=text,
            proposed_doc_ids=proposed_docs,
            sample_size=len(events),
            useful_rate=round(useful_rate, 4),
            reasoning=(
                f"{len(events)} 次查询，{len(feedbacked)} 次有反馈，"
                f"{useful_count} useful（占 {useful_rate:.0%}）"
                f"; doc_ids 来源: {strategy}"
            ),
        ))

    # 高 useful_rate + 高 sample_size 优先
    candidates.sort(
        key=lambda c: (c.useful_rate, c.sample_size), reverse=True,
    )
    log.info("ground_truth_candidates_constructed",
             project_id=project_id, count=len(candidates))
    return candidates[:max_doc_ids]


async def eval_all_projects(
    *, qa_callable: QaCallable, version: str = "", k: int = 5,
) -> list[RecallEvalReport]:
    """批量评估所有有 ground truth 的 project（M9 #3 · 外部 cron / ISS-Job 入口）。

    遍历每个 project 调 ``run_recall_eval`` + ``check_recall_alerts_and_propagate``。
    单 project 异常静默吞掉，不阻断其他。返回所有成功生成的 reports。
    """
    project_ids = list_projects_with_ground_truth()
    out: list[RecallEvalReport] = []
    for project_id in project_ids:
        try:
            report = await run_recall_eval(
                qa_callable=qa_callable,
                project_id=project_id, version=version, k=k,
            )
            out.append(report)
            try:
                check_recall_alerts_and_propagate(project_id=project_id)
            except Exception as ce:
                log.warning("eval_all_alert_check_failed",
                            project_id=project_id, error=str(ce))
        except Exception as e:
            log.warning("eval_all_project_failed",
                        project_id=project_id, error=str(e))
    log.info("eval_all_completed",
             projects=len(project_ids), reports=len(out))
    return out


def check_recall_alerts_and_propagate(
    *, project_id: str, lookback: int = 10,
) -> dict:
    """评估 + 把告警追加到当前活跃观察期（M5 #2 PromotionObservation）。

    用途：run_recall_eval 完成后调一次，让 dashboard `observations.alerting`
    包含召回率漂移信号。返回 trend dict（同 compute_recall_trend）+ propagated bool。
    """
    trend = compute_recall_trend(project_id=project_id, lookback=lookback)
    propagated = False
    if trend["alert_messages"]:
        # 复用 M5 #2 观察期 alerts 通道（不新增一套机制）
        try:
            from packages.rebuild import get_current_observation
            obs = get_current_observation(project_id)
            if obs is not None:
                for msg in trend["alert_messages"]:
                    if msg not in obs.alerts:
                        obs.alerts.append(msg)
                if obs.status == "watching":
                    obs.status = "alert"
                propagated = True
                log.warning(
                    "recall_drift_alert_propagated",
                    project_id=project_id,
                    observation_id=obs.observation_id,
                    alerts=trend["alert_messages"],
                )
        except Exception as e:
            log.warning("recall_alert_propagate_failed",
                        project_id=project_id, error=str(e))
    trend["propagated"] = propagated
    return trend
