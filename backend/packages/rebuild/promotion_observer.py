"""promote 后 7 天观察期（M5 #2 · 决策书 §5.3）。

工作流（M5 lite）：

1. ``promote_shadow`` 成功后，switch_orchestrator 调 ``start_observation`` 记录 baseline 快照
2. SME 或定时器调 ``tick_observation`` 采样 → 对比 baseline → 检测漂移
3. 超阈值 → status=alert + alerts 列表追加，不自动 rollback（让 SME 决策）
4. 7 天到期 → status=expired

设计原则（feedback memory · AI native + 轻量化）：
- 函数式 API + 内存存储（PG 持久化留后续）
- 不自动 rollback（决策书 §5.3 锁定 SME 主导）
- 单 project 同时只允许一个活跃观察期
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from packages.common import get_logger
from packages.common.types import PromotionObservation
from packages.rebuild.metrics_collector import collect_metrics, compute_drift
from packages.rebuild.shadow_graph import ShadowGraphStore

log = get_logger("rebuild.observer")


# ────────────────────────────────────────────────────────────────────────
#  常量
# ────────────────────────────────────────────────────────────────────────

OBSERVATION_DAYS = 7  # 决策书 §5.3 锁定

# 漂移告警阈值
_ENTITY_DELTA_ALERT = 0.5         # 实体数变化 > 50%
_RELATION_DELTA_ALERT = 0.5       # 关系数变化 > 50%
_CUSTOM_RATIO_GROWTH_ALERT = 2.0  # 自定义关系比例增长 > 200%
_CUSTOM_RATIO_FROM_ZERO_ALERT = 0.1  # 基线为 0 时，current > 10% 即告警


# ────────────────────────────────────────────────────────────────────────
#  内存存储（M5 lite，PG 持久化留后续）
# ────────────────────────────────────────────────────────────────────────

_observations: dict[str, PromotionObservation] = {}
_current: dict[str, str] = {}  # project_id → 当前活跃 observation_id


def reset_observations_for_test() -> None:
    _observations.clear()
    _current.clear()


def list_observations(project_id: str | None = None) -> list[PromotionObservation]:
    """列出观察期记录（None = 全部，否则按 project_id 过滤）。"""
    out = list(_observations.values())
    if project_id is not None:
        out = [o for o in out if o.project_id == project_id]
    return sorted(out, key=lambda o: o.promoted_at, reverse=True)


def get_observation(observation_id: str) -> PromotionObservation | None:
    return _observations.get(observation_id)


def get_current_observation(project_id: str) -> PromotionObservation | None:
    obs_id = _current.get(project_id)
    return _observations.get(obs_id) if obs_id else None


# ────────────────────────────────────────────────────────────────────────
#  主流程
# ────────────────────────────────────────────────────────────────────────


def start_observation(
    project_id: str,
    version: str,
    *,
    known_relation_type_ids: set[str] | None = None,
    shadow: ShadowGraphStore | None = None,
) -> PromotionObservation:
    """promote 后立即调用 → 启动 7 天观察期，记录 baseline 快照。

    若该 project 已有活跃观察期，旧的标记 expired 后再开新的。
    """
    if project_id in _current:
        old = _observations.get(_current[project_id])
        if old and old.status == "watching":
            old.status = "expired"
            log.info("promotion_observation_superseded",
                     project_id=project_id, old_id=old.observation_id)

    baseline = collect_metrics(
        project_id, version,
        known_relation_type_ids=known_relation_type_ids,
        shadow=shadow,
    )

    obs_id = f"obs_{uuid.uuid4().hex[:10]}"
    now = datetime.now(tz=None)
    obs = PromotionObservation(
        observation_id=obs_id,
        project_id=project_id,
        version=version,
        promoted_at=now,
        expires_at=now + timedelta(days=OBSERVATION_DAYS),
        baseline=baseline,
        status="watching",
    )
    _observations[obs_id] = obs
    _current[project_id] = obs_id

    log.info(
        "promotion_observation_started",
        project_id=project_id, version=version,
        observation_id=obs_id,
        expires_at=obs.expires_at.isoformat(),
        baseline_entities=baseline.entity_count,
        baseline_relations=baseline.relation_count,
    )
    return obs


def tick_observation(
    project_id: str,
    *,
    known_relation_type_ids: set[str] | None = None,
    shadow: ShadowGraphStore | None = None,
) -> PromotionObservation | None:
    """单次观察期采样 + 检查（SME 或外部定时器调用）。

    Returns:
        更新后的 PromotionObservation；None = 该项目无活跃观察期
    """
    obs = get_current_observation(project_id)
    if obs is None:
        return None
    if obs.status in ("expired", "rolled_back"):
        return obs

    now = datetime.now(tz=None)
    if now >= obs.expires_at:
        obs.status = "expired"
        log.info(
            "promotion_observation_expired",
            project_id=project_id, observation_id=obs.observation_id,
        )
        return obs

    snapshot = collect_metrics(
        project_id, obs.version,
        known_relation_type_ids=known_relation_type_ids,
        shadow=shadow,
    )
    obs.snapshots.append(snapshot)

    drift = compute_drift(obs.baseline, snapshot)
    new_alerts = _check_alerts(drift)
    if new_alerts:
        for a in new_alerts:
            if a not in obs.alerts:
                obs.alerts.append(a)
        obs.status = "alert"
        log.warning(
            "promotion_observation_alert",
            project_id=project_id,
            observation_id=obs.observation_id,
            alerts=new_alerts,
        )

    return obs


def mark_rolled_back(project_id: str) -> bool:
    """rollback_promotion 调用 → 把活跃观察期标记 rolled_back。"""
    obs = get_current_observation(project_id)
    if obs is None:
        return False
    obs.status = "rolled_back"
    log.info(
        "promotion_observation_rolled_back",
        project_id=project_id, observation_id=obs.observation_id,
    )
    return True


# ────────────────────────────────────────────────────────────────────────
#  告警规则
# ────────────────────────────────────────────────────────────────────────


def _check_alerts(drift: dict) -> list[str]:
    alerts: list[str] = []

    entity_delta = abs(float(drift.get("entity_count_delta_pct", 0.0)))
    if entity_delta > _ENTITY_DELTA_ALERT:
        alerts.append(
            f"实体数变化 {entity_delta:.0%} > 阈值 {_ENTITY_DELTA_ALERT:.0%}"
        )

    rel_delta = abs(float(drift.get("relation_count_delta_pct", 0.0)))
    if rel_delta > _RELATION_DELTA_ALERT:
        alerts.append(
            f"关系数变化 {rel_delta:.0%} > 阈值 {_RELATION_DELTA_ALERT:.0%}"
        )

    base = float(drift.get("custom_relation_ratio_baseline", 0.0))
    cur = float(drift.get("custom_relation_ratio_current", 0.0))
    if base > 0.01:
        if cur / base > _CUSTOM_RATIO_GROWTH_ALERT:
            alerts.append(
                f"自定义关系比例从 {base:.1%} 涨到 {cur:.1%}"
                f"（>{_CUSTOM_RATIO_GROWTH_ALERT:.0f}x）"
            )
    elif cur > _CUSTOM_RATIO_FROM_ZERO_ALERT:
        alerts.append(
            f"自定义关系比例从 ~0 涨到 {cur:.1%}（本体覆盖度下降）"
        )

    lost = drift.get("lost_key_types", [])
    if isinstance(lost, list) and lost:
        alerts.append(f"关键实体类型消失：{', '.join(lost[:5])}")

    return alerts
