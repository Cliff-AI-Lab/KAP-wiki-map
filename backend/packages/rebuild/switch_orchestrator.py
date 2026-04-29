"""灰度切换 + 回滚（决策书 §5.3 7 天观察期 / 一键回退）。

M4 lite：
- compare_versions：返回 RebuildDiffReport（节点 / 实体 / 关系数 + 类型分布对比）
- promote_shadow(force)：通过启发式安全检查 → 调用 ShadowGraphStore.swap_shadow_to_main
- rollback_promotion：一键回滚到上版本

启发式安全规则（M4 lite，决策书 §5.3 提到指标观察留 M5）：
- 节点数变化 > 30%（增或减）→ 不安全（建议人审）
- 关键实体类型 在新版本中数量为 0 → 不安全
- 安全或 force=True 才放行

不做（M5）：
- 召回率 / SME 驳回率 / 命中率 等运行时指标采集
- 7 天自动观察 + 自动恶化告警
- 任意历史版本回滚
"""

from __future__ import annotations

from packages.common import get_logger
from packages.common.types import RebuildDiffReport
from packages.rebuild.promotion_observer import (
    mark_rolled_back,
    start_observation,
)
from packages.rebuild.shadow_graph import ShadowGraphStore, get_shadow_store

log = get_logger("rebuild.switch")


# ════════════════════════════════════════════════════════════════════════
#  compare_versions
# ════════════════════════════════════════════════════════════════════════


_NODE_CHANGE_THRESHOLD = 0.3   # 节点数变化 30% 阈值
_KEY_TYPE_PROTECTED_FACTOR = 0.1  # 关键类型保护阈值（< 10% 为低）


def compare_versions(
    project_id: str,
    source_version: str,
    target_version: str,
    *,
    shadow: ShadowGraphStore | None = None,
) -> RebuildDiffReport:
    """对比两版本图谱，返回 RebuildDiffReport + 启发式 safe_to_promote。"""
    s = shadow or get_shadow_store()

    src_node_count = s.entity_count(project_id, source_version)
    tgt_node_count = s.entity_count(project_id, target_version)
    src_rel_count = s.relation_count(project_id, source_version)
    tgt_rel_count = s.relation_count(project_id, target_version)

    src_dist = s.entity_type_distribution(project_id, source_version)
    tgt_dist = s.entity_type_distribution(project_id, target_version)

    added = sorted(set(tgt_dist) - set(src_dist))
    removed = sorted(set(src_dist) - set(tgt_dist))

    # ── 启发式安全检查 ──
    safety_reasons: list[str] = []

    # 1. 节点数变化幅度
    if src_node_count > 0:
        delta = abs(tgt_node_count - src_node_count) / src_node_count
        if delta > _NODE_CHANGE_THRESHOLD:
            safety_reasons.append(
                f"节点数变化 {delta:.1%} > {_NODE_CHANGE_THRESHOLD:.0%}（src={src_node_count} tgt={tgt_node_count}）"
            )

    # 2. 关键类型保护：source 中占比 ≥ 10% 的类型在 target 中不应该消失
    if src_node_count > 0:
        for type_id, count in src_dist.items():
            if count / src_node_count >= _KEY_TYPE_PROTECTED_FACTOR:
                if tgt_dist.get(type_id, 0) == 0:
                    safety_reasons.append(
                        f"关键类型 {type_id} 在新版本消失（source 占比 {count / src_node_count:.0%}）"
                    )

    safe = len(safety_reasons) == 0

    return RebuildDiffReport(
        project_id=project_id,
        source_version=source_version,
        target_version=target_version,
        source_node_count=src_node_count,
        target_node_count=tgt_node_count,
        source_relation_count=src_rel_count,
        target_relation_count=tgt_rel_count,
        entity_type_distribution_source=src_dist,
        entity_type_distribution_target=tgt_dist,
        added_entity_types=added,
        removed_entity_types=removed,
        safe_to_promote=safe,
        safety_reasons=safety_reasons,
    )


# ════════════════════════════════════════════════════════════════════════
#  promote_shadow / rollback_promotion
# ════════════════════════════════════════════════════════════════════════


class PromoteRefused(Exception):
    """启发式安全检查未通过，需要 force 才能继续。"""


def promote_shadow(
    project_id: str,
    source_version: str,
    target_version: str,
    *,
    force: bool = False,
    shadow: ShadowGraphStore | None = None,
) -> RebuildDiffReport:
    """灰度切换：影子图谱 → 主图谱（决策书 §5.3）。

    Args:
        force: True 跳过启发式检查直接切换（紧急 / SME 已审）

    Returns:
        RebuildDiffReport（含切换前的对比报告）

    Raises:
        PromoteRefused: 安全检查未通过且 force=False
        ValueError: 影子库不存在
    """
    s = shadow or get_shadow_store()
    report = compare_versions(
        project_id, source_version, target_version, shadow=s,
    )

    if not report.safe_to_promote and not force:
        raise PromoteRefused(
            f"启发式安全检查未通过 ({len(report.safety_reasons)} 项)：" +
            "; ".join(report.safety_reasons)
        )

    ok = s.swap_shadow_to_main(project_id, target_version)
    if not ok:
        raise ValueError(f"影子库不存在 (project={project_id}, version={target_version})")

    log.info(
        "shadow_promoted",
        project_id=project_id,
        source=source_version, target=target_version,
        forced=force, safe=report.safe_to_promote,
    )

    # M5 #2 · 启动 7 天观察期（baseline = 切换时刻快照）
    try:
        start_observation(project_id, target_version, shadow=s)
    except Exception as e:
        log.warning("promotion_observation_start_failed",
                    project_id=project_id, error=str(e))

    return report


def rollback_promotion(
    project_id: str,
    *,
    shadow: ShadowGraphStore | None = None,
) -> str | None:
    """一键回滚到上一版本（决策书 §5.3 7 天观察期）。

    Returns:
        回滚到的版本号；None = 无可回滚版本
    """
    s = shadow or get_shadow_store()
    rolled = s.rollback_to_previous(project_id)
    if rolled:
        log.info("promotion_rolled_back", project_id=project_id, version=rolled)
        # M5 #2 · 标记观察期 rolled_back
        try:
            mark_rolled_back(project_id)
        except Exception as e:
            log.warning("promotion_observation_mark_failed",
                        project_id=project_id, error=str(e))
    return rolled
