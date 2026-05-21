"""M22 #5 · 实体消歧 + 关系抽取器 + governance merge decision 单测。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from packages.common.types import ExtractedEntity
from packages.extraction.entity_resolver import (
    MergeCandidate,
    _cosine,
    _normalized_edit_distance,
    find_merge_candidates,
)


# ────────── 字符串相似度 ──────────


class TestStringSimilarity:
    def test_identical_returns_one(self):
        assert _normalized_edit_distance("汽轮机1号", "汽轮机1号") == 1.0

    def test_completely_different(self):
        score = _normalized_edit_distance("汽轮机", "锅炉")
        assert 0 <= score < 0.5

    def test_close_variant(self):
        # "1#" vs "1号" 一个字符差
        score = _normalized_edit_distance("汽轮机1#", "汽轮机1号")
        assert score > 0.7

    def test_empty_handled(self):
        assert _normalized_edit_distance("", "") == 1.0
        assert _normalized_edit_distance("a", "") == 0.0


# ────────── 余弦相似度 ──────────


class TestCosine:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.5]
        assert abs(_cosine(v, v) - 1.0) < 1e-9

    def test_orthogonal(self):
        assert _cosine([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_mismatched_dims(self):
        assert _cosine([1.0, 0.0], [1.0]) == 0.0


# ────────── find_merge_candidates ──────────


def _entity(eid: str, name: str, type_id: str = "E_DEVICE") -> ExtractedEntity:
    return ExtractedEntity(
        entity_id=eid, name=name, type_id=type_id, confidence=0.8,
    )


class TestFindMergeCandidates:
    def test_string_threshold_matches_similar_pair(self):
        ents = [
            _entity("e1", "汽轮机1号"),
            _entity("e2", "汽轮机1#"),
            _entity("e3", "锅炉A"),
        ]
        cands = find_merge_candidates(ents, string_threshold=0.7)
        # e1/e2 应被识别, e3 与前者差太大
        assert len(cands) == 1
        c = cands[0]
        assert {c.entity_a_id, c.entity_b_id} == {"e1", "e2"}
        assert c.type_id == "E_DEVICE"
        assert c.string_similarity > 0.7

    def test_different_type_ids_never_merged(self):
        ents = [
            _entity("e1", "汽轮机1号", type_id="E_DEVICE"),
            _entity("e2", "汽轮机1号", type_id="E_DOCUMENT"),  # 同名但不同类型
        ]
        cands = find_merge_candidates(ents, string_threshold=0.5)
        assert cands == []

    def test_l1_type_excluded(self):
        ents = [
            _entity("e1", "汽轮机A", type_id="E_L1_DEVICE"),
            _entity("e2", "汽轮机B", type_id="E_L1_DEVICE"),
        ]
        cands = find_merge_candidates(
            ents, string_threshold=0.3,
            l1_type_ids={"E_L1_DEVICE"},
        )
        # L1 类型实体不参与合并候选
        assert cands == []

    def test_vector_path_promotes_visually_different_names(self):
        # 字符串相似度低但 embedding 近 → 仍应进候选
        ents = [
            _entity("e1", "高压机组 A"),
            _entity("e2", "1#turbo"),  # 完全不同名
        ]
        embeddings = {
            "e1": [1.0, 0.0, 0.0],
            "e2": [0.99, 0.05, 0.0],  # 近似平行
        }
        cands = find_merge_candidates(
            ents,
            embeddings=embeddings,
            string_threshold=0.99,    # 字符串路径不可能命中
            vector_threshold=0.9,
        )
        assert len(cands) == 1
        assert cands[0].vector_similarity is not None
        assert cands[0].vector_similarity > 0.9

    def test_results_sorted_by_score(self):
        ents = [
            _entity("e1", "A"), _entity("e2", "A"),   # 完全同名
            _entity("e3", "ABC"), _entity("e4", "ABD"),  # 一字符差
        ]
        cands = find_merge_candidates(ents, string_threshold=0.5)
        # 至少两个候选, score 降序
        assert len(cands) >= 2
        assert cands[0].score >= cands[-1].score


# ────────── governance /entity-merge-decision 端点 ──────────


@pytest.fixture
def governance_app(monkeypatch):
    """M22 #9: D12 闭环硬校验 — fixture 提供 store + 已认领的 SME 工单。"""
    import asyncio
    from datetime import datetime, timezone

    from packages.observability import decision_log as dl
    from packages.common.types import GovernanceQueueItem
    from packages.storage.governance_queue_store import GovernanceQueueStore
    from api.deps import get_governance_queue_store
    from api.routers.governance import router

    recorded: list[dict] = []

    async def _capture(event):
        recorded.append({
            "decision_type": event.decision_type,
            "target_id": event.target_id,
            "actor": event.actor,
            "project_id": event.project_id,
            "note": event.note,
        })

    dl.reset_decisions_for_test()
    dl.set_pg_sink(_capture)

    store = GovernanceQueueStore()
    asyncio.get_event_loop().run_until_complete(store.initialize())

    # 预置一个已认领的 SME 工单
    sme_item = GovernanceQueueItem(
        id="gq_sme_001", project_id="proj_a", agent="auditor",
        kind="unverified", title="合并候选: A vs B",
        priority=50, status="reviewing",
        created_at=datetime.now(timezone.utc),
        workstation="W6", assigned_role="SME",
        claimed_by="sme_001",
    )
    asyncio.get_event_loop().run_until_complete(store.upsert(sme_item))

    # 另一个未认领的工单 (测 L4)
    dg_item = GovernanceQueueItem(
        id="gq_dg_002", project_id="proj_a", agent="auditor",
        kind="unverified", title="合并候选: C vs D",
        priority=50, status="pending",
        created_at=datetime.now(timezone.utc),
        workstation="W4", assigned_role="DG",  # 错的角色, 测 L3
    )
    asyncio.get_event_loop().run_until_complete(store.upsert(dg_item))

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_governance_queue_store] = lambda: store

    yield app, recorded, store

    dl.reset_decisions_for_test()


class TestEntityMergeDecisionAPI:
    """M22 #9: D12 闭环硬校验 5 层 (L1-L5)。"""

    def _valid_body(self, **overrides) -> dict:
        body = {
            "project_id": "proj_a",
            "queue_item_id": "gq_sme_001",
            "entity_a_id": "ent_aaa",
            "entity_b_id": "ent_bbb",
            "entity_a_type_id": "E_DEVICE",
            "entity_b_type_id": "E_DEVICE",
            "decision": "approve",
            "actor": "sme_001",
            "note": "字符串高度相似 + 历史 doc 重叠",
        }
        body.update(overrides)
        return body

    def test_happy_path_approve(self, governance_app):
        app, recorded, store = governance_app
        client = TestClient(app)
        r = client.post("/api/v1/governance/entity-merge-decision",
                        json=self._valid_body())
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["decision_type"] == "entity_merge_approved"
        assert body["target_id"] == "ent_aaa::ent_bbb"
        assert body["actor"] == "sme_001"
        assert body["queue_item_id"] == "gq_sme_001"
        assert body["queue_resolved"] is True
        # 决策日志已写, 包含 queue/type 元信息
        assert len(recorded) == 1
        note = recorded[0]["note"]
        assert "queue=gq_sme_001" in note
        assert "type=E_DEVICE" in note

    def test_reject_decision(self, governance_app):
        app, recorded, _ = governance_app
        client = TestClient(app)
        r = client.post("/api/v1/governance/entity-merge-decision",
                        json=self._valid_body(decision="reject"))
        assert r.status_code == 200
        assert r.json()["decision_type"] == "entity_merge_rejected"
        assert recorded[0]["decision_type"] == "entity_merge_rejected"

    def test_L1_invalid_decision_returns_400(self, governance_app):
        app, *_ = governance_app
        client = TestClient(app)
        r = client.post("/api/v1/governance/entity-merge-decision",
                        json=self._valid_body(decision="maybe"))
        assert r.status_code == 400
        assert "decision" in r.text

    def test_L5_type_id_mismatch_returns_400(self, governance_app):
        app, *_ = governance_app
        client = TestClient(app)
        r = client.post("/api/v1/governance/entity-merge-decision",
                        json=self._valid_body(entity_b_type_id="E_DOCUMENT"))
        assert r.status_code == 400
        assert "type_id" in r.text

    def test_L2_unknown_queue_item_returns_404(self, governance_app):
        app, *_ = governance_app
        client = TestClient(app)
        r = client.post("/api/v1/governance/entity-merge-decision",
                        json=self._valid_body(queue_item_id="gq_does_not_exist"))
        assert r.status_code == 404

    def test_L2_project_mismatch_returns_400(self, governance_app):
        app, *_ = governance_app
        client = TestClient(app)
        r = client.post("/api/v1/governance/entity-merge-decision",
                        json=self._valid_body(project_id="proj_OTHER"))
        assert r.status_code == 400
        assert "project_id" in r.text

    def test_L3_non_SME_role_returns_403(self, governance_app):
        app, *_ = governance_app
        client = TestClient(app)
        # 用 DG 角色的工单
        r = client.post("/api/v1/governance/entity-merge-decision",
                        json=self._valid_body(queue_item_id="gq_dg_002"))
        assert r.status_code == 403
        assert "SME" in r.text

    def test_L4_actor_mismatch_returns_403(self, governance_app):
        app, *_ = governance_app
        client = TestClient(app)
        # actor 不等于 claimed_by=sme_001
        r = client.post("/api/v1/governance/entity-merge-decision",
                        json=self._valid_body(actor="sme_002"))
        assert r.status_code == 403
        assert "认领人" in r.text or "claimed" in r.text.lower()

    def test_decision_logged_with_queue_metadata(self, governance_app):
        app, recorded, store = governance_app
        client = TestClient(app)
        r = client.post("/api/v1/governance/entity-merge-decision",
                        json=self._valid_body())
        assert r.status_code == 200
        # 决策日志含 queue_item_id + type_id 元信息（防绕过合并约束）
        assert "queue=gq_sme_001" in recorded[0]["note"]
        assert "type=E_DEVICE" in recorded[0]["note"]
