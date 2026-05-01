"""M17 #3 · Wiki 编译质量评分单测（mock LLM；老式快速回归）。

按 memory feedback_real_llm_in_tests：老 mock 测试保留作 schema 快速回归；
真 LLM 测试见 tests/integration/test_live_llm_wiki_quality.py。
"""

from __future__ import annotations

import pytest

from packages.observability import (
    aggregate_wiki_quality,
    list_wiki_quality_scores,
    reset_wiki_quality_for_test,
    score_wiki_page,
)
from packages.observability import wiki_quality as wq_mod


@pytest.fixture(autouse=True)
def _reset():
    reset_wiki_quality_for_test()
    yield
    reset_wiki_quality_for_test()


PERFECT_LLM_RESPONSE = {
    "consistency": {"score": 0.95, "reason": "完全符合源"},
    "completeness": {"score": 0.9, "reason": "覆盖全面"},
    "evidence": {"score": 0.85, "reason": "引用充分"},
    "repetition": {"score": 0.95, "reason": "无冗余"},
    "freshness": {"score": 0.8, "reason": "时效新"},
    "cross_domain": {"score": 0.75, "reason": "关联自然"},
}


LOW_QUALITY_LLM_RESPONSE = {
    "consistency": {"score": 0.3, "reason": "与源矛盾"},
    "completeness": {"score": 0.4, "reason": "缺关键事实"},
    "evidence": {"score": 0.5, "reason": "证据不足"},
    "repetition": {"score": 0.6, "reason": "有冗余"},
    "freshness": {"score": 0.4, "reason": "含过期信息"},
    "cross_domain": {"score": 0.5, "reason": "关联牵强"},
}


class TestScoreWikiPage:
    async def test_perfect_score_no_alert(self, monkeypatch) -> None:
        async def fake(_sys, _user):
            return PERFECT_LLM_RESPONSE

        monkeypatch.setattr(wq_mod, "acall_llm_json", fake)
        score = await score_wiki_page(
            page_id="p_demo", page_type="domain_overview",
            title="电机维护手册", content="x" * 100,
            source_doc_count=5, cross_ref_count=3,
            project_id="p1",
        )
        assert score.consistency.score == 0.95
        # overall = 0.95*0.2 + 0.9*0.2 + 0.85*0.2 + 0.95*0.1 + 0.8*0.15 + 0.75*0.15
        # = 0.19 + 0.18 + 0.17 + 0.095 + 0.12 + 0.1125 = 0.8675
        assert 0.86 < score.overall < 0.88
        assert score.quality_alert is False
        assert score.error == ""

    async def test_low_score_triggers_alert(self, monkeypatch) -> None:
        async def fake(_sys, _user):
            return LOW_QUALITY_LLM_RESPONSE

        monkeypatch.setattr(wq_mod, "acall_llm_json", fake)
        score = await score_wiki_page(
            page_id="p_low", page_type="source_summary",
            title="低质量页", content="x",
            project_id="p1",
        )
        # overall ≈ 0.3*0.2 + 0.4*0.2 + 0.5*0.2 + 0.6*0.1 + 0.4*0.15 + 0.5*0.15
        # = 0.06 + 0.08 + 0.1 + 0.06 + 0.06 + 0.075 = 0.435
        assert score.overall < 0.6
        assert score.quality_alert is True

    async def test_llm_failure_returns_error_score(self, monkeypatch) -> None:
        async def fake(_sys, _user):
            raise RuntimeError("LLM down")

        monkeypatch.setattr(wq_mod, "acall_llm_json", fake)
        score = await score_wiki_page(
            page_id="p_fail", page_type="index", title="x", content="x",
        )
        assert "LLM down" in score.error
        # 默认 0 分；不入聚合字典
        assert score.overall == 0.0

    async def test_invalid_dim_score_clamped(self, monkeypatch) -> None:
        async def fake(_sys, _user):
            return {
                "consistency": {"score": 1.5, "reason": "越界"},
                "completeness": {"score": -0.2, "reason": "负"},
                "evidence": {"score": "not-a-number", "reason": "无效"},
                "repetition": {"score": 0.5, "reason": ""},
                "freshness": {"score": 0.5, "reason": ""},
                "cross_domain": {"score": 0.5, "reason": ""},
            }

        monkeypatch.setattr(wq_mod, "acall_llm_json", fake)
        score = await score_wiki_page(
            page_id="p_bad", page_type="index", title="x", content="x",
        )
        assert score.consistency.score == 1.0       # clamped 上限
        assert score.completeness.score == 0.0      # clamped 下限
        assert score.evidence.score == 0.0          # 解析失败默认 0

    async def test_score_persisted_for_lookup(self, monkeypatch) -> None:
        async def fake(_sys, _user):
            return PERFECT_LLM_RESPONSE

        monkeypatch.setattr(wq_mod, "acall_llm_json", fake)
        await score_wiki_page(
            page_id="p_a", page_type="index", title="A", content="x",
            project_id="p1",
        )
        await score_wiki_page(
            page_id="p_b", page_type="index", title="B", content="x",
            project_id="p1",
        )
        all_scores = list_wiki_quality_scores(project_id="p1")
        assert len(all_scores) == 2


class TestAggregate:
    async def test_empty_aggregate(self) -> None:
        agg = aggregate_wiki_quality()
        assert agg["total_scored"] == 0
        assert agg["alerting_count"] == 0
        assert agg["avg_overall"] == 0.0

    async def test_aggregate_with_mix(self, monkeypatch) -> None:
        responses = [PERFECT_LLM_RESPONSE, LOW_QUALITY_LLM_RESPONSE]
        idx = {"i": 0}

        async def fake(_sys, _user):
            r = responses[idx["i"] % len(responses)]
            idx["i"] += 1
            return r

        monkeypatch.setattr(wq_mod, "acall_llm_json", fake)
        await score_wiki_page(
            page_id="p_high", page_type="index", title="高",
            content="x", project_id="p1",
        )
        await score_wiki_page(
            page_id="p_low", page_type="index", title="低",
            content="x", project_id="p1",
        )

        agg = aggregate_wiki_quality(project_id="p1")
        assert agg["total_scored"] == 2
        assert agg["alerting_count"] == 1
        assert 0.4 < agg["avg_overall"] < 0.7
        for dim in ("consistency", "completeness", "evidence",
                    "repetition", "freshness", "cross_domain"):
            assert 0.0 <= agg["avg_dimensions"][dim] <= 1.0
