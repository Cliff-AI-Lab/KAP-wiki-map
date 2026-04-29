"""M2 #4 块① · 批 1 · ArchitectAgent 状态机骨架单测。"""

from __future__ import annotations

import pytest

from packages.architect.agent import (
    ArchitectAgent,
    get_architect_agent,
    reset_architect_agent_for_test,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_architect_agent_for_test()
    yield
    reset_architect_agent_for_test()


# ════════════════════════════════════════════════════════════════════════
#  Session CRUD
# ════════════════════════════════════════════════════════════════════════


class TestSessionLifecycle:
    def test_create_session_returns_id_and_initial_stage(self) -> None:
        agent = ArchitectAgent()
        session = agent.create_session(project_id="p1")
        assert session.session_id.startswith("arch_")
        assert session.stage == "identify"
        assert session.project_id == "p1"
        assert session.draft is None

    def test_create_session_records_samples(self) -> None:
        agent = ArchitectAgent()
        samples = ["设备点检与润滑标准", "工艺参数控制规程", "OQC 检验记录"]
        session = agent.create_session(project_id="p1", sample_texts=samples)
        assert len(session.history) == 1
        sys_msg = session.history[0]
        assert sys_msg["role"] == "system"
        assert "3 份样本" in sys_msg["content"]

    def test_get_session_returns_none_for_unknown(self) -> None:
        agent = ArchitectAgent()
        assert agent.get_session("ghost") is None

    def test_list_sessions_filters_by_project(self) -> None:
        agent = ArchitectAgent()
        agent.create_session("p1")
        agent.create_session("p1")
        agent.create_session("p2")
        assert len(agent.list_sessions()) == 3
        assert len(agent.list_sessions(project_id="p1")) == 2


# ════════════════════════════════════════════════════════════════════════
#  Singleton
# ════════════════════════════════════════════════════════════════════════


class TestSingleton:
    def test_get_returns_same_instance(self) -> None:
        a1 = get_architect_agent()
        a2 = get_architect_agent()
        assert a1 is a2

    def test_reset_creates_new_instance(self) -> None:
        a1 = get_architect_agent()
        reset_architect_agent_for_test()
        a2 = get_architect_agent()
        assert a1 is not a2


# ════════════════════════════════════════════════════════════════════════
#  process_message 路由
# ════════════════════════════════════════════════════════════════════════


class TestProcessMessage:
    async def test_unknown_session_raises(self) -> None:
        agent = ArchitectAgent()
        with pytest.raises(ValueError, match="不存在"):
            await agent.process_message("ghost", "hi")

    async def test_identify_without_samples_returns_prompt(self) -> None:
        agent = ArchitectAgent()
        s = agent.create_session("p1")
        result = await agent.process_message(s.session_id, "你好")
        assert "上传" in result["assistant"]
        assert result["stage"] == "identify"

    async def test_identify_with_samples_advances_stage(self) -> None:
        """批 2 industry_recognizer 已接入 — 模拟高置信度返回，验证 draft + stage 推进。"""
        from unittest.mock import patch
        from packages.architect.industry_recognizer import IndustryRecognitionResult
        from packages.common.types import IndustryCandidate

        async def fake_recognize(samples, **kwargs):
            return IndustryRecognitionResult(
                industry_code="manufacturing",
                industry_name="制造业",
                confidence=0.85,
                top_candidates=[IndustryCandidate(
                    industry_code="manufacturing",
                    industry_name="制造业",
                    confidence=0.85,
                )],
                recognized_signals=["生产管理", "工艺", "质量"],
                stage_used="stage1",
            )

        agent = ArchitectAgent()
        s = agent.create_session("p1")
        with patch(
            "packages.architect.industry_recognizer.recognize_industry",
            side_effect=fake_recognize,
        ):
            result = await agent.process_message(
                s.session_id, "请识别行业",
                sample_texts=["设备点检", "工艺标准"],
            )
        assert result["draft"] is not None
        assert result["draft"]["industry_code"] == "manufacturing"
        # 高置信度 → stage 推进到 propose
        assert result["stage"] == "propose"

    async def test_history_records_user_and_assistant(self) -> None:
        agent = ArchitectAgent()
        s = agent.create_session("p1")
        await agent.process_message(s.session_id, "hello")
        # 含 system + user + assistant，至少 2 条新消息
        roles = [h["role"] for h in s.history]
        assert "user" in roles
        assert "assistant" in roles

    async def test_export_stage_blocks_further_dialog(self) -> None:
        agent = ArchitectAgent()
        s = agent.create_session("p1")
        s.stage = "export"
        result = await agent.process_message(s.session_id, "再聊聊")
        assert "已导出" in result["assistant"]
        assert result["stage"] == "export"

    async def test_refine_export_keyword_advances_to_export(self) -> None:
        """refine 阶段用户回复"导出" → stage 切到 export。"""
        from packages.common.types import TaxonomyDraft
        agent = ArchitectAgent()
        s = agent.create_session("p1")
        s.stage = "refine"
        s.draft = TaxonomyDraft(
            industry_code="manufacturing", industry_name="制造业", confidence=0.8,
        )
        result = await agent.process_message(s.session_id, "导出")
        assert result["stage"] == "export"
        assert "export" in result["assistant"].lower() or "导出" in result["assistant"]


# ════════════════════════════════════════════════════════════════════════
#  Stage 推进的容错（占位路径）
# ════════════════════════════════════════════════════════════════════════


class TestStageGracefulDegradation:
    async def test_propose_without_draft_returns_error_message(self) -> None:
        agent = ArchitectAgent()
        s = agent.create_session("p1")
        s.stage = "propose"
        s.draft = None
        result = await agent.process_message(s.session_id, "继续")
        assert "缺少行业" in result["assistant"]

    async def test_refine_without_draft_returns_error_message(self) -> None:
        agent = ArchitectAgent()
        s = agent.create_session("p1")
        s.stage = "refine"
        s.draft = None
        result = await agent.process_message(s.session_id, "改一下")
        assert "缺少主树" in result["assistant"]
