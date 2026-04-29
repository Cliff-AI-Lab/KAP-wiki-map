"""M3 #5 · session/proposal store 持久化单测（内存模式）。

PG 模式需真实 DB 连接，单测覆盖到内存实现 + Pydantic 序列化即可。
集成测试在 PG 部署后单独跑。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from packages.architect.session_store import (
    InMemoryArchitectSessionStore,
)
from packages.common.types import (
    ArchitectSession,
    OntologyEntityType,
    OntologyEvolutionProposal,
    TaxonomyDraft,
)
from packages.ontology.proposal_store import (
    InMemoryOntologyProposalStore,
)


# ════════════════════════════════════════════════════════════════════════
#  ArchitectSessionStore — InMemory
# ════════════════════════════════════════════════════════════════════════


class TestInMemoryArchitectSessionStore:
    async def test_upsert_and_get(self) -> None:
        store = InMemoryArchitectSessionStore()
        await store.initialize()

        session = ArchitectSession(
            session_id="s1", project_id="p1", stage="propose",
            history=[{"role": "user", "content": "hi"}],
        )
        await store.upsert(session)

        retrieved = await store.get("s1")
        assert retrieved is not None
        assert retrieved.session_id == "s1"
        assert retrieved.project_id == "p1"
        assert retrieved.stage == "propose"

    async def test_upsert_overwrites(self) -> None:
        store = InMemoryArchitectSessionStore()
        await store.initialize()
        s1 = ArchitectSession(session_id="x", project_id="p", stage="identify")
        await store.upsert(s1)
        s2 = ArchitectSession(session_id="x", project_id="p", stage="export")
        await store.upsert(s2)

        retrieved = await store.get("x")
        assert retrieved.stage == "export"

    async def test_get_nonexistent_returns_none(self) -> None:
        store = InMemoryArchitectSessionStore()
        await store.initialize()
        assert await store.get("ghost") is None

    async def test_list_by_project(self) -> None:
        store = InMemoryArchitectSessionStore()
        await store.initialize()
        await store.upsert(ArchitectSession(session_id="a", project_id="P1"))
        await store.upsert(ArchitectSession(session_id="b", project_id="P1"))
        await store.upsert(ArchitectSession(session_id="c", project_id="P2"))

        result = await store.list_by_project("P1")
        assert len(result) == 2
        assert {s.session_id for s in result} == {"a", "b"}

    async def test_delete(self) -> None:
        store = InMemoryArchitectSessionStore()
        await store.initialize()
        await store.upsert(ArchitectSession(session_id="d", project_id="p"))
        assert await store.delete("d") is True
        assert await store.delete("d") is False  # 已删
        assert await store.get("d") is None

    async def test_session_with_full_draft(self) -> None:
        """带 draft 的 session 完整往返。"""
        store = InMemoryArchitectSessionStore()
        await store.initialize()
        draft = TaxonomyDraft(
            industry_code="manufacturing", industry_name="制造业",
            confidence=0.85, taxonomy=[],
        )
        session = ArchitectSession(
            session_id="full", project_id="p1", stage="refine", draft=draft,
        )
        await store.upsert(session)
        retrieved = await store.get("full")
        assert retrieved.draft is not None
        assert retrieved.draft.industry_code == "manufacturing"


# ════════════════════════════════════════════════════════════════════════
#  OntologyProposalStore — InMemory
# ════════════════════════════════════════════════════════════════════════


class TestInMemoryOntologyProposalStore:
    async def test_upsert_and_get(self) -> None:
        store = InMemoryOntologyProposalStore()
        await store.initialize()

        proposal = OntologyEvolutionProposal(
            proposal_id="onto_1", project_id="p1", layer="L2",
            proposed_entity_type=OntologyEntityType(
                type_id="control_loop", type_name="控制回路", layer="L2",
            ),
            evidence_count=80,
            reasoning="样本均涉及 PID 闭环",
        )
        await store.upsert(proposal)

        retrieved = await store.get("onto_1")
        assert retrieved is not None
        assert retrieved.proposed_entity_type.type_id == "control_loop"
        assert retrieved.evidence_count == 80

    async def test_status_filter(self) -> None:
        store = InMemoryOntologyProposalStore()
        await store.initialize()

        await store.upsert(OntologyEvolutionProposal(
            proposal_id="p_pending", project_id="proj1",
            status="pending",
            proposed_entity_type=OntologyEntityType(type_id="x", type_name="X"),
        ))
        await store.upsert(OntologyEvolutionProposal(
            proposal_id="p_approved", project_id="proj1",
            status="approved",
            proposed_entity_type=OntologyEntityType(type_id="y", type_name="Y"),
        ))

        pending = await store.list_by_project("proj1", status="pending")
        assert len(pending) == 1
        assert pending[0].proposal_id == "p_pending"

        all_p = await store.list_by_project("proj1")
        assert len(all_p) == 2

    async def test_list_sorted_by_created_at_desc(self) -> None:
        store = InMemoryOntologyProposalStore()
        await store.initialize()

        old = OntologyEvolutionProposal(
            proposal_id="old", project_id="p",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            proposed_entity_type=OntologyEntityType(type_id="a", type_name="A"),
        )
        new = OntologyEvolutionProposal(
            proposal_id="new", project_id="p",
            created_at=datetime(2026, 12, 1, tzinfo=timezone.utc),
            proposed_entity_type=OntologyEntityType(type_id="b", type_name="B"),
        )
        await store.upsert(old)
        await store.upsert(new)

        result = await store.list_by_project("p")
        assert result[0].proposal_id == "new"
        assert result[1].proposal_id == "old"

    async def test_project_isolation(self) -> None:
        store = InMemoryOntologyProposalStore()
        await store.initialize()
        await store.upsert(OntologyEvolutionProposal(
            proposal_id="a", project_id="X",
            proposed_entity_type=OntologyEntityType(type_id="a", type_name="A"),
        ))
        await store.upsert(OntologyEvolutionProposal(
            proposal_id="b", project_id="Y",
            proposed_entity_type=OntologyEntityType(type_id="b", type_name="B"),
        ))
        assert len(await store.list_by_project("X")) == 1
        assert len(await store.list_by_project("Z")) == 0

    async def test_get_nonexistent_returns_none(self) -> None:
        store = InMemoryOntologyProposalStore()
        await store.initialize()
        assert await store.get("ghost") is None
