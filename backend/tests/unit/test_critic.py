"""M2 #1 · LLM-Critic 6 维质疑单测（决策书 §5.5 D13）。"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

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
from packages.distillation.agents.critic import (
    _parse_critic_response,
    arun_critic,
    critic_to_review_description,
    run_critic,
)


# ════════════════════════════════════════════════════════════════════════
#  Fixtures
# ════════════════════════════════════════════════════════════════════════


def _doc() -> RawDocument:
    return RawDocument(
        doc_id="d1",
        title="设备点检与润滑标准",
        content="本标准引用 GB/T 6075-2003 振动评价。" * 50,
        source_system=SourceSystem.LOCAL,
        source_id="local-1",
        org_id="default",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 4, 1),
    )


def _librarian() -> LibrarianResult:
    return LibrarianResult(
        doc_type=DocType.REGULATION,
        version_id=None,
        key_topics=["设备点检", "润滑"],
        mentioned_entities=[],
        is_conversational=False,
        estimated_value="HIGH",
    )


def _judge() -> JudgeResult:
    return JudgeResult(
        reasoning=JudgeReasoning(
            recency_analysis="x", recency_score=8,
            density_analysis="x", density_score=7,
            completeness_analysis="x", completeness_score=6,
            redundancy_analysis="x", redundancy_score=2,
        ),
        decision=Decision.KEEP,
        confidence=0.7,
        kpi_retain=0.65,
        summary="保留：设备维护标准核心文件",
        key_entities=["GB/T 6075"],
        needs_review=False,
    )


# ════════════════════════════════════════════════════════════════════════
#  _parse_critic_response
# ════════════════════════════════════════════════════════════════════════


class TestParseCriticResponse:
    def test_full_six_dimensions(self) -> None:
        raw = {
            "findings": [
                {"dimension": d, "severity": 0.2, "finding": f"f-{d}",
                 "evidence": "e", "suggestion": "s"}
                for d in ("consistency", "completeness", "evidence",
                          "duplication", "timeliness", "cross_domain")
            ],
            "summary": "整体可用",
        }
        result = _parse_critic_response(raw)
        assert len(result.findings) == 6
        assert result.summary == "整体可用"
        assert result.overall_severity == pytest.approx(0.2)

    def test_missing_dimensions_filled_with_zero(self) -> None:
        """LLM 漏 4 个维度时自动补 0 severity 占位。"""
        raw = {
            "findings": [
                {"dimension": "timeliness", "severity": 0.9,
                 "finding": "GB/T 6075-2003 已作废"},
                {"dimension": "evidence", "severity": 0.4, "finding": "x"},
            ],
            "summary": "时效问题",
        }
        result = _parse_critic_response(raw)
        assert len(result.findings) == 6  # 6 维齐全
        timeliness = next(f for f in result.findings if f.dimension == "timeliness")
        assert timeliness.severity == 0.9
        # 漏掉的维度填了占位
        consistency = next(f for f in result.findings if f.dimension == "consistency")
        assert consistency.severity == 0.0
        assert "未提及" in consistency.finding

    def test_invalid_dimension_ignored(self) -> None:
        raw = {
            "findings": [
                {"dimension": "fake_dim", "severity": 0.9, "finding": "x"},
                {"dimension": "consistency", "severity": 0.5, "finding": "real"},
            ],
        }
        result = _parse_critic_response(raw)
        consistency = next(f for f in result.findings if f.dimension == "consistency")
        assert consistency.severity == 0.5
        # fake_dim 被丢弃，6 维其他维度补 0
        assert len(result.findings) == 6

    def test_severity_clamped_to_unit_range(self) -> None:
        raw = {
            "findings": [
                {"dimension": "consistency", "severity": 1.5, "finding": "x"},
                {"dimension": "evidence", "severity": -0.3, "finding": "y"},
            ],
        }
        result = _parse_critic_response(raw)
        c = next(f for f in result.findings if f.dimension == "consistency")
        e = next(f for f in result.findings if f.dimension == "evidence")
        assert c.severity == 1.0
        assert e.severity == 0.0

    def test_overall_severity_is_max(self) -> None:
        raw = {
            "findings": [
                {"dimension": "consistency", "severity": 0.3, "finding": "x"},
                {"dimension": "duplication", "severity": 0.85, "finding": "重复实体"},
                {"dimension": "evidence", "severity": 0.4, "finding": "x"},
            ],
        }
        result = _parse_critic_response(raw)
        assert result.overall_severity == 0.85

    def test_empty_findings_returns_six_zeros(self) -> None:
        result = _parse_critic_response({"summary": ""})
        assert len(result.findings) == 6
        assert all(f.severity == 0.0 for f in result.findings)
        assert result.overall_severity == 0.0


# ════════════════════════════════════════════════════════════════════════
#  has_blocking_issue
# ════════════════════════════════════════════════════════════════════════


class TestBlockingIssue:
    def test_severity_above_threshold_blocks(self) -> None:
        result = CriticResult(findings=[
            CriticFinding(dimension="consistency", severity=0.7),
        ])
        assert result.has_blocking_issue() is True

    def test_below_threshold_not_blocking(self) -> None:
        result = CriticResult(findings=[
            CriticFinding(dimension="consistency", severity=0.5),
        ])
        assert result.has_blocking_issue() is False

    def test_custom_threshold(self) -> None:
        result = CriticResult(findings=[
            CriticFinding(dimension="evidence", severity=0.3),
        ])
        assert result.has_blocking_issue(threshold=0.2) is True


# ════════════════════════════════════════════════════════════════════════
#  run_critic / arun_critic
# ════════════════════════════════════════════════════════════════════════


class TestRunCriticSync:
    def test_normal_path(self) -> None:
        with patch(
            "packages.distillation.agents.critic.call_llm_json",
            return_value={
                "findings": [
                    {"dimension": "evidence", "severity": 0.6, "finding": "证据弱"},
                ],
                "summary": "证据需补强",
            },
        ):
            result = run_critic(_doc(), _librarian(), None, _judge())
        assert result.overall_severity == 0.6
        assert "证据" in result.summary

    def test_llm_failure_returns_empty_critic(self) -> None:
        """LLM 调用失败 → 返回空 critic，pipeline 不阻断。"""
        with patch(
            "packages.distillation.agents.critic.call_llm_json",
            side_effect=Exception("LLM down"),
        ):
            result = run_critic(_doc(), _librarian(), None, _judge())
        assert result.overall_severity == 0.0
        assert "失败" in result.summary


class TestArunCriticAsync:
    async def test_async_path(self) -> None:
        with patch(
            "packages.distillation.agents.critic.acall_llm_json",
            return_value={
                "findings": [
                    {"dimension": "timeliness", "severity": 0.8,
                     "finding": "GB/T 6075-2003 已作废"},
                ],
                "summary": "标准过期",
            },
        ):
            result = await arun_critic(_doc(), _librarian(), None, _judge())
        assert result.has_blocking_issue() is True
        assert any(f.dimension == "timeliness" and f.severity == 0.8
                   for f in result.findings)


# ════════════════════════════════════════════════════════════════════════
#  critic_to_review_description
# ════════════════════════════════════════════════════════════════════════


class TestReviewDescription:
    def test_only_salient_findings_included(self) -> None:
        critic = CriticResult(
            findings=[
                CriticFinding(dimension="consistency", severity=0.1, finding="无大问题"),
                CriticFinding(dimension="evidence", severity=0.5, finding="证据偏弱"),
                CriticFinding(dimension="timeliness", severity=0.9, finding="标准作废"),
            ],
            summary="时效问题严重",
        )
        desc = critic_to_review_description(critic, base_desc="原描述")
        assert "原描述" in desc
        assert "时效问题严重" in desc
        assert "evidence" in desc      # severity 0.5 >= 0.3 → 列出
        assert "timeliness" in desc    # severity 0.9 → 列出
        assert "consistency" not in desc  # severity 0.1 < 0.3 → 不列

    def test_no_findings_returns_base_only(self) -> None:
        critic = CriticResult(findings=[], summary="")
        assert critic_to_review_description(critic, base_desc="原") == "原"
