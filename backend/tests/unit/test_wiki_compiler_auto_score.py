"""M18 #1 · WikiCompiler 自动评分集成（编译完成 → 自动 6 维评分）。

验证 compile_source / compile_domain 编译后挂上 score_wiki_page，
并兼容 auto_score=False 关闭开关。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from packages.common.types import RefinedResult
from packages.distillation import wiki_compiler as wc_mod
from packages.distillation.wiki_compiler import WikiCompiler
from packages.observability import (
    get_wiki_quality_score,
    list_wiki_quality_scores,
    reset_wiki_quality_for_test,
)
from packages.observability import wiki_quality as wq_mod


PERFECT_RESPONSE = {
    "consistency": {"score": 0.92, "reason": "一致"},
    "completeness": {"score": 0.88, "reason": "完整"},
    "evidence": {"score": 0.85, "reason": "证据足"},
    "repetition": {"score": 0.95, "reason": "无冗余"},
    "freshness": {"score": 0.8, "reason": "新"},
    "cross_domain": {"score": 0.78, "reason": "关联自然"},
}


@pytest.fixture(autouse=True)
def _reset():
    reset_wiki_quality_for_test()
    yield
    reset_wiki_quality_for_test()


def _make_stores():
    raw_store = MagicMock()
    raw_store.get_raw = AsyncMock(return_value={"title": "燃机巡检"})
    wiki_store = MagicMock()
    wiki_store.upsert_page = AsyncMock(return_value=None)
    domain_store = MagicMock()
    domain_store.list_domains = MagicMock(return_value=[])
    return raw_store, wiki_store, domain_store


class TestCompileSourceAutoScore:
    async def test_compile_source_triggers_quality_score(self, monkeypatch) -> None:
        """compile_source 完成 → score_wiki_page 落入 _scores 字典。"""
        raw, wiki, dom = _make_stores()

        # 同步 LLM（用于 source 内容编译）
        monkeypatch.setattr(
            wc_mod, "call_llm",
            lambda _sys, _user, **_kw: "# 燃机巡检\n## 核心摘要\n关键参数...\n",
        )

        # 异步 LLM（用于质量评分）
        async def fake_critic(_sys, _user):
            return PERFECT_RESPONSE

        monkeypatch.setattr(wq_mod, "acall_llm_json", fake_critic)

        compiler = WikiCompiler(raw, wiki, dom)
        page = await compiler.compile_source(
            doc_id="d1",
            doc_title="燃机巡检",
            domain_id="energy/maintenance",
            domain_name="维护",
            refined_result=RefinedResult(summary="x", entities=[], relations=[]),
            project_id="p1",
        )

        assert page.page_type == "source_summary"
        score = get_wiki_quality_score(page.page_id)
        assert score is not None
        assert score.project_id == "p1"
        assert score.overall > 0.8
        assert score.quality_alert is False

    async def test_compile_domain_triggers_quality_score(self, monkeypatch) -> None:
        raw, wiki, dom = _make_stores()
        monkeypatch.setattr(
            wc_mod, "call_llm",
            lambda _sys, _user, **_kw: "# 维护域概览\n## 概述\n聚合内容...\n",
        )

        async def fake_critic(_sys, _user):
            return PERFECT_RESPONSE

        monkeypatch.setattr(wq_mod, "acall_llm_json", fake_critic)

        compiler = WikiCompiler(raw, wiki, dom)
        page = await compiler.compile_domain(
            domain_id="energy/maintenance",
            domain_name="维护",
            domain_desc="燃机维护",
            project_id="p1",
            refined_results=[
                ("d1", RefinedResult(summary="x", entities=[], relations=[])),
            ],
        )

        assert page.page_type == "domain_overview"
        score = get_wiki_quality_score(page.page_id)
        assert score is not None
        assert score.project_id == "p1"

    async def test_auto_score_disabled_skips_scoring(self, monkeypatch) -> None:
        """auto_score=False → 不调评分；_scores 保持空。"""
        raw, wiki, dom = _make_stores()
        monkeypatch.setattr(
            wc_mod, "call_llm",
            lambda _sys, _user, **_kw: "# x\n## 核心摘要\nx\n",
        )

        critic_called = {"n": 0}

        async def fake_critic(_sys, _user):
            critic_called["n"] += 1
            return PERFECT_RESPONSE

        monkeypatch.setattr(wq_mod, "acall_llm_json", fake_critic)

        compiler = WikiCompiler(raw, wiki, dom, auto_score=False)
        await compiler.compile_source(
            doc_id="d1", doc_title="x",
            domain_id="energy", domain_name="能源",
            refined_result=RefinedResult(summary="", entities=[], relations=[]),
            project_id="p1",
        )

        assert critic_called["n"] == 0
        assert list_wiki_quality_scores() == []

    async def test_score_failure_does_not_break_compile(self, monkeypatch) -> None:
        """LLM 评分失败 → 编译仍成功返回 page。"""
        raw, wiki, dom = _make_stores()
        monkeypatch.setattr(
            wc_mod, "call_llm",
            lambda _sys, _user, **_kw: "# x\n## 核心摘要\nx\n",
        )

        async def fake_critic(_sys, _user):
            raise RuntimeError("LLM 评分挂了")

        monkeypatch.setattr(wq_mod, "acall_llm_json", fake_critic)

        compiler = WikiCompiler(raw, wiki, dom)
        page = await compiler.compile_source(
            doc_id="d1", doc_title="x",
            domain_id="energy", domain_name="能源",
            refined_result=RefinedResult(summary="", entities=[], relations=[]),
            project_id="p1",
        )

        # 编译本身成功；评分失败不阻塞
        assert page is not None
        assert page.page_type == "source_summary"
        # _scores 不入库（错误情况按 wiki_quality.py 设计跳过 _scores）
        assert get_wiki_quality_score(page.page_id) is None
