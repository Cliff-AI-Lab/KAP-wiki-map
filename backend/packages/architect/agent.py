"""ArchitectAgent — 块① 对话状态机（决策书 §4.1）。

4 阶段流程（决策书 §4.1）：

    identify  → propose  → refine  → export

每阶段对应一个 transition 函数；``process_message(session, user_msg)`` 主入口
按 session.stage 路由到对应 transition。

设计原则（feedback memory · AI native + 轻量化）：
- 函数式 + dict-based 内存 session store，不上 LangGraph 等重框架
- transition 函数纯函数化（除 LLM 调用副作用外），便于单测
- 状态推进失败时 stage 回退（不阻断后续重试）

M2 lite：
- session 内存存储（单实例，重启丢失）
- refine 阶段简单实现（add/remove/rename 命令），完整 CRUD 留 M3
- 不接 PG / Redis 持久化
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from packages.common import get_logger
from packages.common.types import ArchitectSession, TaxonomyDraft

log = get_logger("architect.agent")


class ArchitectAgent:
    """块① 对话状态机。

    内存 session store（M3 接 PG）；单例由 get_architect_agent() 管理。
    """

    def __init__(self) -> None:
        self._sessions: dict[str, ArchitectSession] = {}

    # ── Session CRUD ──

    def create_session(
        self,
        project_id: str,
        sample_texts: list[str] | None = None,
    ) -> ArchitectSession:
        """新建对话会话（PRD F1.1 项目初始化）。

        Args:
            project_id: 多租户项目 ID
            sample_texts: 上传材料样本（标题 + 摘要），下一步 identify 用
        """
        session_id = f"arch_{uuid.uuid4().hex[:12]}"
        session = ArchitectSession(
            session_id=session_id,
            project_id=project_id,
            stage="identify",
            history=[],
        )
        if sample_texts:
            session.history.append({
                "role": "system",
                "content": f"用户上传了 {len(sample_texts)} 份样本材料",
                "timestamp": datetime.now().isoformat(),
                "samples_preview": [t[:100] for t in sample_texts[:3]],
            })
        self._sessions[session_id] = session
        log.info("architect_session_created",
                 session_id=session_id, project_id=project_id,
                 samples=len(sample_texts or []))
        return session

    def get_session(self, session_id: str) -> ArchitectSession | None:
        return self._sessions.get(session_id)

    def list_sessions(self, project_id: str | None = None) -> list[ArchitectSession]:
        out = list(self._sessions.values())
        if project_id:
            out = [s for s in out if s.project_id == project_id]
        return out

    # ── 阶段 transition（按 session.stage 路由）──

    async def process_message(
        self,
        session_id: str,
        user_msg: str,
        sample_texts: list[str] | None = None,
    ) -> dict[str, Any]:
        """对话主入口 — 按当前 stage 路由到对应 transition。

        Returns:
            {"assistant": str, "stage": ArchitectStage, "draft": TaxonomyDraft | None}
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError(f"session 不存在: {session_id}")

        # 记录用户消息
        session.history.append({
            "role": "user", "content": user_msg,
            "timestamp": datetime.now().isoformat(),
        })

        # 路由到 stage transition
        if session.stage == "identify":
            assistant = await self._transition_identify(session, sample_texts or [])
        elif session.stage == "propose":
            assistant = await self._transition_propose(session)
        elif session.stage == "refine":
            assistant = await self._transition_refine(session, user_msg)
        elif session.stage == "export":
            assistant = "体系已导出，无需进一步对话。如需重新调整，请新建会话。"
        else:
            assistant = "未知阶段，请联系管理员"

        # 记录 assistant 回复
        session.history.append({
            "role": "assistant", "content": assistant,
            "timestamp": datetime.now().isoformat(),
            "stage_after": session.stage,
        })
        session.updated_at = datetime.now()

        return {
            "assistant": assistant,
            "stage": session.stage,
            "draft": session.draft.model_dump() if session.draft else None,
        }

    # ── 阶段实现（批 2/3 完善；本批仅占位）──

    async def _transition_identify(
        self,
        session: ArchitectSession,
        sample_texts: list[str],
    ) -> str:
        """阶段 1: 行业识别（批 2 接 industry_recognizer）。"""
        if not sample_texts and (session.draft is None or not session.draft.industry_code):
            return (
                "您好！我是 KAP 知识架构师智能体。请先上传 5-10 份代表性材料"
                "（如制度文件、SOP、研发报告等），我会自动识别行业并提议主树。"
            )

        # 批 2 实现：调 industry_recognizer
        try:
            from packages.architect.industry_recognizer import recognize_industry
            result = await recognize_industry(sample_texts)
        except (ImportError, AttributeError):
            # 批 1 阶段 industry_recognizer 还没建 — 占位
            log.info("architect_identify_placeholder", session_id=session.session_id)
            session.draft = TaxonomyDraft(
                industry_code="manufacturing",
                industry_name="制造业（占位 — 待批 2 接入识别器）",
                confidence=0.5,
            )
            return "（批 1 阶段占位：批 2 接入 industry_recognizer 后给真实识别结果）"

        # 写入 draft
        session.draft = TaxonomyDraft(
            industry_code=result.industry_code,
            industry_name=result.industry_name,
            confidence=result.confidence,
            recognized_signals=result.recognized_signals,
            top_candidates=result.top_candidates,
        )

        # 决策书 §4.1：低置信度提示用户上传更多材料（PRD F1.1.5 推荐 200+）
        if result.confidence < 0.5:
            return (
                f"识别置信度较低（{result.confidence:.2f}）。"
                f"候选行业 top 3：{[c.industry_name for c in result.top_candidates[:3]]}。"
                f"建议上传更多代表性材料（≥50 份），或直接告诉我贵司行业。"
            )

        # 进入下一阶段
        session.stage = "propose"
        return (
            f"识别为「{result.industry_name}」（置信度 {result.confidence:.2f}）。"
            f"依据：{', '.join(result.recognized_signals[:5])}。"
            f"\n\n回复 \"确认\" 我会基于行业模板提议初版主树；如有偏差请告诉我正确行业。"
        )

    async def _transition_propose(self, session: ArchitectSession) -> str:
        """阶段 2: 主树提议（批 3 接 taxonomy_builder）。"""
        if session.draft is None:
            return "缺少行业识别结果，请回到 identify 阶段。"
        try:
            from packages.architect.taxonomy_builder import propose_taxonomy
            sample_texts = [
                h.get("content", "") for h in session.history if h.get("role") == "user"
            ]
            taxonomy = await propose_taxonomy(session.draft.industry_code, sample_texts)
            session.draft.taxonomy = taxonomy
        except (ImportError, AttributeError):
            log.info("architect_propose_placeholder", session_id=session.session_id)
            return "（批 1 阶段占位：批 3 接入 taxonomy_builder 后提议真实主树）"

        session.stage = "refine"
        return (
            f"已基于「{session.draft.industry_name}」模板提议 {len(session.draft.taxonomy)} 个一级业务域。"
            f"您可以告诉我：要修改哪个节点（如 \"删除 仓储管理\"）、合并哪些节点、或新增什么。"
            f"满意后回复 \"导出\"。"
        )

    async def _transition_refine(self, session: ArchitectSession, user_msg: str) -> str:
        """阶段 3: 客户对话调整（批 3 接 apply_user_command）。"""
        if session.draft is None:
            return "缺少主树草稿，请回到 propose 阶段。"

        # 检查导出指令
        if any(kw in user_msg for kw in ("导出", "完成", "确认导出", "提交")):
            session.stage = "export"
            return (
                f"准备导出体系。请调用 POST /architect/sessions/{session.session_id}/export "
                f"完成导出 + 注册到行业模板库。"
            )

        try:
            from packages.architect.taxonomy_builder import apply_user_command
            session.draft = apply_user_command(session.draft, user_msg)
        except (ImportError, AttributeError):
            log.info("architect_refine_placeholder", session_id=session.session_id)
            return "（批 1 阶段占位：批 3 接入 apply_user_command 后真实调整）"

        return (
            f"已应用调整。当前主树有 {len(session.draft.taxonomy)} 个一级节点。"
            f"继续调整或回复 \"导出\" 完成。"
        )


# ════════════════════════════════════════════════════════════════════════
#  全局单例
# ════════════════════════════════════════════════════════════════════════

_global_agent: ArchitectAgent | None = None


def get_architect_agent() -> ArchitectAgent:
    """懒加载全局 ArchitectAgent 单例（M2 lite 内存模式）。"""
    global _global_agent
    if _global_agent is None:
        _global_agent = ArchitectAgent()
    return _global_agent


def reset_architect_agent_for_test() -> None:
    """测试用：清掉单例。"""
    global _global_agent
    _global_agent = None
