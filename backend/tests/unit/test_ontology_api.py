"""M3 #1 双层本体 · 批 4 · API endpoints + 矩阵审核台联动单测。"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from api.routers.ontology import (
    _proposal_store,
    reset_proposal_store_for_test,
    router,
)
from packages.common.auth import UserContext
from packages.common.types import (
    OntologyEntityType,
    OntologyEvolutionProposal,
    OntologyVersion,
)
from packages.ontology import (
    register_l2,
    reset_registry_for_test,
    reset_store_for_test,
)


class _UserInjectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        roles_header = request.headers.get("X-Test-Roles", "")
        roles = [r.strip() for r in roles_header.split(",") if r.strip()]
        request.state.user = UserContext(user_id="test-user", roles=roles)
        return await call_next(request)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.add_middleware(_UserInjectMiddleware)
    return app


@pytest.fixture(autouse=True)
def _reset():
    reset_registry_for_test()
    reset_store_for_test()
    reset_proposal_store_for_test()
    yield
    reset_registry_for_test()
    reset_store_for_test()
    reset_proposal_store_for_test()


@pytest.fixture
def client():
    return TestClient(_build_app())


# ════════════════════════════════════════════════════════════════════════
#  GET /ontology/{layer}
# ════════════════════════════════════════════════════════════════════════


class TestGetCurrentOntology:
    def test_l1_manufacturing_returns_builtin(self, client) -> None:
        r = client.get(
            "/api/v1/ontology/L1?industry_code=manufacturing",
            headers={"X-Test-Roles": "READER"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["industry_code"] == "manufacturing"
        # 9 个核心实体类型
        type_ids = {e["type_id"] for e in body["entity_types"]}
        assert "product" in type_ids and "process" in type_ids

    def test_l2_returns_404_when_empty(self, client) -> None:
        r = client.get(
            "/api/v1/ontology/L2?project_id=p1",
            headers={"X-Test-Roles": "READER"},
        )
        assert r.status_code == 404

    def test_l1_missing_industry_returns_400(self, client) -> None:
        r = client.get(
            "/api/v1/ontology/L1",
            headers={"X-Test-Roles": "READER"},
        )
        assert r.status_code == 400


# ════════════════════════════════════════════════════════════════════════
#  POST /proposals/scan + 联动 4×6 矩阵
# ════════════════════════════════════════════════════════════════════════


class TestScanEndpoint:
    def test_below_threshold_no_proposal(self, client) -> None:
        r = client.post(
            "/api/v1/ontology/proposals/scan",
            json={
                "industry_code": "manufacturing",
                "project_id": "p1",
                "candidate_entity_names": ["a", "b"],
                "threshold": 50,
            },
            headers={"X-Test-Roles": "SME"},
        )
        assert r.status_code == 200
        assert r.json()["triggered"] is False

    def test_scan_creates_proposal(self, client) -> None:
        candidates = [f"new_{i}" for i in range(60)]

        async def fake_llm(system, user):
            return {
                "type_id": "control_loop",
                "type_name": "控制回路",
                "description": "PID 闭环控制",
                "examples": ["a", "b", "c"],
                "confidence": 0.85,
            }

        with patch(
            "packages.ontology.evolution_proposer.acall_llm_json",
            side_effect=fake_llm,
        ):
            r = client.post(
                "/api/v1/ontology/proposals/scan",
                json={
                    "industry_code": "manufacturing",
                    "project_id": "p1",
                    "candidate_entity_names": candidates,
                    "threshold": 50,
                },
                headers={"X-Test-Roles": "SME"},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["triggered"] is True
        assert body["proposal_created"] is True
        assert body["proposal_id"].startswith("onto_")

    def test_scan_requires_sme(self, client) -> None:
        r = client.post(
            "/api/v1/ontology/proposals/scan",
            json={"industry_code": "manufacturing", "project_id": "p1",
                  "candidate_entity_names": []},
            headers={"X-Test-Roles": "READER"},
        )
        assert r.status_code == 403


# ════════════════════════════════════════════════════════════════════════
#  GET /proposals
# ════════════════════════════════════════════════════════════════════════


class TestListProposals:
    def test_list_filters_by_project(self, client) -> None:
        # 注入两条提议
        p1 = OntologyEvolutionProposal(
            proposal_id="p_1", project_id="A", layer="L2",
            proposed_entity_type=OntologyEntityType(type_id="x", type_name="X"),
        )
        p2 = OntologyEvolutionProposal(
            proposal_id="p_2", project_id="B", layer="L2",
            proposed_entity_type=OntologyEntityType(type_id="y", type_name="Y"),
        )
        _proposal_store["p_1"] = p1
        _proposal_store["p_2"] = p2

        r = client.get(
            "/api/v1/ontology/proposals?project_id=A",
            headers={"X-Test-Roles": "SME"},
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["proposal_id"] == "p_1"


# ════════════════════════════════════════════════════════════════════════
#  POST /proposals/{id}/approve
# ════════════════════════════════════════════════════════════════════════


class TestApproveProposal:
    def test_approve_creates_new_l2_version(self, client) -> None:
        p = OntologyEvolutionProposal(
            proposal_id="p_a", project_id="proj1", layer="L2",
            proposed_entity_type=OntologyEntityType(
                type_id="control_loop", type_name="控制回路", layer="L2",
            ),
        )
        _proposal_store["p_a"] = p

        r = client.post(
            "/api/v1/ontology/proposals/p_a/approve",
            json={"reason": "合理"},
            headers={"X-Test-Roles": "SME"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "approved"
        assert body["new_version"].startswith("ont-v")

        # 验证 L2 版本含新实体类型
        from packages.ontology import get_current_l2
        l2 = get_current_l2("proj1")
        assert l2 is not None
        assert "control_loop" in l2.entity_type_ids()

    def test_approve_unknown_returns_404(self, client) -> None:
        r = client.post(
            "/api/v1/ontology/proposals/ghost/approve",
            json={},
            headers={"X-Test-Roles": "SME"},
        )
        assert r.status_code == 404

    def test_double_approve_blocked(self, client) -> None:
        p = OntologyEvolutionProposal(
            proposal_id="p_b", project_id="p1", layer="L2",
            proposed_entity_type=OntologyEntityType(type_id="x", type_name="X"),
            status="approved",
        )
        _proposal_store["p_b"] = p

        r = client.post(
            "/api/v1/ontology/proposals/p_b/approve",
            json={},
            headers={"X-Test-Roles": "SME"},
        )
        assert r.status_code == 400


class TestRejectProposal:
    def test_reject_marks_status(self, client) -> None:
        p = OntologyEvolutionProposal(
            proposal_id="p_r", project_id="p1", layer="L2",
            proposed_entity_type=OntologyEntityType(type_id="x", type_name="X"),
        )
        _proposal_store["p_r"] = p

        r = client.post(
            "/api/v1/ontology/proposals/p_r/reject",
            json={"reason": "粒度过粗"},
            headers={"X-Test-Roles": "SME"},
        )
        assert r.status_code == 200
        assert _proposal_store["p_r"].status == "rejected"
        assert "粒度过粗" in _proposal_store["p_r"].reasoning


class TestVersionsListing:
    def test_list_l1_versions(self, client) -> None:
        r = client.get(
            "/api/v1/ontology/versions/list?layer=L1&industry_code=manufacturing",
            headers={"X-Test-Roles": "READER"},
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body) >= 1


class TestDiffEndpoint:
    def test_diff_two_l2_versions(self, client) -> None:
        v1 = OntologyVersion(
            version="ont-v1.0.0", layer="L2", project_id="p1",
            entity_types=[OntologyEntityType(type_id="a", type_name="A")],
        )
        v2 = OntologyVersion(
            version="ont-v1.0.1", layer="L2", project_id="p1",
            entity_types=[
                OntologyEntityType(type_id="a", type_name="A"),
                OntologyEntityType(type_id="b", type_name="B"),
            ],
        )
        register_l2(v1)
        register_l2(v2)

        r = client.get(
            "/api/v1/ontology/diff/compare?layer=L2&from=ont-v1.0.0&to=ont-v1.0.1&project_id=p1",
            headers={"X-Test-Roles": "READER"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "b" in body["added_entity_types"]
