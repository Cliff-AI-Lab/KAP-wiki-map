"""M22 #7 · 增量重抽 lite 单测。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from packages.common.types import OntologyDiff
from packages.rebuild.incremental import (
    RebuildPlan,
    analyze_impact,
    collect_affected_types,
)


def _diff(
    added_e=None, removed_e=None, modified_e=None,
    added_r=None, removed_r=None, modified_r=None,
    from_v="v1.0", to_v="v1.1",
) -> OntologyDiff:
    return OntologyDiff(
        from_version=from_v, to_version=to_v,
        added_entity_types=added_e or [],
        removed_entity_types=removed_e or [],
        modified_entity_types=modified_e or [],
        added_relation_types=added_r or [],
        removed_relation_types=removed_r or [],
        modified_relation_types=modified_r or [],
    )


class TestCollectAffectedTypes:
    def test_merges_all_three_buckets(self):
        d = _diff(added_e=["A"], removed_e=["B"], modified_e=["C"])
        ents, rels = collect_affected_types(d)
        assert ents == {"A", "B", "C"}
        assert rels == set()


class TestAnalyzeImpactWithoutDocs:
    def test_no_docs_empty_plan(self):
        plan = analyze_impact(_diff(modified_e=["E1"]), {}, project_id="p1")
        assert plan.full_docs == []
        assert plan.partial_docs == []
        assert plan.skipped_docs == []
        assert plan.est_cost_units == 0


class TestAnalyzeImpactPartialOnly:
    def test_modify_existing_type_only_affects_owners(self):
        # diff: 修改 E_DEVICE; 文档 d1 用 E_DEVICE, d2 用 E_DOC, d3 用两个
        plan = analyze_impact(
            _diff(modified_e=["E_DEVICE"]),
            doc_to_types={
                "d1": {"E_DEVICE"},
                "d2": {"E_DOC"},
                "d3": {"E_DEVICE", "E_DOC"},
            },
            project_id="p1",
        )
        assert set(plan.partial_docs) == {"d1", "d3"}
        assert plan.skipped_docs == ["d2"]
        assert plan.full_docs == []
        # M22 #9: est_cost 不再 int(0.6)=0; round(0.6)=1, 或 partial//4=0 取较大
        # 2 个 partial → round(0.6)=1, partial//4=0 → max(0, 1) = 1
        assert plan.est_cost_units == 1
        assert plan.est_savings_ratio > 0.6

    def test_removed_type_same_logic(self):
        # 删除类型仍是 partial（删除类型的实体覆盖）
        plan = analyze_impact(
            _diff(removed_e=["E_OLD"]),
            doc_to_types={"d1": {"E_OLD"}, "d2": {"E_KEEP"}},
            project_id="p1",
        )
        assert plan.partial_docs == ["d1"]
        assert plan.skipped_docs == ["d2"]


class TestAnalyzeImpactNewType:
    def test_new_entity_type_forces_full_rebuild_per_doc(self):
        # 新增类型 → 旧文档可能漏抽, 全部走 full
        plan = analyze_impact(
            _diff(added_e=["E_NEW"]),
            doc_to_types={"d1": {"E_X"}, "d2": {"E_Y"}, "d3": set()},
            project_id="p1",
        )
        # 任何文档都需要全文重抽（哪怕原来无相关实体）
        assert set(plan.full_docs) == {"d1", "d2", "d3"}
        assert plan.partial_docs == []
        assert plan.skipped_docs == []
        assert plan.est_cost_units == 3
        assert plan.est_savings_ratio == 0.0


class TestAnalyzeImpactL1Changed:
    def test_l1_forces_full_regardless_of_diff(self):
        plan = analyze_impact(
            _diff(modified_e=["E_DEVICE"]),
            doc_to_types={"d1": {"E_X"}, "d2": {"E_Y"}},
            project_id="p1",
            l1_changed=True,
        )
        assert set(plan.full_docs) == {"d1", "d2"}
        assert plan.partial_docs == []
        assert plan.est_savings_ratio == 0.0


class TestRebuildPlanSerialization:
    def test_to_dict_contains_counts(self):
        plan = RebuildPlan(
            project_id="p1", from_version="v1", to_version="v2",
            full_docs=["a"], partial_docs=["b", "c"], skipped_docs=["d"],
            affected_type_ids={"E_X"},
            est_cost_units=2, est_savings_ratio=0.55,
        )
        d = plan.to_dict()
        assert d["full_count"] == 1
        assert d["partial_count"] == 2
        assert d["skipped_count"] == 1
        assert d["affected_type_ids"] == ["E_X"]
        assert d["est_savings_ratio"] == 0.55


# ────────── /rebuild/incremental 端点 ──────────


@pytest.fixture
def rebuild_app():
    from api.routers.rebuild import router
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


class TestAnalyzeImpactRelationDiff:
    """M22 #9 codex HIGH #4: relation diff 也参与影响面分析。"""

    def test_modified_relation_affects_only_docs_using_it(self):
        plan = analyze_impact(
            _diff(modified_r=["R_CONNECTED_TO"]),
            doc_to_types={"d1": {"E_X"}, "d2": {"E_Y"}, "d3": {"E_Z"}},
            doc_to_relations={
                "d1": {"R_CONNECTED_TO"},
                "d2": {"R_OTHER"},
                "d3": set(),
            },
            project_id="p1",
        )
        # 只有 d1 用了被改关系 → partial; d2/d3 skipped
        assert plan.partial_docs == ["d1"]
        assert set(plan.skipped_docs) == {"d2", "d3"}

    def test_entity_and_relation_diff_combined(self):
        plan = analyze_impact(
            _diff(modified_e=["E_DEVICE"], modified_r=["R_LINK"]),
            doc_to_types={"d1": {"E_DEVICE"}, "d2": {"E_X"}, "d3": {"E_Y"}},
            doc_to_relations={"d1": set(), "d2": {"R_LINK"}, "d3": set()},
            project_id="p1",
        )
        # d1 命中 entity, d2 命中 relation, d3 都不命中
        assert set(plan.partial_docs) == {"d1", "d2"}
        assert plan.skipped_docs == ["d3"]

    def test_no_doc_to_relations_defaults_to_entity_only(self):
        # 不传 doc_to_relations → 关系 diff 不参与（向后兼容）
        plan = analyze_impact(
            _diff(modified_r=["R_X"]),
            doc_to_types={"d1": {"E_A"}, "d2": {"E_B"}},
            project_id="p1",
        )
        # 没人命中 → 全 skipped
        assert plan.partial_docs == []
        assert set(plan.skipped_docs) == {"d1", "d2"}


class TestIncrementalRebuildAPI:
    def test_dry_run_returns_plan(self, rebuild_app):
        client = TestClient(rebuild_app)
        body = {
            "project_id": "p1",
            "version_from": "v1.0",
            "version_to": "v1.1",
            "dry_run": True,
            "doc_to_types_override": {
                "d1": ["E_DEVICE"],
                "d2": ["E_DOC"],
            },
        }
        r = client.post("/api/v1/rebuild/incremental", json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["dry_run"] is True
        plan = data["plan"]
        # 空 diff（无 added/removed/modified）→ 都 skipped
        assert plan["skipped_count"] == 2
        assert plan["full_count"] == 0
        assert plan["partial_count"] == 0

    def test_dry_run_false_returns_501(self, rebuild_app):
        """M22 #9 codex HIGH #5: 不再静默返回 200 误导调用方。"""
        client = TestClient(rebuild_app)
        body = {
            "project_id": "p1",
            "version_from": "v1.0",
            "version_to": "v1.1",
            "dry_run": False,
            "doc_to_types_override": {"d1": ["E_DEVICE"]},
        }
        r = client.post("/api/v1/rebuild/incremental", json=body)
        assert r.status_code == 501
        assert "M22" in r.text or "未实现" in r.text or "rebuild_orchestrator" in r.text

    def test_explicit_diff_fields_used(self, rebuild_app):
        """M22 #9 codex HIGH #5: caller 可直接传 diff 字段。"""
        client = TestClient(rebuild_app)
        body = {
            "project_id": "p1",
            "version_from": "v1.0",
            "version_to": "v1.1",
            "dry_run": True,
            "added_entity_types": ["E_NEW_TYPE"],
            "doc_to_types_override": {
                "d1": ["E_OLD"], "d2": ["E_OLD"],
            },
        }
        r = client.post("/api/v1/rebuild/incremental", json=body)
        assert r.status_code == 200
        plan = r.json()["plan"]
        # 有 added_entity_types → 全 full
        assert plan["full_count"] == 2
        assert plan["partial_count"] == 0
        assert plan["skipped_count"] == 0

    def test_doc_to_relations_passed_through(self, rebuild_app):
        """M22 #9: 关系 diff + doc_to_relations_override 推导影响面。"""
        client = TestClient(rebuild_app)
        body = {
            "project_id": "p1",
            "version_from": "v1.0", "version_to": "v1.1",
            "dry_run": True,
            "modified_relation_types": ["R_LINK"],
            "doc_to_types_override": {"d1": ["E_X"], "d2": ["E_X"]},
            "doc_to_relations_override": {"d1": ["R_LINK"], "d2": ["R_OTHER"]},
        }
        r = client.post("/api/v1/rebuild/incremental", json=body)
        assert r.status_code == 200
        plan = r.json()["plan"]
        assert plan["partial_count"] == 1  # d1 命中 R_LINK
        assert plan["skipped_count"] == 1  # d2

    def test_doc_to_types_override_size_limit(self, rebuild_app):
        """M22 #9 codex LOW: 超 10000 docs 返 413。"""
        client = TestClient(rebuild_app)
        big_dict = {f"d{i}": ["E_X"] for i in range(10001)}
        body = {
            "project_id": "p1",
            "version_from": "v1.0", "version_to": "v1.1",
            "dry_run": True,
            "doc_to_types_override": big_dict,
        }
        r = client.post("/api/v1/rebuild/incremental", json=body)
        assert r.status_code == 413

    def test_missing_override_returns_400(self, rebuild_app):
        client = TestClient(rebuild_app)
        body = {
            "project_id": "p1",
            "version_from": "v1.0",
            "version_to": "v1.1",
            "dry_run": True,
        }
        r = client.post("/api/v1/rebuild/incremental", json=body)
        assert r.status_code == 400
        assert "doc_to_types_override" in r.text
