"""M4 批 2 · 重抽编排器单测（决策书 §5.3）。"""

from __future__ import annotations

import pytest

from packages.common.types import (
    ExtractedEntity,
    ExtractedRelation,
    ExtractionResult,
    RebuildJob,
)
from packages.rebuild import (
    arun_rebuild,
    get_job,
    get_shadow_store,
    list_jobs,
    reset_jobs_for_test,
    reset_shadow_store_for_test,
    start_rebuild,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_jobs_for_test()
    reset_shadow_store_for_test()
    yield
    reset_jobs_for_test()
    reset_shadow_store_for_test()


# ════════════════════════════════════════════════════════════════════════
#  start_rebuild / get_job / list_jobs
# ════════════════════════════════════════════════════════════════════════


class TestJobLifecycle:
    def test_start_creates_pending_job(self) -> None:
        job = start_rebuild("p1", "v1.0.0", "v1.0.1")
        assert job.status == "pending"
        assert job.source_version == "v1.0.0"
        assert job.target_version == "v1.0.1"
        assert job.job_id.startswith("rb_")

    def test_get_job_by_id(self) -> None:
        job = start_rebuild("p1", "v1", "v2")
        retrieved = get_job(job.job_id)
        assert retrieved is not None
        assert retrieved.job_id == job.job_id

    def test_list_jobs_filters_by_project(self) -> None:
        start_rebuild("A", "v1", "v2")
        start_rebuild("A", "v2", "v3")
        start_rebuild("B", "v1", "v2")
        assert len(list_jobs("A")) == 2
        assert len(list_jobs("B")) == 1
        assert len(list_jobs()) == 3


# ════════════════════════════════════════════════════════════════════════
#  arun_rebuild — 主循环
# ════════════════════════════════════════════════════════════════════════


def _mk_extractor(entities=None, relations=None):
    """构造 fake W4 extractor，返回固定结果。"""
    async def _extractor(*, doc_id, content, industry_code, project_id):
        return ExtractionResult(
            doc_id=doc_id,
            entities=entities or [],
            relations=relations or [],
        )
    return _extractor


class TestArunRebuild:
    async def test_normal_flow(self) -> None:
        job = start_rebuild("p1", "v1", "v2")
        chunks = [
            {"chunk_id": f"c{i}", "doc_id": f"d{i}", "content": f"内容 {i}"}
            for i in range(3)
        ]
        extractor = _mk_extractor(
            entities=[ExtractedEntity(
                entity_id="e1", name="设备 A", type_id="equipment",
            )],
        )

        result = await arun_rebuild(
            job, chunks=chunks,
            industry_code="manufacturing",
            extractor=extractor,
        )

        assert result.status == "completed"
        assert result.chunks_total == 3
        assert result.chunks_processed == 3
        assert result.chunks_extracted == 3  # 全部 cache miss
        assert result.progress == 1.0

        # 影子图谱含实体（同名 dedup → 1 个）
        shadow = get_shadow_store()
        entities = shadow.list_entities("p1", "v2")
        assert len(entities) == 1

    async def test_hash_cache_hit_skips_extraction(self) -> None:
        from packages.rebuild import ChunkHashCache, compute_chunk_hash

        job = start_rebuild("p1", "v1", "v2")
        chunks = [
            {"chunk_id": "c1", "doc_id": "d1", "content": "stable content"},
            {"chunk_id": "c2", "doc_id": "d2", "content": "stable content 2"},
        ]
        # 预填缓存：c1 已经有 hash 记录
        cache = ChunkHashCache()
        cache.set("c1", compute_chunk_hash("stable content"))

        call_count = {"n": 0}

        async def _extractor(*, doc_id, content, industry_code, project_id):
            call_count["n"] += 1
            return ExtractionResult(doc_id=doc_id)

        result = await arun_rebuild(
            job, chunks=chunks,
            industry_code="manufacturing",
            extractor=_extractor,
            hash_cache=cache,
        )

        assert result.chunks_hash_hit == 1   # c1 命中
        assert result.chunks_extracted == 1  # 仅 c2 被抽取
        assert call_count["n"] == 1

    async def test_progress_updates_to_one(self) -> None:
        job = start_rebuild("p1", "v1", "v2")
        chunks = [{"chunk_id": "c", "doc_id": "d", "content": "x"}]
        extractor = _mk_extractor()
        result = await arun_rebuild(
            job, chunks=chunks,
            industry_code="manufacturing",
            extractor=extractor,
        )
        assert result.progress == 1.0

    async def test_empty_chunks_progress_one(self) -> None:
        job = start_rebuild("p1", "v1", "v2")
        result = await arun_rebuild(
            job, chunks=[],
            industry_code="manufacturing",
            extractor=_mk_extractor(),
        )
        assert result.status == "completed"
        assert result.progress == 1.0
        assert result.chunks_total == 0

    async def test_extractor_failure_recorded_but_not_aborts(self) -> None:
        """单 chunk 抽取失败不中断整个重抽。"""
        job = start_rebuild("p1", "v1", "v2")
        chunks = [
            {"chunk_id": "c1", "doc_id": "d1", "content": "ok"},
            {"chunk_id": "c2", "doc_id": "d2", "content": "fail"},
        ]

        call_count = {"n": 0}

        async def _flaky(*, doc_id, content, industry_code, project_id):
            call_count["n"] += 1
            if content == "fail":
                raise RuntimeError("simulated")
            return ExtractionResult(doc_id=doc_id)

        result = await arun_rebuild(
            job, chunks=chunks,
            industry_code="manufacturing",
            extractor=_flaky,
        )
        assert result.status == "completed"
        assert result.chunks_processed == 2
        # extracted 仅成功的（c1）
        assert result.chunks_extracted == 1

    async def test_only_pending_jobs_can_run(self) -> None:
        job = start_rebuild("p1", "v1", "v2")
        # 改成已完成
        job.status = "completed"
        result = await arun_rebuild(
            job, chunks=[{"chunk_id": "c", "doc_id": "d", "content": "x"}],
            industry_code="manufacturing",
            extractor=_mk_extractor(),
        )
        # status 不变（仍是 completed）但不会重跑
        assert result.status == "completed"
        assert result.chunks_processed == 0  # 没跑

    async def test_relation_writes_to_shadow(self) -> None:
        job = start_rebuild("p1", "v1", "v2")
        extractor = _mk_extractor(
            entities=[
                ExtractedEntity(entity_id="e1", name="A", type_id="t1"),
                ExtractedEntity(entity_id="e2", name="B", type_id="t2"),
            ],
            relations=[
                ExtractedRelation(
                    source_entity_id="e1", target_entity_id="e2",
                    relation_type_id="uses",
                ),
            ],
        )
        chunks = [{"chunk_id": "c", "doc_id": "d", "content": "x"}]
        await arun_rebuild(
            job, chunks=chunks,
            industry_code="manufacturing",
            extractor=extractor,
        )
        shadow = get_shadow_store()
        rels = shadow.list_relations("p1", "v2")
        assert len(rels) == 1
        assert rels[0]["relation_type_id"] == "uses"
