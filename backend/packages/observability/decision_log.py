"""SME / 系统决策日志（M6 #3 · 决策书 §5.3 简单指标聚合）。

记录关键决策事件（本体提议批 / 驳，灰度切换，回滚等），按时间窗口 / 项目
/ actor 聚合计数。给 SME / 运营看演化健康趋势。

不做（M7 / 留 portal）：
- 召回率 / 命中率（需要 portal 查询埋点）
- 准确率（需要标注 ground truth）
- ML 评分

设计原则（feedback memory · 轻量化）：
- 内存 list，启动 reset；M7 PG 持久化
- 函数式 API
- 失败不抛异常（log 即可）
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

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


# 内存存储（M6 lite，M7 接 PG）
_events: list[DecisionEvent] = []


def reset_decisions_for_test() -> None:
    _events.clear()


def record_decision(
    *,
    project_id: str,
    decision_type: DecisionType,
    actor: str = "",
    target_id: str = "",
    note: str = "",
) -> DecisionEvent:
    """记录一条决策事件（任何调用方自愿接入）。"""
    event = DecisionEvent(
        project_id=project_id,
        decision_type=decision_type,
        actor=actor, target_id=target_id, note=note,
    )
    _events.append(event)
    log.info(
        "decision_recorded",
        project_id=project_id, type=decision_type,
        actor=actor or "system", target=target_id,
    )
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
