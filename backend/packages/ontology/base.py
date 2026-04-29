"""OntologyRegistry — L1 + L2 本体版本注册表（M3 lite 内存模式）。

L1 按 industry_code 索引（manufacturing / energy），平台预置；
L2 按 project_id 索引，客户私有可演化。

每个 (layer, key) 对应一条版本链 → 当前生效 = 最新版本。
"""

from __future__ import annotations

from packages.common import get_logger
from packages.common.types import OntologyLayer, OntologyVersion

log = get_logger("ontology.base")


class OntologyRegistry:
    """全局本体注册表（M3 lite 内存模式；M4 接 PG）。"""

    def __init__(self) -> None:
        # L1: industry_code → list[OntologyVersion]（按 created_at 升序）
        self._l1: dict[str, list[OntologyVersion]] = {}
        # L2: project_id → list[OntologyVersion]
        self._l2: dict[str, list[OntologyVersion]] = {}

    # ── 注册 ──

    def register_l1(self, version: OntologyVersion) -> None:
        if version.layer != "L1":
            raise ValueError(f"L1 注册收到 layer={version.layer}")
        if not version.industry_code:
            raise ValueError("L1 OntologyVersion 必须填 industry_code")
        chain = self._l1.setdefault(version.industry_code, [])
        chain.append(version)
        log.info("ontology_l1_registered",
                 industry=version.industry_code, version=version.version)

    def register_l2(self, version: OntologyVersion) -> None:
        if version.layer != "L2":
            raise ValueError(f"L2 注册收到 layer={version.layer}")
        if not version.project_id:
            raise ValueError("L2 OntologyVersion 必须填 project_id")
        chain = self._l2.setdefault(version.project_id, [])
        chain.append(version)
        log.info("ontology_l2_registered",
                 project_id=version.project_id, version=version.version)

    # ── 查询 ──

    def get_current_l1(self, industry_code: str) -> OntologyVersion | None:
        chain = self._l1.get(industry_code, [])
        return chain[-1] if chain else None

    def get_current_l2(self, project_id: str) -> OntologyVersion | None:
        chain = self._l2.get(project_id, [])
        return chain[-1] if chain else None

    def list_l1_versions(self, industry_code: str) -> list[OntologyVersion]:
        return list(self._l1.get(industry_code, []))

    def list_l2_versions(self, project_id: str) -> list[OntologyVersion]:
        return list(self._l2.get(project_id, []))

    def get_version_by_id(
        self, layer: OntologyLayer, key: str, version: str
    ) -> OntologyVersion | None:
        chain = (self._l1 if layer == "L1" else self._l2).get(key, [])
        for v in chain:
            if v.version == version:
                return v
        return None


# ════════════════════════════════════════════════════════════════════════
#  全局单例 + 内置 L1 自动注册
# ════════════════════════════════════════════════════════════════════════

_global_registry: OntologyRegistry | None = None


def get_registry() -> OntologyRegistry:
    """懒加载单例 + 内置 L1 自动注册。"""
    global _global_registry
    if _global_registry is None:
        _global_registry = OntologyRegistry()
        _autoload_builtin_l1(_global_registry)
    return _global_registry


def _autoload_builtin_l1(registry: OntologyRegistry) -> None:
    """系统启动时自动注册内置 L1（制造 + 能源）。"""
    try:
        from packages.ontology.builtin.manufacturing_l1 import MANUFACTURING_L1_V1
        registry.register_l1(MANUFACTURING_L1_V1)
    except Exception as e:
        log.warning("autoload_manufacturing_l1_failed", error=str(e))
    try:
        from packages.ontology.builtin.energy_l1 import ENERGY_L1_V1
        registry.register_l1(ENERGY_L1_V1)
    except Exception as e:
        log.warning("autoload_energy_l1_failed", error=str(e))


def reset_registry_for_test() -> None:
    """测试用：清掉单例。"""
    global _global_registry
    _global_registry = None


# ── 便捷顶层函数 ──


def register_l1(version: OntologyVersion) -> None:
    get_registry().register_l1(version)


def register_l2(version: OntologyVersion) -> None:
    get_registry().register_l2(version)


def get_current_l1(industry_code: str) -> OntologyVersion | None:
    return get_registry().get_current_l1(industry_code)


def get_current_l2(project_id: str) -> OntologyVersion | None:
    return get_registry().get_current_l2(project_id)
