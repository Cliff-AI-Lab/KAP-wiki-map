"""影子图谱抽象（决策书 §5.3 影子库切换）。

M4 lite 实现：
- 复用现有 GraphStore 数据结构（不开新 Neo4j 实例）
- 用 ``ontology_version`` 标签隔离影子库节点（每个 chunk 抽出的实体挂上目标版本号）
- swap：把影子版本节点提升为 latest（删除主版本节点）
- rollback：保留最近 N 个版本，回退一步

M5：决策书 §5.3 提到"独立 Neo4j 实例"，更安全但运维更重。M4 lite 选择
逻辑隔离平衡复杂度（feedback memory · 轻量化）。

数据结构（每个 (project_id, ontology_version) 形成独立桶）：
  shadow_nodes[(proj, ver)] = {entity_name → {type_id, examples, doc_ids}}
  shadow_edges[(proj, ver)] = list[{source, target, relation_type_id, evidence}]
"""

from __future__ import annotations

from datetime import datetime

from packages.common import get_logger

log = get_logger("rebuild.shadow_graph")


class ShadowGraphStore:
    """影子图谱存储（M4 lite 内存模式 + 版本隔离）。

    Notes:
        本类不替代 GraphStore；GraphStore 仍承担主图谱写入。
        ShadowGraphStore 只承载"按新本体重抽"产生的实体/关系，
        promote 时由 switch_orchestrator 把数据 merge 进 GraphStore。
    """

    def __init__(self) -> None:
        # (project_id, ontology_version) → {entity_name: {...}}
        self._nodes: dict[tuple[str, str], dict[str, dict]] = {}
        # (project_id, ontology_version) → list[edge dict]
        self._edges: dict[tuple[str, str], list[dict]] = {}
        # (project_id) → 当前正在重抽的影子版本号
        self._current_shadow: dict[str, str] = {}
        # (project_id) → 上一个生效版本号（rollback 用）
        self._previous_main: dict[str, str] = {}

    # ── 影子版本注册 ──

    def begin_shadow(self, project_id: str, target_version: str) -> None:
        """标记某个版本为正在重抽的影子库。"""
        self._current_shadow[project_id] = target_version
        self._nodes.setdefault((project_id, target_version), {})
        self._edges.setdefault((project_id, target_version), [])
        log.info("shadow_begin", project_id=project_id, target_version=target_version)

    def current_shadow_version(self, project_id: str) -> str | None:
        return self._current_shadow.get(project_id)

    def cancel_shadow(self, project_id: str) -> None:
        """取消重抽 → 清掉影子库节点。"""
        target = self._current_shadow.pop(project_id, None)
        if target:
            self._nodes.pop((project_id, target), None)
            self._edges.pop((project_id, target), None)
            log.info("shadow_cancelled", project_id=project_id, version=target)

    # ── 影子库写入（重抽时 W4 抽取产物落这里）──

    def add_entity(
        self,
        project_id: str,
        version: str,
        *,
        entity_name: str,
        type_id: str,
        doc_id: str,
        properties: dict | None = None,
    ) -> None:
        bucket = self._nodes.setdefault((project_id, version), {})
        if entity_name in bucket:
            existing = bucket[entity_name]
            doc_ids: set[str] = set(existing.get("doc_ids", []))
            doc_ids.add(doc_id)
            existing["doc_ids"] = sorted(doc_ids)
            # 类型有冲突时记录（保留首次类型，但日志告警）
            if existing.get("type_id") != type_id:
                log.warning("shadow_entity_type_conflict",
                            entity=entity_name, existing=existing.get("type_id"),
                            new=type_id)
        else:
            bucket[entity_name] = {
                "type_id": type_id,
                "doc_ids": [doc_id],
                "properties": properties or {},
                "created_at": datetime.now(tz=None),  # M6 #1 时光机锚点
            }

    def add_relation(
        self,
        project_id: str,
        version: str,
        *,
        source_name: str,
        target_name: str,
        relation_type_id: str,
        doc_id: str,
        evidence: str = "",
    ) -> None:
        bucket = self._edges.setdefault((project_id, version), [])
        # 简单去重：同 source / target / relation 视为一条
        for edge in bucket:
            if (edge["source"] == source_name and edge["target"] == target_name
                    and edge["relation_type_id"] == relation_type_id):
                edge.setdefault("doc_ids", set())
                edge["doc_ids"].add(doc_id)
                return
        bucket.append({
            "source": source_name,
            "target": target_name,
            "relation_type_id": relation_type_id,
            "doc_ids": {doc_id},
            "evidence": evidence,
            "created_at": datetime.now(tz=None),  # M6 #1 时光机锚点
        })

    # ── 查询 ──

    def list_entities(self, project_id: str, version: str) -> list[dict]:
        bucket = self._nodes.get((project_id, version), {})
        return [{"name": name, **info} for name, info in bucket.items()]

    def list_relations(self, project_id: str, version: str) -> list[dict]:
        return list(self._edges.get((project_id, version), []))

    def entity_count(self, project_id: str, version: str) -> int:
        return len(self._nodes.get((project_id, version), {}))

    def relation_count(self, project_id: str, version: str) -> int:
        return len(self._edges.get((project_id, version), []))

    def entity_type_distribution(
        self, project_id: str, version: str,
    ) -> dict[str, int]:
        bucket = self._nodes.get((project_id, version), {})
        out: dict[str, int] = {}
        for info in bucket.values():
            t = info.get("type_id", "")
            if t:
                out[t] = out.get(t, 0) + 1
        return out

    # ── 时光机查询（M6 #1 · 决策书 §5.3 as_of）──

    def entities_as_of(
        self, project_id: str, version: str, before: datetime,
    ) -> list[dict]:
        """返回创建时间 ≤ before 的实体快照。"""
        bucket = self._nodes.get((project_id, version), {})
        out: list[dict] = []
        for name, info in bucket.items():
            ts = info.get("created_at")
            if ts is None or ts <= before:
                out.append({"name": name, **info})
        return out

    def relations_as_of(
        self, project_id: str, version: str, before: datetime,
    ) -> list[dict]:
        """返回创建时间 ≤ before 的关系快照。"""
        bucket = self._edges.get((project_id, version), [])
        out: list[dict] = []
        for edge in bucket:
            ts = edge.get("created_at")
            if ts is None or ts <= before:
                out.append(dict(edge))
        return out

    # ── 切换 / 回滚 ──

    def swap_shadow_to_main(self, project_id: str, target_version: str) -> bool:
        """把影子版本提升为主版本。

        M4 lite：记录 previous_main，影子版本变为 current；
        旧 main 版本数据保留供回滚。

        Returns: True 成功，False 影子库不存在
        """
        key = (project_id, target_version)
        if key not in self._nodes:
            log.warning("shadow_swap_not_found",
                        project_id=project_id, version=target_version)
            return False

        # 记录上一个 main（用于 rollback）
        prev_main = self._current_shadow.get(project_id, "")
        # M4 lite 简化：promote 时把当前 main 记为 previous，target 变为 current
        self._previous_main[project_id] = prev_main
        self._current_shadow.pop(project_id, None)

        log.info("shadow_swapped",
                 project_id=project_id, target=target_version,
                 prev_main=prev_main)
        return True

    def rollback_to_previous(self, project_id: str) -> str | None:
        """回滚到上一个 main 版本。

        Returns: 回滚到的版本号（None = 无可回滚版本）
        """
        prev = self._previous_main.get(project_id)
        if not prev:
            log.warning("shadow_rollback_no_previous", project_id=project_id)
            return None
        self._current_shadow[project_id] = prev
        self._previous_main.pop(project_id, None)
        log.info("shadow_rolled_back", project_id=project_id, version=prev)
        return prev


# ════════════════════════════════════════════════════════════════════════
#  全局单例
# ════════════════════════════════════════════════════════════════════════

_global_shadow: ShadowGraphStore | None = None


def get_shadow_store() -> ShadowGraphStore:
    global _global_shadow
    if _global_shadow is None:
        _global_shadow = ShadowGraphStore()
    return _global_shadow


def reset_shadow_store_for_test() -> None:
    global _global_shadow
    _global_shadow = None
