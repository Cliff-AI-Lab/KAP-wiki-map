"""M3 #2 · 双 Agent 互审完整版 — pipeline 主路径接入单测（决策书 §5.5 D13）。

不重跑完整 pipeline（依赖太多）。聚焦在 _run_critic_for_pr 函数的行为：
- 高 severity 强制 needs_review = True
- 低 severity 不影响
- LLM 失败静默降级
- 关闭 flag 时不触发
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from packages.common import settings
from packages.common.types import (
    AuditResult,
    CriticFinding,
    CriticResult,
    Decision,
    DocType,
    JudgeReasoning,
    JudgeResult,
    LibrarianResult,
    RawDocument,
    SourceSystem,
)
from packages.distillation.pipeline import (
    BatchPipelineResult,
    PipelineResult,
    _run_critic_for_pr,
)


# ════════════════════════════════════════════════════════════════════════
#  Fixtures
# ════════════════════════════════════════════════════════════════════════


def _doc() -> RawDocument:
    return RawDocument(
        doc_id="d1", title="t",
        content="x" * 50,
        source_system=SourceSystem.LOCAL,
        source_id="1", org_id="default",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 4, 1),
    )


def _librarian() -> LibrarianResult:
    return LibrarianResult(
        doc_type=DocType.REGULATION, version_id=None,
        key_topics=[], mentioned_entities=[],
        is_conversational=False, estimated_value="HIGH",
    )


def _judge(confidence: float = 0.8) -> JudgeResult:
    return JudgeResult(
        reasoning=JudgeReasoning(
            recency_analysis="x", recency_score=8,
            density_analysis="x", density_score=7,
            completeness_analysis="x", completeness_score=6,
            redundancy_analysis="x", redundancy_score=2,
        ),
        decision=Decision.KEEP, confidence=confidence, kpi_retain=0.6,
        summary="保留", needs_review=False,
    )


def _make_pr(needs_review: bool = False) -> PipelineResult:
    return PipelineResult(
        doc_id="d1", title="t",
        librarian_result=_librarian(),
        judge_result=_judge(),
        decision=Decision.KEEP,
        needs_review=needs_review,
    )


# ════════════════════════════════════════════════════════════════════════
#  _run_critic_for_pr 行为
# ════════════════════════════════════════════════════════════════════════


class TestRunCriticForPr:
    async def test_blocking_severity_forces_review(self) -> None:
        pr = _make_pr(needs_review=False)
        batch = BatchPipelineResult(kept=1)

        async def fake_critic(doc, lib, audit, judge):
            return CriticResult(
                findings=[
                    CriticFinding(dimension="timeliness", severity=0.85,
                                  finding="标准已作废"),
                ],
                overall_severity=0.85,
                summary="时效问题",
            )

        with patch(
            "packages.distillation.agents.critic.arun_critic",
            side_effect=fake_critic,
        ):
            await _run_critic_for_pr(pr, _doc(), None, _judge(), batch)

        assert pr.needs_review is True
        assert pr.critic_result is not None
        assert pr.critic_result.overall_severity == 0.85
        # batch 计数从 kept 移到 pending_review
        assert batch.kept == 0
        assert batch.pending_review == 1

    async def test_low_severity_does_not_force(self) -> None:
        pr = _make_pr(needs_review=False)
        batch = BatchPipelineResult(kept=1)

        async def fake_critic(doc, lib, audit, judge):
            return CriticResult(
                findings=[CriticFinding(dimension="evidence", severity=0.3)],
                overall_severity=0.3,
            )

        with patch(
            "packages.distillation.agents.critic.arun_critic",
            side_effect=fake_critic,
        ):
            await _run_critic_for_pr(pr, _doc(), None, _judge(), batch)

        assert pr.needs_review is False
        assert pr.critic_result is not None
        # batch 不变
        assert batch.kept == 1
        assert batch.pending_review == 0

    async def test_already_needs_review_keeps_status(self) -> None:
        """已经 needs_review=True 时 critic 不重复升级 + 不重复变 batch 计数。"""
        pr = _make_pr(needs_review=True)
        batch = BatchPipelineResult(pending_review=1)

        async def fake_critic(doc, lib, audit, judge):
            return CriticResult(
                findings=[CriticFinding(dimension="timeliness", severity=0.9)],
                overall_severity=0.9,
            )

        with patch(
            "packages.distillation.agents.critic.arun_critic",
            side_effect=fake_critic,
        ):
            await _run_critic_for_pr(pr, _doc(), None, _judge(), batch)

        assert pr.needs_review is True
        assert batch.pending_review == 1  # 不重复增加

    async def test_critic_failure_silent(self) -> None:
        """LLM-Critic 失败 → pipeline 不阻断，pr 不变。"""
        pr = _make_pr(needs_review=False)
        batch = BatchPipelineResult(kept=1)

        with patch(
            "packages.distillation.agents.critic.arun_critic",
            side_effect=Exception("LLM down"),
        ):
            await _run_critic_for_pr(pr, _doc(), None, _judge(), batch)

        assert pr.needs_review is False
        assert pr.critic_result is None
        assert batch.kept == 1

    async def test_no_librarian_skipped(self) -> None:
        """缺 librarian_result → 跳过 critic 不报错。"""
        pr = PipelineResult(doc_id="d1", title="t",
                            librarian_result=None,
                            judge_result=_judge())
        batch = BatchPipelineResult()

        # 即使 patch critic 也不应被调
        with patch(
            "packages.distillation.agents.critic.arun_critic",
        ) as mock_c:
            await _run_critic_for_pr(pr, _doc(), None, _judge(), batch)
            mock_c.assert_not_called()

    async def test_custom_threshold_via_settings(self, monkeypatch) -> None:
        """settings.critic_blocking_threshold 可调。"""
        monkeypatch.setattr(settings, "critic_blocking_threshold", 0.4)
        pr = _make_pr(needs_review=False)
        batch = BatchPipelineResult(kept=1)

        async def fake_critic(doc, lib, audit, judge):
            return CriticResult(
                findings=[CriticFinding(dimension="evidence", severity=0.5)],
                overall_severity=0.5,
            )

        with patch(
            "packages.distillation.agents.critic.arun_critic",
            side_effect=fake_critic,
        ):
            await _run_critic_for_pr(pr, _doc(), None, _judge(), batch)

        # threshold 0.4，severity 0.5 → blocking
        assert pr.needs_review is True


# ════════════════════════════════════════════════════════════════════════
#  Settings flag 行为
# ════════════════════════════════════════════════════════════════════════


class TestPipelineCriticFlag:
    def test_default_disabled(self) -> None:
        """默认 pipeline_critic_enabled=False（M2 lite 兼容）。"""
        # 不要 monkeypatch，看真实默认
        from packages.common.config import Settings
        s = Settings()
        assert s.pipeline_critic_enabled is False

    def test_can_be_enabled(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "pipeline_critic_enabled", True)
        assert settings.pipeline_critic_enabled is True
