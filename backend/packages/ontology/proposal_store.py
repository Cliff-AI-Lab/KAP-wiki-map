"""OntologyEvolutionProposal PG 持久化（M3 #5）。

M3 #1 ontology router 用内存 dict；本批加 PG 实现 + 内存 fallback。
"""

from __future__ import annotations

from typing import Protocol

from packages.common import get_logger
from packages.common.types import OntologyEvolutionProposal

log = get_logger("ontology.proposal_store")


class OntologyProposalStore(Protocol):
    async def initialize(self) -> None: ...
    async def upsert(self, proposal: OntologyEvolutionProposal) -> None: ...
    async def get(self, proposal_id: str) -> OntologyEvolutionProposal | None: ...
    async def list_by_project(
        self, project_id: str, status: str | None = None,
    ) -> list[OntologyEvolutionProposal]: ...


class InMemoryOntologyProposalStore:
    def __init__(self) -> None:
        self._data: dict[str, OntologyEvolutionProposal] = {}

    async def initialize(self) -> None:
        log.info("ontology_proposal_store_memory_mode")

    async def upsert(self, proposal: OntologyEvolutionProposal) -> None:
        self._data[proposal.proposal_id] = proposal

    async def get(self, proposal_id: str) -> OntologyEvolutionProposal | None:
        return self._data.get(proposal_id)

    async def list_by_project(
        self, project_id: str, status: str | None = None,
    ) -> list[OntologyEvolutionProposal]:
        out = [p for p in self._data.values() if p.project_id == project_id]
        if status:
            out = [p for p in out if p.status == status]
        return sorted(out, key=lambda p: p.created_at, reverse=True)


class PgOntologyProposalStore:
    """PG 持久化 OntologyEvolutionProposal。"""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn = None

    async def initialize(self) -> None:
        import psycopg
        try:
            self._conn = await psycopg.AsyncConnection.connect(self._dsn)
        except Exception as e:
            raise RuntimeError(f"PG connect failed: {e}") from e

        async with self._conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS ontology_proposals (
                    proposal_id        VARCHAR(64) PRIMARY KEY,
                    project_id         VARCHAR(64) NOT NULL,
                    layer              VARCHAR(4) NOT NULL DEFAULT 'L2',
                    proposed_entity    JSONB,
                    proposed_relation  JSONB,
                    evidence_count     INT NOT NULL DEFAULT 0,
                    sample_entities    JSONB DEFAULT '[]'::jsonb,
                    reasoning          TEXT,
                    status             VARCHAR(16) NOT NULL DEFAULT 'pending',
                    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    resolver           VARCHAR(64) DEFAULT '',
                    resolved_at        TIMESTAMPTZ
                )
            """)
            await cur.execute(
                "CREATE INDEX IF NOT EXISTS ontology_proposals_project_idx "
                "ON ontology_proposals(project_id, status)"
            )
            await self._conn.commit()
        log.info("ontology_proposal_store_pg_connected")

    async def upsert(self, proposal: OntologyEvolutionProposal) -> None:
        assert self._conn is not None
        import json as _json
        et = (
            _json.dumps(proposal.proposed_entity_type.model_dump(),
                        ensure_ascii=False, default=str)
            if proposal.proposed_entity_type else None
        )
        rt = (
            _json.dumps(proposal.proposed_relation_type.model_dump(),
                        ensure_ascii=False, default=str)
            if proposal.proposed_relation_type else None
        )
        samples = _json.dumps(proposal.sample_entities, ensure_ascii=False)

        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO ontology_proposals
                  (proposal_id, project_id, layer, proposed_entity, proposed_relation,
                   evidence_count, sample_entities, reasoning, status,
                   created_at, resolver, resolved_at)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb,
                        %s, %s::jsonb, %s, %s, %s, %s, %s)
                ON CONFLICT (proposal_id) DO UPDATE SET
                    layer = EXCLUDED.layer,
                    proposed_entity = EXCLUDED.proposed_entity,
                    proposed_relation = EXCLUDED.proposed_relation,
                    evidence_count = EXCLUDED.evidence_count,
                    sample_entities = EXCLUDED.sample_entities,
                    reasoning = EXCLUDED.reasoning,
                    status = EXCLUDED.status,
                    resolver = EXCLUDED.resolver,
                    resolved_at = EXCLUDED.resolved_at
                """,
                (
                    proposal.proposal_id, proposal.project_id, proposal.layer,
                    et, rt, proposal.evidence_count, samples,
                    proposal.reasoning, proposal.status,
                    proposal.created_at, proposal.resolver, proposal.resolved_at,
                ),
            )
            await self._conn.commit()

    async def get(self, proposal_id: str) -> OntologyEvolutionProposal | None:
        assert self._conn is not None
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT proposal_id, project_id, layer, proposed_entity, "
                "proposed_relation, evidence_count, sample_entities, "
                "reasoning, status, created_at, resolver, resolved_at "
                "FROM ontology_proposals WHERE proposal_id = %s",
                (proposal_id,),
            )
            row = await cur.fetchone()
        return _row_to_proposal(row) if row else None

    async def list_by_project(
        self, project_id: str, status: str | None = None,
    ) -> list[OntologyEvolutionProposal]:
        assert self._conn is not None
        async with self._conn.cursor() as cur:
            if status:
                await cur.execute(
                    "SELECT proposal_id, project_id, layer, proposed_entity, "
                    "proposed_relation, evidence_count, sample_entities, "
                    "reasoning, status, created_at, resolver, resolved_at "
                    "FROM ontology_proposals "
                    "WHERE project_id = %s AND status = %s "
                    "ORDER BY created_at DESC",
                    (project_id, status),
                )
            else:
                await cur.execute(
                    "SELECT proposal_id, project_id, layer, proposed_entity, "
                    "proposed_relation, evidence_count, sample_entities, "
                    "reasoning, status, created_at, resolver, resolved_at "
                    "FROM ontology_proposals "
                    "WHERE project_id = %s ORDER BY created_at DESC",
                    (project_id,),
                )
            rows = await cur.fetchall()
        return [_row_to_proposal(r) for r in rows]


def _row_to_proposal(row) -> OntologyEvolutionProposal:
    """PG row → OntologyEvolutionProposal。"""
    from packages.common.types import OntologyEntityType, OntologyRelationType
    (
        proposal_id, project_id, layer, et_json, rt_json,
        evidence_count, samples_json, reasoning, status,
        created_at, resolver, resolved_at,
    ) = row

    et = None
    if et_json:
        data = et_json if isinstance(et_json, dict) else _safe_json_load(et_json)
        if data:
            et = OntologyEntityType.model_validate(data)
    rt = None
    if rt_json:
        data = rt_json if isinstance(rt_json, dict) else _safe_json_load(rt_json)
        if data:
            rt = OntologyRelationType.model_validate(data)
    samples: list = []
    if samples_json:
        if isinstance(samples_json, list):
            samples = samples_json
        else:
            samples = _safe_json_load(samples_json) or []

    return OntologyEvolutionProposal(
        proposal_id=proposal_id, project_id=project_id, layer=layer,
        proposed_entity_type=et, proposed_relation_type=rt,
        evidence_count=evidence_count, sample_entities=samples,
        reasoning=reasoning or "", status=status,
        created_at=created_at, resolver=resolver or "",
        resolved_at=resolved_at,
    )


def _safe_json_load(s):
    import json as _json
    try:
        return _json.loads(s)
    except (TypeError, ValueError):
        return None
