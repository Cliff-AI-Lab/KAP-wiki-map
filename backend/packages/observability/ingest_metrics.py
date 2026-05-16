"""W6 入库可观测性（M22 #6）。

补齐 W6 入库链路的可观测性缺口 — M7-M20 埋了查询 / Wiki 编译 / W4 抽取 诊断的点,
唯独 W6 入库本身的吞吐 / 单文档延迟 / 阶段耗时 / 失败率 没数。MinerU 接入后
（M22 #1）单页解析时延会变大, 没埋点会盲飞。

5 阶段耗时 + 错误分桶, 仿 M19 #1 wiki_quality + M20 #1 extraction_quality 模式:
  parse_ms / chunk_ms / embed_ms / vector_write_ms / graph_write_ms
  error_kind: parse_error / chunk_error / embed_timeout / vector_full / graph_violation / unknown
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Awaitable, Callable, Literal

from pydantic import BaseModel, Field

from packages.common import get_logger

log = get_logger("observability.ingest_metrics")


IngestStatus = Literal["success", "failed"]
IngestErrorKind = Literal[
    "",
    "parse_error",
    "chunk_error",
    "embed_timeout",
    "vector_full",
    "graph_violation",
    "raw_save_failed",
    "unknown",
]


class IngestMetric(BaseModel):
    """单文档 W6 入库诊断（M22 #6）。"""
    doc_id: str
    project_id: str = ""
    parser_name: str = ""                    # mineru / pdfplumber / abbyy / external 等
    source_system: str = ""
    doc_size: int = 0                         # 字节
    chunk_count: int = 0
    # 5 阶段耗时（毫秒）
    parse_ms: int = 0
    chunk_ms: int = 0
    embed_ms: int = 0
    vector_write_ms: int = 0
    graph_write_ms: int = 0
    total_ms: int = 0
    status: IngestStatus = "success"
    error_kind: IngestErrorKind = ""
    error_message: str = ""
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))


_metrics: list[IngestMetric] = []
_METRICS_MAX = 5000

_pg_sink: Callable[[IngestMetric], Awaitable[None]] | None = None


def reset_ingest_metrics_for_test() -> None:
    global _pg_sink
    _metrics.clear()
    _pg_sink = None


def set_ingest_metrics_pg_sink(
    sink: Callable[[IngestMetric], Awaitable[None]] | None,
) -> None:
    global _pg_sink
    _pg_sink = sink


def _fire_and_forget(coro_factory) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro_factory())
    except RuntimeError:
        pass


def record_ingest_metric(metric: IngestMetric) -> IngestMetric:
    """记录一次入库诊断（同步入口；PG sink 已配置时异步落盘）。"""
    metric.total_ms = (
        metric.parse_ms + metric.chunk_ms + metric.embed_ms
        + metric.vector_write_ms + metric.graph_write_ms
    )
    _metrics.append(metric)
    if len(_metrics) > _METRICS_MAX:
        # 简单截断 — 保留最近; 不动 LRU 复杂度
        del _metrics[:len(_metrics) - _METRICS_MAX]

    log.info(
        "ingest_metric_recorded",
        doc_id=metric.doc_id, project=metric.project_id,
        status=metric.status, total_ms=metric.total_ms,
        chunks=metric.chunk_count, parser=metric.parser_name,
    )

    if _pg_sink is not None:
        _fire_and_forget(lambda: _pg_sink(metric))  # type: ignore[misc]
    return metric


# ── 计时辅助 ─────────────────────────────────────────────


class StageTimer:
    """用于阶段计时的轻量上下文管理器。

    用法:
        timer = StageTimer()
        async with timer("parse"):
            ...
        async with timer("chunk"):
            ...
        metric = IngestMetric(doc_id="...", **timer.as_dict())
    """

    def __init__(self) -> None:
        self.records: dict[str, int] = {}

    @asynccontextmanager
    async def __call__(self, stage: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.records[stage] = int((time.perf_counter() - t0) * 1000)

    def get(self, stage: str) -> int:
        return self.records.get(stage, 0)

    def as_dict(self) -> dict[str, int]:
        """映射到 IngestMetric 的 *_ms 字段名。"""
        mapping = {
            "parse": "parse_ms",
            "chunk": "chunk_ms",
            "embed": "embed_ms",
            "vector_write": "vector_write_ms",
            "graph_write": "graph_write_ms",
        }
        out: dict[str, int] = {}
        for stage, field in mapping.items():
            out[field] = self.records.get(stage, 0)
        return out


# ── 趋势聚合（仿 wiki_quality / extraction_quality） ──


def compute_ingest_trend(
    project_id: str = "",
    bucket_hours: int = 1,
    limit: int = 100,
) -> list[dict]:
    """按时间桶聚合最近 N 个入库诊断。

    Returns:
        [{bucket_start, total, success, failed, avg_total_ms,
          p95_total_ms, error_kinds: {kind: count}}, ...]
    """
    pool = [m for m in _metrics
            if not project_id or m.project_id == project_id]
    if not pool:
        return []

    # 按 bucket 分组
    bucket_sec = bucket_hours * 3600
    groups: dict[int, list[IngestMetric]] = {}
    for m in pool:
        ts = int(m.ingested_at.timestamp())
        bkt = (ts // bucket_sec) * bucket_sec
        groups.setdefault(bkt, []).append(m)

    out: list[dict] = []
    for bkt in sorted(groups.keys())[-limit:]:
        items = groups[bkt]
        n = len(items)
        success = sum(1 for x in items if x.status == "success")
        failed = n - success
        totals = sorted([x.total_ms for x in items])
        # p95 = sorted[ceil(n*0.95)-1] = sorted[min(n-1, int(n*0.95))]
        # n=20 → 索引 19 = 第 20 个值 = 真 p95
        p95_idx = min(n - 1, int(n * 0.95)) if n else 0
        avg = sum(totals) / n if n else 0
        error_kinds: dict[str, int] = {}
        for x in items:
            if x.error_kind:
                error_kinds[x.error_kind] = error_kinds.get(x.error_kind, 0) + 1
        out.append({
            "bucket_start": datetime.fromtimestamp(bkt).isoformat(),
            "total": n,
            "success": success,
            "failed": failed,
            "avg_total_ms": int(avg),
            "p95_total_ms": totals[p95_idx] if totals else 0,
            "error_kinds": error_kinds,
        })
    return out
