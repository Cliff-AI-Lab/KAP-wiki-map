"""M22 #6 · W6 入库可观测性单测。"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from packages.observability.ingest_metrics import (
    IngestMetric,
    StageTimer,
    compute_ingest_trend,
    record_ingest_metric,
    reset_ingest_metrics_for_test,
    set_ingest_metrics_pg_sink,
)


@pytest.fixture(autouse=True)
def _isolate():
    reset_ingest_metrics_for_test()
    yield
    reset_ingest_metrics_for_test()


class TestRecordIngestMetric:
    def test_total_ms_auto_computed(self):
        m = record_ingest_metric(IngestMetric(
            doc_id="d1", parse_ms=100, chunk_ms=50,
            embed_ms=300, vector_write_ms=80, graph_write_ms=20,
            chunk_count=5,
        ))
        assert m.total_ms == 550  # 100+50+300+80+20

    def test_pg_sink_invoked(self):
        captured: list[IngestMetric] = []

        async def _sink(metric: IngestMetric):
            captured.append(metric)

        set_ingest_metrics_pg_sink(_sink)

        async def _run():
            record_ingest_metric(IngestMetric(doc_id="d2", chunk_count=1))
            await asyncio.sleep(0.05)  # 让 create_task 跑完

        asyncio.run(_run())
        assert len(captured) == 1
        assert captured[0].doc_id == "d2"


@pytest.mark.asyncio
class TestStageTimer:
    async def test_records_each_stage(self):
        timer = StageTimer()
        async with timer("parse"):
            await asyncio.sleep(0.01)
        async with timer("embed"):
            await asyncio.sleep(0.01)

        d = timer.as_dict()
        assert d["parse_ms"] >= 9  # 允许 1ms 抖动
        assert d["embed_ms"] >= 9
        assert d["chunk_ms"] == 0  # 没计的阶段保持 0

    async def test_as_dict_field_names_match_metric(self):
        timer = StageTimer()
        async with timer("vector_write"):
            await asyncio.sleep(0.001)
        d = timer.as_dict()
        # 字段名应能直接 unpack 给 IngestMetric
        m = IngestMetric(doc_id="d", **d)
        assert m.vector_write_ms >= 0


class TestTrendAggregation:
    def test_empty_returns_empty(self):
        assert compute_ingest_trend() == []

    def test_groups_by_bucket(self):
        # 两个 bucket 的样本
        t0 = datetime.now() - timedelta(hours=2)
        t1 = datetime.now()
        for i in range(3):
            record_ingest_metric(IngestMetric(
                doc_id=f"d{i}", parse_ms=100, chunk_count=1,
                ingested_at=t0,
            ))
        for i in range(5):
            record_ingest_metric(IngestMetric(
                doc_id=f"e{i}", parse_ms=200, chunk_count=2,
                ingested_at=t1,
            ))
        trend = compute_ingest_trend(bucket_hours=1)
        assert len(trend) >= 2
        totals = [b["total"] for b in trend]
        assert sum(totals) == 8

    def test_success_failed_split(self):
        for i in range(7):
            record_ingest_metric(IngestMetric(
                doc_id=f"d{i}", status="success", parse_ms=10, chunk_count=1,
            ))
        for i in range(3):
            record_ingest_metric(IngestMetric(
                doc_id=f"e{i}", status="failed",
                error_kind="embed_timeout", parse_ms=10,
            ))
        trend = compute_ingest_trend(bucket_hours=24)
        bkt = trend[-1]
        assert bkt["total"] == 10
        assert bkt["success"] == 7
        assert bkt["failed"] == 3
        assert bkt["error_kinds"]["embed_timeout"] == 3

    def test_p95_total_ms(self):
        # 故意造延迟 1ms x 19 + 1000ms x 1, p95 应是 1000
        for i in range(19):
            record_ingest_metric(IngestMetric(
                doc_id=f"fast_{i}", parse_ms=1,
            ))
        record_ingest_metric(IngestMetric(doc_id="slow", parse_ms=1000))
        trend = compute_ingest_trend(bucket_hours=24)
        bkt = trend[-1]
        # p95 索引 = int(20*0.95)-1 = 18, sorted 第 19 个 = 1000
        assert bkt["p95_total_ms"] == 1000


# ────────── /observability/ingest-metrics/trend 端点 ──────────


class TestIngestMetricsTrendEndpoint:
    def test_endpoint_returns_trend(self):
        from api.routers.observability import router

        # 灌点数据
        for i in range(4):
            record_ingest_metric(IngestMetric(
                doc_id=f"d{i}", project_id="p1",
                parse_ms=50, chunk_count=2,
            ))

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        client = TestClient(app)
        r = client.get("/api/v1/observability/ingest-metrics/trend?project_id=p1")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert sum(b["total"] for b in data) == 4
