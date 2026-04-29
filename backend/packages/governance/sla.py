"""SLA 超时升级 sweep（决策书 §5.5 D12）。

D12 锁定：**SLA 超时不允许 LLM 自动通过**，超时必须升级到上级专家。
M1 实现：函数式 sweep_overdue_tasks，由 KAP 后台定期调用（cron / lifespan task）。
M2 接 iss-job (Quartz) 是后续工作。

不引入 celery / Quartz，保持轻量。
"""

from __future__ import annotations

from datetime import datetime, timezone

from packages.common import get_logger
from packages.governance.matrix import is_top_role, next_role_in_chain

log = get_logger("governance.sla")


async def sweep_overdue_tasks(
    store,
    now: datetime | None = None,
) -> int:
    """扫描所有 sla_due_at 已到期的工单，按升级链 escalate 到上级。

    Args:
        store: GovernanceQueueStore 实例
        now: 比较时刻，默认当前 UTC（测试可注入）

    Returns:
        本次升级数量
    """
    cutoff = now or datetime.now(timezone.utc)
    overdue = await store.find_overdue(cutoff)
    upgraded = 0

    for item in overdue:
        if item.assigned_role is None:
            # 无主审角色的旧 V15 工单，跳过（M1 后续批写入侧补全）
            continue

        target = next_role_in_chain(item.assigned_role)
        is_top = is_top_role(item.assigned_role)
        reason = (
            "SLA 超时升级（积压告警）" if is_top
            else f"SLA 超时升级 {item.assigned_role} → {target}"
        )
        await store.escalate(item.id, reason, target)
        upgraded += 1
        log.info(
            "sla_escalated",
            item_id=item.id,
            from_role=item.assigned_role,
            to_role=target,
            is_top=is_top,
        )

    if upgraded:
        log.info("sla_sweep_done", upgraded=upgraded, now=cutoff.isoformat())
    return upgraded
