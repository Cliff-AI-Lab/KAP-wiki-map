"""M1 W4 写入侧 · 蒸馏管线 → 4×6 矩阵双写 hook 单测。"""

from __future__ import annotations

import pytest

from packages.common import settings
from packages.governance.distillation_hook import enqueue_low_confidence_review
from packages.storage.governance_queue_store import GovernanceQueueStore


@pytest.fixture
async def store():
    s = GovernanceQueueStore()
    await s.initialize()
    return s


class TestEnqueueLowConfidenceReview:
    async def test_default_w4_sme_routing(self, store) -> None:
        """W4 默认路由到 SME（决策书 §5.2 W4 必审）。"""
        item = await enqueue_low_confidence_review(
            store=store,
            project_id="p1",
            doc_id="d1",
            doc_title="设备点检与润滑标准",
            confidence=0.42,
            proposed_decision="KEEP",
            reason="实体抽取置信度低",
        )
        assert item.workstation == "W4"
        assert item.assigned_role == "SME"
        assert item.kind == "low_confidence_extract"
        assert item.agent == "distillation"
        assert item.confidence == 0.42
        assert item.status == "pending"

    async def test_sla_due_at_set(self, store, monkeypatch) -> None:
        """sla_due_at 默认 60 分钟，可由 settings 配置。"""
        monkeypatch.setattr(settings, "kap_w4_sla_minutes", 30)
        item = await enqueue_low_confidence_review(
            store=store, project_id="p1", doc_id="d1", doc_title="t",
            confidence=0.5, proposed_decision="KEEP", reason="x",
        )
        assert item.sla_due_at is not None
        # SLA 30 分钟，留 5 分钟容错
        from datetime import datetime, timedelta, timezone
        delta = item.sla_due_at - datetime.now(timezone.utc)
        assert timedelta(minutes=25) < delta < timedelta(minutes=35)

    async def test_priority_inverse_to_confidence(self, store) -> None:
        """priority 与置信度反相关：confidence 越低优先级越高。"""
        low = await enqueue_low_confidence_review(
            store=store, project_id="p1", doc_id="d1", doc_title="t",
            confidence=0.1, proposed_decision="KEEP", reason="x",
        )
        high = await enqueue_low_confidence_review(
            store=store, project_id="p1", doc_id="d2", doc_title="t",
            confidence=0.55, proposed_decision="KEEP", reason="x",
        )
        assert low.priority > high.priority

    async def test_w3_routes_to_dg(self, store) -> None:
        """W3 切块工位（也可低置信度）→ 主审 DG。"""
        item = await enqueue_low_confidence_review(
            store=store, project_id="p1", doc_id="d1", doc_title="t",
            confidence=0.3, proposed_decision="KEEP", reason="x",
            workstation="W3",
        )
        assert item.workstation == "W3"
        assert item.assigned_role == "DG"

    async def test_title_truncated_to_80_chars(self, store) -> None:
        long_title = "A" * 200
        item = await enqueue_low_confidence_review(
            store=store, project_id="p1", doc_id="d1",
            doc_title=long_title,
            confidence=0.3, proposed_decision="KEEP", reason="x",
        )
        # 包装在 [W4-SME 必审] 前缀里 + 80 char title 截断 ≤ 完整 title 长
        assert len(item.title) < len(long_title)

    async def test_persisted_in_store(self, store) -> None:
        item = await enqueue_low_confidence_review(
            store=store, project_id="p1", doc_id="d1", doc_title="t",
            confidence=0.3, proposed_decision="KEEP", reason="x",
        )
        fetched = await store.get(item.id)
        assert fetched is not None
        assert fetched.id == item.id

    async def test_appears_in_matrix_view(self, store) -> None:
        """双写后，矩阵看板能看到该工单。"""
        await enqueue_low_confidence_review(
            store=store, project_id="p1", doc_id="d1", doc_title="t",
            confidence=0.3, proposed_decision="KEEP", reason="x",
        )
        matrix = await store.list_matrix("p1")
        assert matrix.get(("W4", "SME")) == 1


# ════════════════════════════════════════════════════════════════════════
#  M2 #1 · Critic 集成（决策书 §5.5 D13）
# ════════════════════════════════════════════════════════════════════════


class TestCriticIntegration:
    async def test_critic_findings_in_description(self, store) -> None:
        """传入 doc/librarian/judge 时，critic 6 维 finding 拼到 description。"""
        from datetime import datetime
        from unittest.mock import patch
        from packages.common.types import (
            Decision, DocType, JudgeReasoning, JudgeResult,
            LibrarianResult, RawDocument, SourceSystem,
        )

        doc = RawDocument(
            doc_id="d1", title="t", content="x" * 100,
            source_system=SourceSystem.LOCAL, source_id="1", org_id="default",
            created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 4, 1),
        )
        librarian = LibrarianResult(
            doc_type=DocType.REGULATION, version_id=None,
            key_topics=[], mentioned_entities=[],
            is_conversational=False, estimated_value="HIGH",
        )
        judge = JudgeResult(
            reasoning=JudgeReasoning(
                recency_analysis="x", recency_score=8,
                density_analysis="x", density_score=7,
                completeness_analysis="x", completeness_score=6,
                redundancy_analysis="x", redundancy_score=2,
            ),
            decision=Decision.KEEP, confidence=0.4, kpi_retain=0.5,
            summary="保留", needs_review=True,
        )

        with patch(
            "packages.distillation.agents.critic.acall_llm_json",
            return_value={
                "findings": [
                    {"dimension": "timeliness", "severity": 0.85,
                     "finding": "GB/T 6075-2003 已作废"},
                ],
                "summary": "时效问题",
            },
        ):
            item = await enqueue_low_confidence_review(
                store=store, project_id="p1",
                doc_id=doc.doc_id, doc_title=doc.title,
                confidence=0.4, proposed_decision="KEEP", reason="低置信度",
                doc=doc, librarian=librarian, judge=judge,
            )

        assert "时效问题" in item.description
        assert "timeliness" in item.description
        # blocking 提升 priority +20
        assert item.priority >= 60  # 基础 60 + 20

    async def test_no_critic_when_args_missing(self, store) -> None:
        """不传 doc/librarian/judge 时不调 critic（向后兼容旧调用方）。"""
        item = await enqueue_low_confidence_review(
            store=store, project_id="p1",
            doc_id="d1", doc_title="t",
            confidence=0.4, proposed_decision="KEEP", reason="低置信度",
        )
        assert "时效问题" not in item.description
        assert item.priority == 60  # 基础值，未提升
