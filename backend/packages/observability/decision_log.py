"""SME / 系统决策日志（M6 #3 · 决策书 §5.3 简单指标聚合）。

记录关键决策事件（本体提议批 / 驳，灰度切换，回滚等），按时间窗口 / 项目
/ actor 聚合计数。给 SME / 运营看演化健康趋势。

存储模式（M7 #1 加 PG 持久化）：
- 内存 list 永远是读路径（list / aggregate 从 _events 读）
- PG sink 是 write-through 的可选副本（sink 异常不影响主流程）
- 启动 ``initialize_pg_decision_log`` 后水化最近 N 条事件

设计原则（feedback memory · 轻量化）：
- 函数式 API
- 失败不抛异常（log 即可）
- record_decision (sync) → fire-and-forget PG write
- arecord_decision (async) → 等待 PG 写入（更强持久性保证）
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Awaitable, Callable, Literal

from pydantic import BaseModel, Field

from packages.common import get_logger

log = get_logger("observability.decision_log")


DecisionType = Literal[
    "approve_proposal",   # 本体提议批准
    "reject_proposal",    # 本体提议驳回
    "promote",            # 灰度切换
    "rollback",           # 回滚
    "alert_acknowledged", # SME 确认观察期告警
    "facet_approved",     # 4×6 矩阵审核通过
    "facet_rejected",     # 4×6 矩阵审核驳回
]


class DecisionEvent(BaseModel):
    project_id: str
    decision_type: DecisionType
    actor: str = ""                   # SME 用户 id（"" = system）
    target_id: str = ""               # 关联对象 id（如 proposal_id / version）
    note: str = ""
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))


# 内存存储（M6 lite 模式 + M7 PG 持久化的读路径）
_events: list[DecisionEvent] = []

# PG sink（async；通过 ``set_pg_sink`` 注入）
_pg_sink: Callable[[DecisionEvent], Awaitable[None]] | None = None


def reset_decisions_for_test() -> None:
    """清空内存 + 摘除 PG sink（仅测试用）。"""
    global _pg_sink
    _events.clear()
    _pg_sink = None


def set_pg_sink(
    sink: Callable[[DecisionEvent], Awaitable[None]] | None,
) -> None:
    """注入 PG 写入 sink（``initialize_pg_decision_log`` 内部用）。"""
    global _pg_sink
    _pg_sink = sink


def _build_event(
    *, project_id: str, decision_type: DecisionType,
    actor: str, target_id: str, note: str,
) -> DecisionEvent:
    event = DecisionEvent(
        project_id=project_id, decision_type=decision_type,
        actor=actor, target_id=target_id, note=note,
    )
    _events.append(event)
    log.info(
        "decision_recorded",
        project_id=project_id, type=decision_type,
        actor=actor or "system", target=target_id,
    )
    return event


def record_decision(
    *,
    project_id: str,
    decision_type: DecisionType,
    actor: str = "",
    target_id: str = "",
    note: str = "",
) -> DecisionEvent:
    """记录一条决策事件（同步 API · fire-and-forget PG 写入）。

    PG sink 已配置时：用 ``asyncio.create_task`` 异步落盘。
    无 running loop / sink 未配置 → 仅写内存（M6 lite 行为）。
    """
    event = _build_event(
        project_id=project_id, decision_type=decision_type,
        actor=actor, target_id=target_id, note=note,
    )
    if _pg_sink is not None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_pg_sink(event))
        except RuntimeError:
            pass
    return event


async def arecord_decision(
    *,
    project_id: str,
    decision_type: DecisionType,
    actor: str = "",
    target_id: str = "",
    note: str = "",
) -> DecisionEvent:
    """异步 API · 同样追加内存 + 等待 PG 写入（强持久性保证）。"""
    event = _build_event(
        project_id=project_id, decision_type=decision_type,
        actor=actor, target_id=target_id, note=note,
    )
    if _pg_sink is not None:
        try:
            await _pg_sink(event)
        except Exception as e:
            log.warning("decision_log_pg_write_failed", error=str(e))
    return event


def list_decisions(
    *,
    project_id: str | None = None,
    decision_type: DecisionType | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 200,
) -> list[DecisionEvent]:
    """列出决策事件（可按 project / 类型 / 时间窗口过滤）。"""
    # 反向迭代 _events（最新优先）；datetime.now() 分辨率不够会让相同时间戳事件
    # 通过 sort 重新排序失序，所以按插入顺序倒序更稳定。
    out: list[DecisionEvent] = []
    for e in reversed(_events):
        if project_id is not None and e.project_id != project_id:
            continue
        if decision_type is not None and e.decision_type != decision_type:
            continue
        if since is not None and e.occurred_at < since:
            continue
        if until is not None and e.occurred_at > until:
            continue
        out.append(e)
        if len(out) >= limit:
            break
    return out


def aggregate_decisions(
    *,
    project_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict:
    """按 decision_type 聚合计数 + 衍生指标。

    返回:
        {
            "total": int,
            "by_type": {decision_type: count, ...},
            "approval_rate": float,    # approved / (approved + rejected)，无样本时 0
            "promote_rollback_ratio": float,  # promote / max(rollback, 1)
            "window": {since, until, project_id}
        }
    """
    events = list_decisions(
        project_id=project_id, since=since, until=until, limit=10**9,
    )
    # _events 内部满足 limit；当总量小时上面就够了
    by_type: dict[str, int] = {}
    for e in events:
        by_type[e.decision_type] = by_type.get(e.decision_type, 0) + 1

    approved = by_type.get("approve_proposal", 0)
    rejected = by_type.get("reject_proposal", 0)
    promoted = by_type.get("promote", 0)
    rolled = by_type.get("rollback", 0)

    if approved + rejected > 0:
        approval_rate = round(approved / (approved + rejected), 4)
    else:
        approval_rate = 0.0

    if rolled == 0:
        promote_rollback_ratio = float(promoted)  # 无回滚时直接给 promote 数
    else:
        promote_rollback_ratio = round(promoted / rolled, 4)

    return {
        "total": len(events),
        "by_type": by_type,
        "approval_rate": approval_rate,
        "promote_rollback_ratio": promote_rollback_ratio,
        "window": {
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
            "project_id": project_id,
        },
    }
