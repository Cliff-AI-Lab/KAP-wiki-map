"""OntologyStore — 版本持久化 + 演化历史 + diff 计算。

M3 lite：内存模式（基于 OntologyRegistry 的版本链）。
M4 接 PG `ontology_versions` 表 + Neo4j `:Ontology` 标签 + as_of 历史回溯。

主要职责：
- 版本快照保存 / 查询（多版本链）
- 版本间 diff（用于审计 + 灰度切换 M4）
- 当前生效版本（取最新）
- 工厂方法 ``create_next_version`` 基于现有版本递增 patch
"""

from __future__ import annotations

import re
from datetime import datetime

from packages.common import get_logger
from packages.common.types import (
    OntologyDiff,
    OntologyEntityType,
    OntologyLayer,
    OntologyRelationType,
    OntologyVersion,
)
from packages.ontology.base import OntologyRegistry, get_registry

log = get_logger("ontology.store")


_VERSION_PATTERN = re.compile(r"^ont-v(\d+)\.(\d+)\.(\d+)$")


def _bump_patch(version: str) -> str:
    """ont-v1.0.0 → ont-v1.0.1。"""
    m = _VERSION_PATTERN.match(version)
    if not m:
        return f"{version}-next"
    major, minor, patch = (int(m.group(i)) for i in (1, 2, 3))
    return f"ont-v{major}.{minor}.{patch + 1}"


def _bump_minor(version: str) -> str:
    """ont-v1.0.0 → ont-v1.1.0。"""
    m = _VERSION_PATTERN.match(version)
    if not m:
        return f"{version}-minor"
    major, minor = (int(m.group(i)) for i in (1, 2))
    return f"ont-v{major}.{minor + 1}.0"


# ════════════════════════════════════════════════════════════════════════
#  OntologyStore
# ════════════════════════════════════════════════════════════════════════


class OntologyStore:
    """对 OntologyRegistry 的高层封装 + diff / 版本号自动递增。

    `registry` 默认走 get_registry() 全局单例；测试可注入独立实例。
    """

    def __init__(self, registry: OntologyRegistry | None = None) -> None:
        self._registry = registry or get_registry()

    # ── 保存 ──

    def save_version(self, version: OntologyVersion) -> OntologyVersion:
        """保存版本到对应 layer 链尾（最新生效）。"""
        if version.layer == "L1":
            self._registry.register_l1(version)
        else:
            self._registry.register_l2(version)
        log.info(
            "ontology_version_saved",
            layer=version.layer, version=version.version,
            industry=version.industry_code, project=version.project_id,
        )
        return version

    # ── 查询 ──

    def current_version(
        self, layer: OntologyLayer, *, industry_code: str = "", project_id: str = "",
    ) -> OntologyVersion | None:
        if layer == "L1":
            return self._registry.get_current_l1(industry_code)
        return self._registry.get_current_l2(project_id)

    def list_versions(
        self, layer: OntologyLayer, *, industry_code: str = "", project_id: str = "",
    ) -> list[OntologyVersion]:
        if layer == "L1":
            return self._registry.list_l1_versions(industry_code)
        return self._registry.list_l2_versions(project_id)

    def get_version(
        self, layer: OntologyLayer, key: str, version: str,
    ) -> OntologyVersion | None:
        return self._registry.get_version_by_id(layer, key, version)

    # ── 版本递增工厂 ──

    def create_next_version(
        self,
        layer: OntologyLayer,
        *,
        industry_code: str = "",
        project_id: str = "",
        bump: str = "patch",                # patch / minor
        notes: str = "",
        created_by: str = "",
    ) -> OntologyVersion:
        """基于当前最新版本 deep-copy 一份新版本，版本号自动递增。

        调用方可对返回的实例修改 entity_types / relation_types 后再 save_version。
        layer = L2 且无现有版本时，从空版本起步（version = ont-v1.0.0）。
        """
        current = self.current_version(
            layer, industry_code=industry_code, project_id=project_id,
        )
        if current is None:
            # 起步版本（仅 L2 允许；L1 应通过 builtin 内置注册）
            if layer == "L1":
                raise ValueError(f"L1 起步版本应通过 builtin 注册（industry={industry_code}）")
            return OntologyVersion(
                version="ont-v1.0.0",
                layer="L2",
                industry_code="",
                project_id=project_id,
                entity_types=[],
                relation_types=[],
                created_at=datetime.now(),
                created_by=created_by,
                notes=notes or "L2 初始版本",
            )

        next_version = (
            _bump_minor(current.version) if bump == "minor"
            else _bump_patch(current.version)
        )
        # 深拷贝 entity/relation types
        new_entity = [OntologyEntityType.model_validate(e.model_dump())
                      for e in current.entity_types]
        new_relation = [OntologyRelationType.model_validate(r.model_dump())
                        for r in current.relation_types]
        return OntologyVersion(
            version=next_version,
            layer=layer,
            industry_code=industry_code,
            project_id=project_id,
            entity_types=new_entity,
            relation_types=new_relation,
            created_at=datetime.now(),
            created_by=created_by,
            notes=notes,
        )

    # ── Diff ──

    def diff(
        self, before: OntologyVersion, after: OntologyVersion,
    ) -> OntologyDiff:
        """对比两版本 → OntologyDiff（增/删/改）。

        修改判定：type_id 相同但其他字段不同（content hash）。
        """
        before_entities = {e.type_id: e for e in before.entity_types}
        after_entities = {e.type_id: e for e in after.entity_types}

        added_e = sorted(set(after_entities) - set(before_entities))
        removed_e = sorted(set(before_entities) - set(after_entities))
        modified_e = sorted(
            tid for tid in (set(before_entities) & set(after_entities))
            if before_entities[tid].model_dump() != after_entities[tid].model_dump()
        )

        before_relations = {r.type_id: r for r in before.relation_types}
        after_relations = {r.type_id: r for r in after.relation_types}

        added_r = sorted(set(after_relations) - set(before_relations))
        removed_r = sorted(set(before_relations) - set(after_relations))
        modified_r = sorted(
            tid for tid in (set(before_relations) & set(after_relations))
            if before_relations[tid].model_dump() != after_relations[tid].model_dump()
        )

        return OntologyDiff(
            from_version=before.version,
            to_version=after.version,
            added_entity_types=added_e,
            removed_entity_types=removed_e,
            modified_entity_types=modified_e,
            added_relation_types=added_r,
            removed_relation_types=removed_r,
            modified_relation_types=modified_r,
        )


# ════════════════════════════════════════════════════════════════════════
#  全局单例
# ════════════════════════════════════════════════════════════════════════


_global_store: OntologyStore | None = None


def get_ontology_store() -> OntologyStore:
    global _global_store
    if _global_store is None:
        _global_store = OntologyStore()
    return _global_store


def reset_store_for_test() -> None:
    global _global_store
    _global_store = None
