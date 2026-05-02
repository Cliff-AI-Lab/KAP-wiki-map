"""M20 #2 · L2 本体迁移工具单测（export / import / 冲突策略 / 文件 IO）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.common.types import (
    OntologyEntityType, OntologyRelationType, OntologyVersion,
)
from packages.ontology import (
    OntologyExportBundle, OntologyStore,
    deserialize_bundle, export_l2_ontology, export_to_file,
    import_from_file, import_l2_ontology,
    reset_store_for_test, reset_registry_for_test, serialize_bundle,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_store_for_test()
    reset_registry_for_test()
    yield
    reset_store_for_test()
    reset_registry_for_test()


def _make_l2(project_id: str, version: str, entities: list[str], relations: list[str]) -> OntologyVersion:
    return OntologyVersion(
        version=version, layer="L2", project_id=project_id,
        entity_types=[
            OntologyEntityType(type_id=eid, type_name=eid.upper(),
                               description=f"{eid} desc")
            for eid in entities
        ],
        relation_types=[
            OntologyRelationType(type_id=rid, type_name=rid.upper(),
                                  description=f"{rid} desc",
                                  source_types=[], target_types=[])
            for rid in relations
        ],
        created_by="sme1",
    )


class TestExport:
    def test_export_with_history(self) -> None:
        store = OntologyStore()
        store.save_version(_make_l2("p1", "ont-v1.0.0", ["device"], ["controls"]))
        store.save_version(_make_l2("p1", "ont-v1.1.0", ["device", "operator"], ["controls"]))

        bundle = export_l2_ontology("p1", store=store)
        assert bundle.source_project_id == "p1"
        assert bundle.layer == "L2"
        assert len(bundle.versions) == 2
        assert bundle.versions[-1].version == "ont-v1.1.0"

    def test_export_current_only(self) -> None:
        store = OntologyStore()
        store.save_version(_make_l2("p1", "ont-v1.0.0", ["device"], []))
        store.save_version(_make_l2("p1", "ont-v1.1.0", ["device", "op"], []))

        bundle = export_l2_ontology("p1", store=store, include_history=False)
        assert len(bundle.versions) == 1
        assert bundle.versions[0].version == "ont-v1.1.0"

    def test_export_empty_project(self) -> None:
        bundle = export_l2_ontology("p_unknown", store=OntologyStore())
        assert bundle.versions == []
        assert bundle.source_project_id == "p_unknown"


class TestSerialize:
    def test_json_round_trip(self) -> None:
        store = OntologyStore()
        store.save_version(_make_l2("p1", "ont-v1.0.0", ["device"], ["controls"]))
        bundle = export_l2_ontology("p1", store=store)

        text = serialize_bundle(bundle, fmt="json")
        # 是合法 JSON
        data = json.loads(text)
        assert data["source_project_id"] == "p1"

        roundtrip = deserialize_bundle(text)
        assert roundtrip.source_project_id == "p1"
        assert roundtrip.versions[0].version == "ont-v1.0.0"
        assert len(roundtrip.versions[0].entity_types) == 1

    def test_sniff_format_detects_json(self) -> None:
        text = '{"schema_version":"1.0","exported_at":"2026-05-02T00:00:00",' \
               '"layer":"L2","source_project_id":"p1","versions":[]}'
        bundle = deserialize_bundle(text)
        assert bundle.source_project_id == "p1"


class TestFileIO:
    def test_export_to_file_json(self, tmp_path: Path) -> None:
        store = OntologyStore()
        store.save_version(_make_l2("p1", "ont-v1.0.0", ["device"], []))

        out = tmp_path / "ont.json"
        export_to_file("p1", out, store=store)
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["source_project_id"] == "p1"

    def test_export_format_inferred_from_extension(
        self, tmp_path: Path,
    ) -> None:
        store = OntologyStore()
        store.save_version(_make_l2("p1", "ont-v1.0.0", ["device"], []))

        out_yaml = tmp_path / "ont.yaml"
        try:
            export_to_file("p1", out_yaml, store=store)
        except RuntimeError as e:
            if "pyyaml" in str(e):
                pytest.skip("pyyaml 未安装")
            raise
        text = out_yaml.read_text(encoding="utf-8")
        # YAML 应该不是 JSON 起始
        assert not text.lstrip().startswith("{")


class TestImport:
    def test_import_to_empty_target(self) -> None:
        src_store = OntologyStore()
        src_store.save_version(
            _make_l2("p_src", "ont-v1.0.0", ["device", "op"], ["controls"]),
        )
        bundle = export_l2_ontology("p_src", store=src_store)

        # 共享 registry：reset 后 src + tgt 都在同 store
        report = import_l2_ontology(
            bundle, target_project_id="p_tgt", store=src_store,
        )
        assert report.imported_versions == 1
        assert report.new_version == "ont-v1.0.0"
        assert report.target_project_id == "p_tgt"

        cur = src_store.current_version("L2", project_id="p_tgt")
        assert cur is not None
        assert cur.entity_type_ids() == {"device", "op"}

    def test_import_renames_on_conflict(self) -> None:
        store = OntologyStore()
        # 目标已有 device
        store.save_version(_make_l2("p_tgt", "ont-v1.0.0", ["device"], []))

        # 源也有 device + 新增 motor
        src = _make_l2("p_src", "ont-v1.0.0", ["device", "motor"], [])
        bundle = OntologyExportBundle(
            exported_at=src.created_at, source_project_id="p_src",
            versions=[src],
        )
        report = import_l2_ontology(
            bundle, "p_tgt", store=store, on_conflict="rename",
        )
        assert "E:device→device_imported" in report.renamed_types
        cur = store.current_version("L2", project_id="p_tgt")
        eids = cur.entity_type_ids()
        assert "device" in eids                   # 原来的留
        assert "device_imported" in eids         # 重命名后
        assert "motor" in eids                    # 新增

    def test_import_skips_on_conflict(self) -> None:
        store = OntologyStore()
        store.save_version(_make_l2("p_tgt", "ont-v1.0.0", ["device"], []))

        src = _make_l2("p_src", "ont-v1.0.0", ["device", "motor"], [])
        bundle = OntologyExportBundle(
            exported_at=src.created_at, source_project_id="p_src",
            versions=[src],
        )
        report = import_l2_ontology(
            bundle, "p_tgt", store=store, on_conflict="skip",
        )
        assert report.skipped_versions == 1   # device 跳过
        cur = store.current_version("L2", project_id="p_tgt")
        assert cur.entity_type_ids() == {"device", "motor"}
        # device 没有 _imported 后缀
        assert "device_imported" not in cur.entity_type_ids()

    def test_import_overwrites_on_conflict(self) -> None:
        store = OntologyStore()
        # 目标 device 描述短
        store.save_version(_make_l2("p_tgt", "ont-v1.0.0", ["device"], []))
        cur_before = store.current_version("L2", project_id="p_tgt")
        old_desc = cur_before.entity_types[0].description

        # 源 device 描述加长
        src = _make_l2("p_src", "ont-v1.0.0", ["device"], [])
        src.entity_types[0].description = "richer source description"

        bundle = OntologyExportBundle(
            exported_at=src.created_at, source_project_id="p_src",
            versions=[src],
        )
        report = import_l2_ontology(
            bundle, "p_tgt", store=store, on_conflict="overwrite",
        )
        assert "E:device" in report.overwritten_types
        cur = store.current_version("L2", project_id="p_tgt")
        # 新版本 description 来自源
        device_after = next(e for e in cur.entity_types if e.type_id == "device")
        assert device_after.description == "richer source description"
        assert device_after.description != old_desc

    def test_import_empty_bundle_returns_empty_report(self) -> None:
        bundle = OntologyExportBundle(
            exported_at=__import__("datetime").datetime.now(),
            source_project_id="p_src", versions=[],
        )
        report = import_l2_ontology(bundle, "p_tgt", store=OntologyStore())
        assert report.imported_versions == 0
        assert "空" in report.notes

    def test_import_l1_rejected(self) -> None:
        bundle = OntologyExportBundle(
            exported_at=__import__("datetime").datetime.now(),
            source_project_id="", layer="L1", versions=[],
        )
        with pytest.raises(ValueError, match="仅支持 L2"):
            import_l2_ontology(bundle, "p_tgt", store=OntologyStore())


class TestImportFromFile:
    def test_round_trip_via_file(self, tmp_path: Path) -> None:
        store = OntologyStore()
        store.save_version(
            _make_l2("p_src", "ont-v1.0.0", ["device", "motor"], ["controls"]),
        )
        out = tmp_path / "ont.json"
        export_to_file("p_src", out, store=store)

        report = import_from_file(out, "p_tgt2", store=store)
        assert report.imported_versions == 1
        cur = store.current_version("L2", project_id="p_tgt2")
        assert cur is not None
        assert cur.entity_type_ids() == {"device", "motor"}
        assert cur.relation_type_ids() == {"controls"}
