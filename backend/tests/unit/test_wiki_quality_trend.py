"""M19 #1 · Wiki 质量趋势 + PG sink 单测（mock LLM）。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from packages.observability import (
    compute_wiki_quality_trend,
    reset_wiki_quality_for_test,
    score_wiki_page,
    set_wiki_quality_pg_sink,
)
from packages.observability import wiki_quality as wq_mod


PERFECT = {
    "consistency": {"score": 0.9, "reason": "x"},
    "completeness": {"score": 0.9, "reason": "x"},
    "evidence": {"score": 0.9, "reason": "x"},
    "repetition": {"score": 0.9, "reason": "x"},
    "freshness": {"score": 0.9, "reason": "x"},
    "cross_domain": {"score": 0.9, "reason": "x"},
}
DROPPED = {
    "consistency": {"score": 0.4, "reason": "x"},
    "completeness": {"score": 0.4, "reason": "x"},
    "evidence": {"score": 0.4, "reason": "x"},
    "repetition": {"score": 0.4, "reason": "x"},
    "freshness": {"score": 0.4, "reason": "x"},
    "cross_domain": {"score": 0.4, "reason": "x"},
}


@pytest.fixture(autouse=True)
def _reset():
    reset_wiki_quality_for_test()
    yield
    reset_wiki_quality_for_test()


class TestTrend:
    async def test_empty_trend(self) -> None:
        out = compute_wiki_quality_trend()
        assert out["samples"] == 0
        assert out["buckets"] == []
        assert out["delta"] == 0.0
        assert out["trend_alert"] is False

    async def test_single_bucket_no_alert(self, monkeypatch) -> None:
        async def fake(_s, _u): return PERFECT
        monkeypatch.setattr(wq_mod, "acall_llm_json", fake)
        for i in range(5):
            await score_wiki_page(
                page_id=f"p{i}", page_type="index", title="x",
                content="x", project_id="p1",
            )
        out = compute_wiki_quality_trend(project_id="p1", bucket_size=5)
        assert out["samples"] == 5
        assert len(out["buckets"]) == 1
        assert out["buckets"][0]["count"] == 5
        assert 0.85 < out["buckets"][0]["avg_overall"] < 0.95
        assert out["delta"] == 0.0  # 单桶 delta=0
        assert out["trend_alert"] is False

    async def test_decline_triggers_alert(self, monkeypatch) -> None:
        """从 0.9 降到 0.4 应触发 trend_alert（delta < -0.10）。"""
        responses = [PERFECT] * 5 + [DROPPED] * 5
        idx = {"i": 0}

        async def fake(_s, _u):
            r = responses[idx["i"]]
            idx["i"] += 1
            return r

        monkeypatch.setattr(wq_mod, "acall_llm_json", fake)
        for i in range(10):
            score = await score_wiki_page(
                page_id=f"p{i}", page_type="index", title="x",
                content="x", project_id="p1",
            )
            # 手动调整 scored_at 拉开时间，模拟历史
            score.scored_at = datetime.now() - timedelta(minutes=10 - i)

        out = compute_wiki_quality_trend(
            project_id="p1", bucket_size=5,
        )
        assert out["samples"] == 10
        assert len(out["buckets"]) == 2
        assert out["delta"] < -0.10
        assert out["trend_alert"] is True

    async def test_project_filter(self, monkeypatch) -> None:
        async def fake(_s, _u): return PERFECT
        monkeypatch.setattr(wq_mod, "acall_llm_json", fake)
        await score_wiki_page(
            page_id="a", page_type="index", title="x",
            content="x", project_id="p1",
        )
        await score_wiki_page(
            page_id="b", page_type="index", title="x",
            content="x", project_id="p2",
        )
        out_p1 = compute_wiki_quality_trend(project_id="p1")
        out_p2 = compute_wiki_quality_trend(project_id="p2")
        assert out_p1["samples"] == 1
        assert out_p2["samples"] == 1


class TestPgSink:
    async def test_sink_called_on_score(self, monkeypatch) -> None:
        captured: list = []

        async def fake_sink(score):
            captured.append(score)

        async def fake(_s, _u): return PERFECT
        monkeypatch.setattr(wq_mod, "acall_llm_json", fake)

        set_wiki_quality_pg_sink(fake_sink)
        await score_wiki_page(
            page_id="p_1", page_type="index", title="x",
            content="x", project_id="p1",
        )
        # fire-and-forget：等异步任务跑完
        import asyncio
        await asyncio.sleep(0.05)
        assert len(captured) == 1
        assert captured[0].page_id == "p_1"

        set_wiki_quality_pg_sink(None)

    async def test_sink_skipped_for_error_score(self, monkeypatch) -> None:
        """LLM 失败的 error score 不入 _scores 但仍走 sink？

        实际：当前实现 LLM 失败时 return early，不进 _history，不调 sink。
        测试此契约（避免污染 PG 持久化）。
        """
        captured: list = []

        async def fake_sink(score):
            captured.append(score)

        async def fake(_s, _u):
            raise RuntimeError("LLM down")

        monkeypatch.setattr(wq_mod, "acall_llm_json", fake)

        set_wiki_quality_pg_sink(fake_sink)
        await score_wiki_page(
            page_id="p_x", page_type="index", title="x",
            content="x", project_id="p1",
        )
        import asyncio
        await asyncio.sleep(0.05)
        assert len(captured) == 0  # 失败评分不持久化

        set_wiki_quality_pg_sink(None)
