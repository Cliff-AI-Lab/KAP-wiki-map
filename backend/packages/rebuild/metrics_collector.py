"""promote 后指标采集（M5 #2 · 决策书 §5.3 观察期）。

M5 lite 采集维度（轻量化优先，运行时数据指标留 M5 完整版）：
- 实体节点总数
- 关系总数
- 实体类型分布
- 自定义关系比例（type_id 不在已注册关系类型列表中的占比）

不采集（M5 完整版接 OLTP/Skywalking）：
- 召回率 / 命中率（依赖查询统计）
- SME 驳回率（依赖审核台流水）
- 用户主动反馈（依赖 portal 埋点）
"""

from __future__ import annotations

from packages.common import get_logger
from packages.common.types import PromotionMetrics
from packages.rebuild.shadow_graph import ShadowGraphStore, get_shadow_store

log = get_logger("rebuild.metrics")


def collect_metrics(
    project_id: str,
    version: str,
    *,
    known_relation_type_ids: set[str] | None = None,
    shadow: ShadowGraphStore | None = None,
) -> PromotionMetrics:
    """采集某 (project, version) 当前的图谱指标快照。

    Args:
        known_relation_type_ids: 已注册的 L1+L2 关系 type_id 集合
            （传入则计算 custom_relation_ratio；不传则跳过该指标）
    """
    s = shadow or get_shadow_store()
    entity_count = s.entity_count(project_id, version)
    relation_count = s.relation_count(project_id, version)
    distribution = s.entity_type_distribution(project_id, version)

    custom_ratio = 0.0
    if relation_count > 0 and known_relation_type_ids is not None:
        relations = s.list_relations(project_id, version)
        custom = sum(
            1 for e in relations
            if e.get("relation_type_id") not in known_relation_type_ids
        )
        custom_ratio = custom / relation_count

    return PromotionMetrics(
        project_id=project_id,
        version=version,
        entity_count=entity_count,
        relation_count=relation_count,
        entity_type_distribution=distribution,
        custom_relation_ratio=round(custom_ratio, 4),
    )


def compute_drift(
    baseline: PromotionMetrics,
    current: PromotionMetrics,
) -> dict:
    """对比基线 vs 当前 → 返回漂移指标 dict（绝对值版本）。

    返回字段：
        entity_count_delta_pct: 实体数变化比例（带符号）
        relation_count_delta_pct: 关系数变化比例
        custom_relation_ratio_baseline / _current
        lost_key_types: baseline 中占比 ≥ 10% 但 current 中为 0 的 type_ids
    """
    out: dict = {}

    if baseline.entity_count > 0:
        out["entity_count_delta_pct"] = round(
            (current.entity_count - baseline.entity_count) / baseline.entity_count, 4
        )
    else:
        out["entity_count_delta_pct"] = 0.0

    if baseline.relation_count > 0:
        out["relation_count_delta_pct"] = round(
            (current.relation_count - baseline.relation_count) / baseline.relation_count, 4
        )
    else:
        out["relation_count_delta_pct"] = 0.0

    out["custom_relation_ratio_baseline"] = baseline.custom_relation_ratio
    out["custom_relation_ratio_current"] = current.custom_relation_ratio

    lost_key_types: list[str] = []
    if baseline.entity_count > 0:
        for t, c in baseline.entity_type_distribution.items():
            if c / baseline.entity_count >= 0.1:
                if current.entity_type_distribution.get(t, 0) == 0:
                    lost_key_types.append(t)
    out["lost_key_types"] = lost_key_types

    return out
