"""异步 Pipeline 端到端测试（坑 1 批 3 验收）。

覆盖：

- ``arun_pipeline`` 完整 W1-W5 流程跑通（mock 4 个 arun_* agent）
- 噪音过滤 step（同步规则，不走 LLM）
- Librarian 失败不中断，errors 计数正确
- Judge 失败时降级 KEEP 兜底
- needs_review 正确标记 + pending_review 计数
- BatchPipelineResult schema 与 sync 版完全一致
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from packages.common.types import (
    AuditResult,
    Decision,
    DocType,
    EstimatedValue,
    JudgeReasoning,
    JudgeResult,
    LibrarianResult,
    MentionedEntity,
    RawDocument,
    RefinedResult,
    SourceSystem,
)
from packages.distillation.pipeline import arun_pipeline


def _make_doc(doc_id: str, title: str, content: str = "正文示例") -> RawDocument:
    return RawDocument(
        doc_id=doc_id,
        title=title,
        content=content,
        source_system=SourceSystem.FEISHU,
        source_id=f"src-{doc_id}",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        org_id="org-test",
    )


def _make_librarian(value: EstimatedValue = EstimatedValue.HIGH) -> LibrarianResult:
    return LibrarianResult(
        doc_type=DocType.REGULATION,
        version_id="v1.0",
        key_topics=["安全"],
        mentioned_entities=[],
        is_conversational=False,
        estimated_value=value,
    )


def _make_judge_keep() -> JudgeResult:
    return JudgeResult(
        reasoning=JudgeReasoning(
            recency_score=9,
            density_score=9,
            completeness_score=9,
            redundancy_score=1,
        ),
        decision=Decision.KEEP,
        confidence=0.95,
        kpi_retain=0.85,
        summary="高价值",
        key_entities=[],
        needs_review=False,
        rule_hit="R5",
    )


def _make_judge_review() -> JudgeResult:
    """触发 needs_review 的 JudgeResult（坑 3 R3 通道）。"""
    return JudgeResult(
        reasoning=JudgeReasoning(
            recency_score=5, density_score=5, completeness_score=5, redundancy_score=3,
        ),
        decision=Decision.KEEP,
        confidence=0.45,
        kpi_retain=0.40,
        summary="中等",
        needs_review=True,
        rule_hit="R3",
    )


def _make_refined(domain_id: str = "energy/safety") -> RefinedResult:
    return RefinedResult(
        summary="精炼摘要",
        catalog=[],
        keywords=["安全"],
        entities=[],
        relations=[],
        index_text="文档索引",
        domain_id=domain_id,
        doc_description="安全相关",
        key_elements=[],
    )


# ─────────── 端到端 ───────────


class TestArunPipelineE2E:
    @pytest.mark.asyncio
    async def test_full_pipeline_keep_all(self, monkeypatch) -> None:
        """3 篇文档全 KEEP，验证 W1-W5 全跑通 + Refiner 全部产出。"""
        from packages.distillation import pipeline as pipe_mod

        docs = [
            _make_doc("doc-001", "安全制度 v1"),
            _make_doc("doc-002", "安全制度 v2"),
            _make_doc("doc-003", "安全制度 v3"),
        ]

        async def fake_arun_librarian(doc):
            return _make_librarian()

        async def fake_arun_auditor(category, group_docs, meta):
            return AuditResult(summary="无重叠", max_overlap_score=0.0)

        async def fake_arun_judge(doc, lib, audit, **kwargs):
            return _make_judge_keep()

        async def fake_arun_refiner(doc, lib, domain_list_text="", **kwargs):
            return _make_refined()

        monkeypatch.setattr(pipe_mod, "arun_librarian", fake_arun_librarian)
        monkeypatch.setattr(pipe_mod, "arun_conflict_auditor", fake_arun_auditor)
        monkeypatch.setattr(pipe_mod, "arun_judge", fake_arun_judge)
        monkeypatch.setattr(pipe_mod, "arun_refiner", fake_arun_refiner)
        # 不让 noise filter 干扰
        monkeypatch.setattr(pipe_mod, "is_noise_document", lambda doc: False)

        batch = await arun_pipeline(docs)

        assert batch.total == 3
        assert batch.kept == 3
        assert batch.discarded == 0
        assert batch.archived == 0
        assert batch.pending_review == 0
        assert batch.errors == 0
        # 所有文档都应进 refiner_result
        for pr in batch.results:
            assert pr.refined_result is not None
            assert pr.refined_result.domain_id == "energy/safety"

    @pytest.mark.asyncio
    async def test_noise_filter_step(self, monkeypatch) -> None:
        """噪音文档应在 W1 前被过滤，不进入 LLM 调用。"""
        from packages.distillation import pipeline as pipe_mod

        docs = [_make_doc("doc-noise", "广告"), _make_doc("doc-real", "真实文档")]

        # 第一篇被识别为噪音
        monkeypatch.setattr(
            pipe_mod, "is_noise_document",
            lambda doc: doc.doc_id == "doc-noise",
        )

        librarian_called = []
        async def fake_arun_librarian(doc):
            librarian_called.append(doc.doc_id)
            return _make_librarian()

        async def fake_arun_judge(doc, lib, audit, **kw):
            return _make_judge_keep()

        async def fake_arun_refiner(doc, lib, **kw):
            return _make_refined()

        monkeypatch.setattr(pipe_mod, "arun_librarian", fake_arun_librarian)
        monkeypatch.setattr(pipe_mod, "arun_judge", fake_arun_judge)
        monkeypatch.setattr(pipe_mod, "arun_refiner", fake_arun_refiner)

        batch = await arun_pipeline(docs)

        # 噪音文档不应进 librarian
        assert "doc-noise" not in librarian_called
        assert "doc-real" in librarian_called
        # 噪音应计入 discarded + noise_filtered
        assert batch.noise_filtered == 1
        assert batch.discarded == 1
        assert batch.kept == 1

    @pytest.mark.asyncio
    async def test_librarian_failure_does_not_break_pipeline(
        self, monkeypatch
    ) -> None:
        """单文档 Librarian 失败不应中断整批，errors 计数 +1。"""
        from packages.common.exceptions import LLMCallError
        from packages.distillation import pipeline as pipe_mod

        docs = [_make_doc("doc-ok", "正常"), _make_doc("doc-fail", "失败")]

        async def fake_arun_librarian(doc):
            if doc.doc_id == "doc-fail":
                raise LLMCallError("simulated LLM failure")
            return _make_librarian()

        async def fake_arun_judge(doc, lib, audit, **kw):
            return _make_judge_keep()

        async def fake_arun_refiner(doc, lib, **kw):
            return _make_refined()

        monkeypatch.setattr(pipe_mod, "arun_librarian", fake_arun_librarian)
        monkeypatch.setattr(pipe_mod, "arun_judge", fake_arun_judge)
        monkeypatch.setattr(pipe_mod, "arun_refiner", fake_arun_refiner)
        monkeypatch.setattr(pipe_mod, "is_noise_document", lambda doc: False)

        batch = await arun_pipeline(docs)

        assert batch.errors == 1
        assert batch.total == 2
        # doc-ok 应跑完整路径
        ok_pr = next(pr for pr in batch.results if pr.doc_id == "doc-ok")
        assert ok_pr.error is None
        assert ok_pr.librarian_result is not None
        # doc-fail 应有 error 字段
        fail_pr = next(pr for pr in batch.results if pr.doc_id == "doc-fail")
        assert "Librarian LLM 调用失败" in fail_pr.error

    @pytest.mark.asyncio
    async def test_judge_failure_falls_back_to_keep(self, monkeypatch) -> None:
        """Judge 失败时降级保守 KEEP（决策书 §13 容错策略）。"""
        from packages.common.exceptions import LLMCallError
        from packages.distillation import pipeline as pipe_mod

        docs = [_make_doc("doc-001", "文档")]

        async def fake_arun_librarian(doc):
            return _make_librarian()

        async def fake_arun_judge(doc, lib, audit, **kw):
            raise LLMCallError("judge crashed")

        async def fake_arun_refiner(doc, lib, **kw):
            return _make_refined()

        monkeypatch.setattr(pipe_mod, "arun_librarian", fake_arun_librarian)
        monkeypatch.setattr(pipe_mod, "arun_judge", fake_arun_judge)
        monkeypatch.setattr(pipe_mod, "arun_refiner", fake_arun_refiner)
        monkeypatch.setattr(pipe_mod, "is_noise_document", lambda doc: False)

        batch = await arun_pipeline(docs)

        # Judge 失败 → 兜底 KEEP，但 errors+1
        assert batch.kept == 1
        assert batch.errors == 1
        pr = batch.results[0]
        assert pr.decision == Decision.KEEP
        assert "Judge LLM 调用失败" in pr.error

    @pytest.mark.asyncio
    async def test_needs_review_routes_correctly(self, monkeypatch) -> None:
        """needs_review=True 的文档进 pending_review 计数（坑 3 R3 路由）。"""
        from packages.distillation import pipeline as pipe_mod

        docs = [_make_doc("doc-keep", "高价值"), _make_doc("doc-review", "待审")]

        async def fake_arun_librarian(doc):
            return _make_librarian()

        async def fake_arun_judge(doc, lib, audit, **kw):
            if doc.doc_id == "doc-review":
                return _make_judge_review()
            return _make_judge_keep()

        async def fake_arun_refiner(doc, lib, **kw):
            return _make_refined()

        monkeypatch.setattr(pipe_mod, "arun_librarian", fake_arun_librarian)
        monkeypatch.setattr(pipe_mod, "arun_judge", fake_arun_judge)
        monkeypatch.setattr(pipe_mod, "arun_refiner", fake_arun_refiner)
        monkeypatch.setattr(pipe_mod, "is_noise_document", lambda doc: False)

        batch = await arun_pipeline(docs)

        assert batch.pending_review == 1
        assert batch.kept == 1  # doc-keep 直接 KEEP
        review_pr = next(pr for pr in batch.results if pr.doc_id == "doc-review")
        assert review_pr.needs_review is True
        assert review_pr.judge_result.rule_hit == "R3"

    @pytest.mark.asyncio
    async def test_empty_documents(self) -> None:
        """空文档列表，pipeline 应安全返回空结果。"""
        batch = await arun_pipeline([])
        assert batch.total == 0
        assert len(batch.results) == 0
        assert batch.kept == 0
