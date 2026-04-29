"""W4 写入侧：蒸馏管线 → 4×6 矩阵审核台 hook（决策书 §5.2 W4 必审）。

蒸馏管线（W3 切块 / W4 实体抽取）的 LLM-Critic 给出低置信度时，
本 hook 把同一条 review item 双写到 KAP M1 governance_queue_store，
带 ``workstation=W4`` / ``assigned_role=SME``（W4 主审角色，§5.2 锁定）+
``sla_due_at``（默认 60 分钟，配置项 kap_w4_sla_minutes）。

M2 升级（决策书 §5.5 D13）：
- 入工单前调 ``arun_critic`` 6 维质疑，把 finding 摘要拼到 description
- 即使 judge 高置信度，critic blocking issue 也强制升级 needs_review
- ``include_critic`` 参数可关闭（dev 测试 / 离线工具用）

V15 既有 ``metadata_store.enqueue_review`` 路径不动，本 hook 是**双写**而非替代。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from packages.common import get_logger, settings
from packages.common.types import (
    AuditResult,
    GovernanceQueueItem,
    JudgeResult,
    LibrarianResult,
    RawDocument,
)
from packages.governance.matrix import primary_role_for
from packages.storage.governance_queue_store import GovernanceQueueStore

log = get_logger("governance.distillation_hook")


async def enqueue_low_confidence_review(
    *,
    store: GovernanceQueueStore,
    project_id: str,
    doc_id: str,
    doc_title: str,
    confidence: float,
    proposed_decision: str,
    reason: str,
    workstation: str = "W4",
    # M2 #1 critic 集成（可选；非空时 hook 内部调 acritic 增强 description）
    doc: RawDocument | None = None,
    librarian: LibrarianResult | None = None,
    audit: AuditResult | None = None,
    judge: JudgeResult | None = None,
    include_critic: bool = True,
) -> GovernanceQueueItem:
    """蒸馏管线低置信度 → 4×6 矩阵审核台双写。

    Args:
        store: GovernanceQueueStore 实例
        project_id: 多租户项目 ID
        doc_id: 关联文档 ID
        doc_title: 文档标题（用于审核台展示）
        confidence: LLM Critic 置信度 0-1（< REVIEW_CONFIDENCE_THRESHOLD 才进这里）
        proposed_decision: AI 建议决策（KEEP/ARCHIVE/DISCARD）— 决策书 ReviewTask.proposed_action
        reason: 进入审核的原因（Judge.summary 或规则命中说明）
        workstation: 工位（默认 W4 实体抽取；W3 切块也可走同一 hook）

    Returns:
        新建的 GovernanceQueueItem
    """
    role = primary_role_for(workstation)  # W4 → SME；W3 → DG
    sla_minutes = getattr(settings, "kap_w4_sla_minutes", 60)
    sla_due = datetime.now(timezone.utc) + timedelta(minutes=sla_minutes)

    # priority 与置信度反相关：confidence 越低优先级越高（最低 0.0 → priority 100）
    priority = max(0, min(100, int((1.0 - confidence) * 100)))

    base_desc = (
        f"AI 建议: {proposed_decision} · 置信度 {confidence:.2f} · "
        f"理由: {reason[:200]}"
    )
    description = base_desc

    # M2 #1: 调 LLM-Critic 6 维质疑（决策书 §5.5 D13），把 finding 拼到 description
    # 失败/超时静默降级（critic 内部已 try/catch），不阻塞工单创建
    if include_critic and doc and librarian and judge:
        try:
            from packages.distillation.agents.critic import (
                arun_critic,
                critic_to_review_description,
            )
            critic_result = await arun_critic(doc, librarian, audit, judge)
            description = critic_to_review_description(critic_result, base_desc)
            # critic blocking 提升优先级（即使原 confidence 一般）
            if critic_result.has_blocking_issue():
                priority = min(100, priority + 20)
        except Exception as e:
            log.warning("critic_hook_failed_skip", doc_id=doc_id, error=str(e))

    item = GovernanceQueueItem(
        id=f"gq_{uuid.uuid4().hex[:10]}",
        project_id=project_id,
        agent="distillation",  # type: ignore[arg-type]
        kind="low_confidence_extract",  # type: ignore[arg-type]
        title=f"[W4-SME 必审] {doc_title[:80]}",
        description=description[:1000],  # 防 description 撑爆 UI
        target_ref=f"doc/{doc_id}",
        priority=priority,
        status="pending",
        created_at=datetime.now(timezone.utc),
        workstation=workstation,  # type: ignore[arg-type]
        assigned_role=role,
        sla_due_at=sla_due,
        confidence=confidence,
    )
    await store.upsert(item)
    log.info(
        "distillation_review_enqueued",
        item_id=item.id,
        doc_id=doc_id,
        workstation=workstation,
        assigned_role=role,
        confidence=confidence,
        priority=priority,
    )
    return item
