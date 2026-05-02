"""L2 本体迁移工具（M20 #2）。

支持客户共建 L2 本体的跨项目 / 跨环境迁移。

场景：
1. 项目 A 已稳定运行的 L2 本体 → 项目 B 复用（同企业新部门）
2. PoC 环境 → 生产环境的本体导出 / 导入
3. SME 离线编辑 L2（导出 → 改 YAML → 导入）

格式：
- JSON（默认；机器友好）
- YAML（人友好；支持注释；导入时可保留客户备注）

冲突策略：
- ``rename``  — 目标 project_id 已有同 type_id 时，importid 后缀加 _imported
- ``skip``    — 已存在则跳过该 type
- ``overwrite`` — 已存在则覆盖（强制；生产慎用）
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from packages.common import get_logger
from packages.common.types import (
    OntologyEntityType, OntologyLayer, OntologyRelationType, OntologyVersion,
)
from packages.ontology.store import OntologyStore

log = get_logger("ontology.migration")


ConflictStrategy = Literal["rename", "skip", "overwrite"]
ExportFormat = Literal["json", "yaml"]


class OntologyExportBundle(BaseModel):
    """单个 L2 项目的完整导出（多版本）。"""
    schema_version: str = "1.0"
    exported_at: datetime
    layer: OntologyLayer = "L2"
    source_project_id: str
    versions: list[OntologyVersion]


class ImportReport(BaseModel):
    """导入操作汇报。"""
    target_project_id: str
    imported_versions: int = 0
    skipped_versions: int = 0
    renamed_types: list[str] = []
    overwritten_types: list[str] = []
    new_version: str = ""               # 导入后产生的新版本号（target 视角）
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
#  导出
# ════════════════════════════════════════════════════════════════════════


def export_l2_ontology(
    project_id: str,
    *,
    store: OntologyStore | None = None,
    include_history: bool = True,
) -> OntologyExportBundle:
    """打包某 project 的 L2 本体（含/不含历史版本）。"""
    store = store or OntologyStore()
    if include_history:
        versions = store.list_versions("L2", project_id=project_id)
    else:
        cur = store.current_version("L2", project_id=project_id)
        versions = [cur] if cur else []

    if not versions:
        log.warning("ontology_export_no_versions", project_id=project_id)

    return OntologyExportBundle(
        exported_at=datetime.now(tz=None),
        source_project_id=project_id,
        versions=versions,
    )


def serialize_bundle(
    bundle: OntologyExportBundle, fmt: ExportFormat = "json",
) -> str:
    """打包为 JSON / YAML 文本。"""
    data = bundle.model_dump(mode="json")
    if fmt == "json":
        return json.dumps(data, ensure_ascii=False, indent=2)
    if fmt == "yaml":
        try:
            import yaml
        except ImportError as e:
            raise RuntimeError(
                "YAML 导出需要 pyyaml；pip install pyyaml 或改用 json",
            ) from e
        return yaml.safe_dump(
            data, allow_unicode=True, sort_keys=False, indent=2,
        )
    raise ValueError(f"不支持的格式: {fmt}")


def export_to_file(
    project_id: str, output_path: str | Path,
    *,
    store: OntologyStore | None = None,
    fmt: ExportFormat | None = None,
    include_history: bool = True,
) -> Path:
    output_path = Path(output_path)
    if fmt is None:
        fmt = "yaml" if output_path.suffix.lower() in (".yaml", ".yml") else "json"
    bundle = export_l2_ontology(
        project_id, store=store, include_history=include_history,
    )
    text = serialize_bundle(bundle, fmt=fmt)
    output_path.write_text(text, encoding="utf-8")
    log.info("ontology_export_done",
             project_id=project_id, output=str(output_path),
             versions=len(bundle.versions))
    return output_path


# ════════════════════════════════════════════════════════════════════════
#  导入
# ════════════════════════════════════════════════════════════════════════


def deserialize_bundle(text: str, fmt: ExportFormat | None = None) -> OntologyExportBundle:
    """从 JSON / YAML 文本反序列化（自动嗅探格式）。"""
    fmt = fmt or _sniff_format(text)
    if fmt == "json":
        data = json.loads(text)
    elif fmt == "yaml":
        try:
            import yaml
        except ImportError as e:
            raise RuntimeError("YAML 解析需要 pyyaml") from e
        data = yaml.safe_load(text)
    else:
        raise ValueError(f"不支持的格式: {fmt}")
    return OntologyExportBundle.model_validate(data)


def _sniff_format(text: str) -> ExportFormat:
    """简易格式嗅探。"""
    s = text.strip()
    if s.startswith("{") or s.startswith("["):
        return "json"
    return "yaml"


def import_l2_ontology(
    bundle: OntologyExportBundle,
    target_project_id: str,
    *,
    store: OntologyStore | None = None,
    on_conflict: ConflictStrategy = "rename",
    created_by: str = "ontology_migration",
    notes: str = "",
) -> ImportReport:
    """把 bundle 导入到 target_project_id（L2 only）。

    流程：
    1. 取目标项目当前 L2（若无则起空版本）
    2. 对每个待导入 type 检查冲突：
       - rename：换 type_id 加 _imported 后缀
       - skip：跳过（不引入）
       - overwrite：覆盖（保留 type_id，替换其他字段）
    3. 合并实体 / 关系类型，bump minor 版本号写回
    4. 返回 ImportReport
    """
    store = store or OntologyStore()
    if bundle.layer != "L2":
        raise ValueError("仅支持 L2 导入；L1 由平台维护")

    if not bundle.versions:
        return ImportReport(
            target_project_id=target_project_id,
            notes="bundle 为空（无版本可导入）",
        )

    # 用 bundle 中最新版本作为待导入内容（不递归导入历史；history 仅供审计）
    src_latest = bundle.versions[-1]

    cur = store.current_version("L2", project_id=target_project_id)
    if cur is None:
        # 目标项目尚无 L2，直接以新版本起步
        new_version = OntologyVersion(
            version="ont-v1.0.0",
            layer="L2",
            project_id=target_project_id,
            entity_types=[
                e.model_copy() for e in src_latest.entity_types
            ],
            relation_types=[
                r.model_copy() for r in src_latest.relation_types
            ],
            created_by=created_by,
            notes=(notes or f"imported from {bundle.source_project_id}"),
        )
        store.save_version(new_version)
        return ImportReport(
            target_project_id=target_project_id,
            imported_versions=1,
            new_version=new_version.version,
            notes="目标项目无既有 L2；以新版本起步",
        )

    existing_eids = cur.entity_type_ids()
    existing_rids = cur.relation_type_ids()

    next_ver = store.create_next_version(
        "L2",
        project_id=target_project_id,
        bump="minor",
        created_by=created_by,
        notes=(notes or f"imported from {bundle.source_project_id}"),
    )

    # 合并 entity_types
    renamed: list[str] = []
    overwritten: list[str] = []
    skipped = 0

    for et in src_latest.entity_types:
        if et.type_id in existing_eids:
            if on_conflict == "skip":
                skipped += 1
                continue
            if on_conflict == "rename":
                new_id = f"{et.type_id}_imported"
                cloned = et.model_copy(update={"type_id": new_id})
                next_ver.entity_types.append(cloned)
                renamed.append(f"E:{et.type_id}→{new_id}")
            elif on_conflict == "overwrite":
                # 找到原位置替换
                for i, ee in enumerate(next_ver.entity_types):
                    if ee.type_id == et.type_id:
                        next_ver.entity_types[i] = et.model_copy()
                        overwritten.append(f"E:{et.type_id}")
                        break
        else:
            next_ver.entity_types.append(et.model_copy())

    # 合并 relation_types
    for rt in src_latest.relation_types:
        if rt.type_id in existing_rids:
            if on_conflict == "skip":
                skipped += 1
                continue
            if on_conflict == "rename":
                new_id = f"{rt.type_id}_imported"
                cloned = rt.model_copy(update={"type_id": new_id})
                next_ver.relation_types.append(cloned)
                renamed.append(f"R:{rt.type_id}→{new_id}")
            elif on_conflict == "overwrite":
                for i, rr in enumerate(next_ver.relation_types):
                    if rr.type_id == rt.type_id:
                        next_ver.relation_types[i] = rt.model_copy()
                        overwritten.append(f"R:{rt.type_id}")
                        break
        else:
            next_ver.relation_types.append(rt.model_copy())

    store.save_version(next_ver)
    log.info(
        "ontology_import_done",
        target=target_project_id, source=bundle.source_project_id,
        new_version=next_ver.version, conflict_strategy=on_conflict,
        renamed=len(renamed), overwritten=len(overwritten), skipped=skipped,
    )

    return ImportReport(
        target_project_id=target_project_id,
        imported_versions=1,
        skipped_versions=skipped,
        renamed_types=renamed,
        overwritten_types=overwritten,
        new_version=next_ver.version,
        notes=f"merged from {bundle.source_project_id} via {on_conflict}",
    )


def import_from_file(
    file_path: str | Path, target_project_id: str,
    *,
    store: OntologyStore | None = None,
    on_conflict: ConflictStrategy = "rename",
) -> ImportReport:
    file_path = Path(file_path)
    text = file_path.read_text(encoding="utf-8")
    bundle = deserialize_bundle(text)
    return import_l2_ontology(
        bundle, target_project_id,
        store=store, on_conflict=on_conflict,
        notes=f"imported from {file_path.name}",
    )
