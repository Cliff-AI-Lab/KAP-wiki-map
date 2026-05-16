"""M22 #7 · 增量重抽 lite 模式 — 影响面分析 + 增量计划生成。

M4 全量重抽影子库 在大客户场景（10万+ 文档）下成本不可接受, 尤其 MinerU
接入后单文档解析成本翻倍。本模块提供基于本体 diff 的"影响面分析": 算出哪些
文档需要全量重抽 / 部分重抽 / 完全跳过, 输出 RebuildPlan + 估算成本。

设计原则:
- 纯函数实现, 不依赖具体 store; doc → type_id 映射由 caller 提供（来自
  graph_store / entity_index 任选）
- 7 天观察期 + 灰度切换路径 **保持不变**（D8 锁定）
- 全量重抽路径保留（兼容老路径 + 大版本升级场景）
- L1 类型变更 = 全量重抽（行业本体扩展, 影响所有文档）
- L2 类型变更 = 增量（只重抽用到该类型的文档）
"""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.common import get_logger
from packages.common.types import OntologyDiff

log = get_logger("rebuild.incremental")


@dataclass
class RebuildPlan:
    """增量重抽计划。"""
    project_id: str
    from_version: str
    to_version: str
    full_docs: list[str] = field(default_factory=list)       # 必须全量重抽
    partial_docs: list[str] = field(default_factory=list)    # 仅重抽变化部分实体/关系
    skipped_docs: list[str] = field(default_factory=list)    # 完全跳过（不受影响）
    affected_type_ids: set[str] = field(default_factory=set)
    affected_relation_ids: set[str] = field(default_factory=set)
    est_cost_units: int = 0                                   # 估算成本（单位 = 1 文档解析）
    est_savings_ratio: float = 0.0                            # vs 全量重抽节省比例

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "full_docs": self.full_docs,
            "partial_docs": self.partial_docs,
            "skipped_docs": self.skipped_docs,
            "full_count": len(self.full_docs),
            "partial_count": len(self.partial_docs),
            "skipped_count": len(self.skipped_docs),
            "affected_type_ids": sorted(self.affected_type_ids),
            "affected_relation_ids": sorted(self.affected_relation_ids),
            "est_cost_units": self.est_cost_units,
            "est_savings_ratio": round(self.est_savings_ratio, 3),
        }


def collect_affected_types(diff: OntologyDiff) -> tuple[set[str], set[str]]:
    """从 OntologyDiff 提取所有"被影响"的 type_id 集合（增/删/改 实体 + 关系）。"""
    affected_entity = (
        set(diff.added_entity_types)
        | set(diff.removed_entity_types)
        | set(diff.modified_entity_types)
    )
    affected_relation = (
        set(diff.added_relation_types)
        | set(diff.removed_relation_types)
        | set(diff.modified_relation_types)
    )
    return affected_entity, affected_relation


def analyze_impact(
    diff: OntologyDiff,
    doc_to_types: dict[str, set[str]],
    project_id: str = "",
    l1_changed: bool = False,
) -> RebuildPlan:
    """基于本体 diff + 文档→类型索引 算出增量重抽计划。

    Args:
        diff: 本体两版本之间的差异（来自 OntologyStore.diff）
        doc_to_types: {doc_id → set[已抽实体的 type_id]}; 由 caller 从
            graph_store / entity_index 查; 空 dict 视为该项目无入库文档
        project_id: 项目 id（仅用于回填 RebuildPlan）
        l1_changed: True 时强制全量重抽（L1 行业本体变更影响所有文档）

    Returns:
        RebuildPlan, 含 full/partial/skipped 三组 + 成本估算
    """
    affected_e, affected_r = collect_affected_types(diff)

    plan = RebuildPlan(
        project_id=project_id,
        from_version=diff.from_version,
        to_version=diff.to_version,
        affected_type_ids=affected_e,
        affected_relation_ids=affected_r,
    )

    total_docs = len(doc_to_types)
    if total_docs == 0:
        return plan

    if l1_changed:
        # L1 变更必须全量重抽 — 行业本体的类型可能"突然出现"在任何文档里
        plan.full_docs = sorted(doc_to_types.keys())
        plan.est_cost_units = total_docs
        plan.est_savings_ratio = 0.0
        log.info("incremental_rebuild_l1_changed_full",
                 project=project_id, full=total_docs)
        return plan

    # L2 变更走增量：被影响 type 出现在哪些文档里
    # 删除/修改 类型 → partial（重新抽该类型实体, 旧实体覆盖）
    # 新增类型 → full（旧文档可能漏抽了, 需要全文重扫）
    has_new_type = bool(diff.added_entity_types or diff.added_relation_types)

    for doc_id, type_ids in doc_to_types.items():
        if has_new_type:
            plan.full_docs.append(doc_id)
            continue
        # 仅有删除/修改：用到被改类型的文档 → partial, 其他 skip
        if type_ids & affected_e:
            plan.partial_docs.append(doc_id)
        else:
            plan.skipped_docs.append(doc_id)

    plan.full_docs.sort()
    plan.partial_docs.sort()
    plan.skipped_docs.sort()

    # 成本估算：full = 1 unit, partial = 0.3 unit（仅重抽变化部分）
    plan.est_cost_units = int(
        len(plan.full_docs) * 1.0 + len(plan.partial_docs) * 0.3
    )
    full_baseline = total_docs * 1.0
    if full_baseline > 0:
        plan.est_savings_ratio = max(0.0, 1.0 - plan.est_cost_units / full_baseline)

    log.info(
        "incremental_rebuild_plan_ready",
        project=project_id,
        from_v=diff.from_version, to_v=diff.to_version,
        full=len(plan.full_docs), partial=len(plan.partial_docs),
        skipped=len(plan.skipped_docs),
        est_cost=plan.est_cost_units,
        savings=round(plan.est_savings_ratio, 3),
    )

    return plan
