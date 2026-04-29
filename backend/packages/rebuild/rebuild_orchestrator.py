"""重抽编排器（决策书 §5.3 全量重抽机制）。

核心流程：
1. SME 批准本体演化提议（M3 #1）→ 创建 RebuildJob
2. arun_rebuild 异步主循环：
   - 拉所有已入库 chunks
   - 对每个 chunk 计算 hash + 决策"调 W4 还是重映射"
   - 写入影子图谱（带 target_version 标签）
3. 完成后等 SME promote / rollback

设计原则（feedback memory · 轻量化）：
- 函数式实现，单文件
- 内存 RebuildJob store（M5 接 PG）
- asyncio.gather + Semaphore 限并发（M0 坑 1 模式）
- 失败回滚：清掉影子图谱版本桶
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from packages.common import get_logger
from packages.common.types import RebuildJob, RebuildStatus
from packages.rebuild.incremental_hash import (
    ChunkHashCache,
    ChunkHashStore,
    compute_chunk_hash,
    should_reextract,
)
from packages.rebuild.shadow_graph import get_shadow_store

log = get_logger("rebuild.orchestrator")


# ════════════════════════════════════════════════════════════════════════
#  Job Store（M4 lite 内存模式）
# ════════════════════════════════════════════════════════════════════════

_job_store: dict[str, RebuildJob] = {}


def reset_jobs_for_test() -> None:
    _job_store.clear()


def get_job(job_id: str) -> RebuildJob | None:
    return _job_store.get(job_id)


def list_jobs(project_id: str | None = None) -> list[RebuildJob]:
    out = list(_job_store.values())
    if project_id:
        out = [j for j in out if j.project_id == project_id]
    return sorted(out, key=lambda j: j.started_at, reverse=True)


# ════════════════════════════════════════════════════════════════════════
#  start_rebuild
# ════════════════════════════════════════════════════════════════════════


def start_rebuild(
    project_id: str,
    source_version: str,
    target_version: str,
) -> RebuildJob:
    """创建 RebuildJob 入库（不启动循环；调用方按需 await arun_rebuild）。"""
    job_id = f"rb_{uuid.uuid4().hex[:10]}"
    job = RebuildJob(
        job_id=job_id,
        project_id=project_id,
        source_version=source_version,
        target_version=target_version,
        status="pending",
    )
    _job_store[job_id] = job
    log.info("rebuild_job_created",
             job_id=job_id, project_id=project_id,
             source=source_version, target=target_version)
    return job


def update_status(job_id: str, status: RebuildStatus, error: str = "") -> None:
    job = _job_store.get(job_id)
    if not job:
        return
    job.status = status
    if error:
        job.error = error
    if status in ("completed", "failed", "cancelled"):
        job.finished_at = datetime.now(timezone.utc)


# ════════════════════════════════════════════════════════════════════════
#  arun_rebuild 主循环
# ════════════════════════════════════════════════════════════════════════


# 抽取并发上限（每文档一次 LLM 调用，避免限流）
_REBUILD_SEMAPHORE_LIMIT = 4


async def arun_rebuild(
    job: RebuildJob,
    *,
    chunks: list[dict],
    industry_code: str,
    extractor=None,                   # 注入 W4 extract_entities_and_relations，便于测试 mock
    hash_cache: ChunkHashStore | None = None,
) -> RebuildJob:
    """异步重抽主循环（决策书 §5.3）。

    Args:
        job: RebuildJob 实例（status 应为 pending）
        chunks: 待重抽 chunks 列表，每项 {chunk_id, doc_id, content}
        industry_code: 行业 code（W4 entity_extractor 用）
        extractor: 可注入的抽取函数；默认导入 packages.extraction
        hash_cache: 可注入哈希缓存；默认新建空缓存

    Returns:
        更新后的 RebuildJob（status=completed / failed）
    """
    if job.status != "pending":
        log.warning("rebuild_job_not_pending", job_id=job.job_id, status=job.status)
        return job

    update_status(job.job_id, "running")
    job.chunks_total = len(chunks)
    cache = hash_cache or ChunkHashCache()
    shadow = get_shadow_store()
    shadow.begin_shadow(job.project_id, job.target_version)

    # 默认 extractor（M3 #4 W4 实体抽取）
    if extractor is None:
        from packages.extraction.entity_extractor import (
            extract_entities_and_relations,
        )
        extractor = extract_entities_and_relations

    sem = asyncio.Semaphore(_REBUILD_SEMAPHORE_LIMIT)

    async def _process_chunk(c: dict) -> None:
        async with sem:
            chunk_id = c.get("chunk_id", "")
            doc_id = c.get("doc_id", "")
            content = c.get("content", "")
            try:
                content_hash = compute_chunk_hash(content)
                if should_reextract(chunk_id, content_hash, cache):
                    # cache miss → 调 W4 抽取
                    result = await extractor(
                        doc_id=doc_id,
                        content=content,
                        industry_code=industry_code,
                        project_id=job.project_id,
                    )
                    job.chunks_extracted += 1
                    cache.set(chunk_id, content_hash)
                    # 写入影子图谱
                    for entity in getattr(result, "entities", []):
                        shadow.add_entity(
                            job.project_id, job.target_version,
                            entity_name=entity.name, type_id=entity.type_id,
                            doc_id=doc_id,
                            properties=getattr(entity, "properties", {}) or {},
                        )
                    for rel in getattr(result, "relations", []):
                        # 关系的 source/target 是 entity_id；M4 lite 用名字索引（约定输入 chunks 中能反查）
                        # 简化：用 entity_id 作为 source/target name 占位（W4 输出用 stable id）
                        shadow.add_relation(
                            job.project_id, job.target_version,
                            source_name=rel.source_entity_id,
                            target_name=rel.target_entity_id,
                            relation_type_id=rel.relation_type_id,
                            doc_id=doc_id,
                            evidence=rel.evidence,
                        )
                else:
                    # hash 命中 → 跳过 W4，仅记录命中数
                    # M4 lite 假设旧抽取产物可在 promote 时按 type_id 重映射
                    job.chunks_hash_hit += 1
            except Exception as e:
                log.warning(
                    "rebuild_chunk_failed",
                    job_id=job.job_id, chunk_id=chunk_id, error=str(e),
                )
            finally:
                job.chunks_processed += 1
                job.progress = (
                    job.chunks_processed / job.chunks_total
                    if job.chunks_total > 0 else 1.0
                )

    try:
        await asyncio.gather(
            *(_process_chunk(c) for c in chunks),
            return_exceptions=False,
        )
    except Exception as e:
        log.error("rebuild_aborted", job_id=job.job_id, error=str(e))
        update_status(job.job_id, "failed", error=str(e))
        # 失败回滚：清影子库版本桶
        shadow.cancel_shadow(job.project_id)
        return job

    job.progress = 1.0  # 完成时强制满进度（处理空 chunks 边界）

    # M5 #3 · PG 持久化模式时，flush 把当批 hash 落盘
    flush = getattr(cache, "flush", None)
    if flush is not None and callable(flush):
        try:
            written = await flush()
            log.info("rebuild_hash_cache_flushed",
                     job_id=job.job_id, count=written)
        except Exception as e:
            log.warning("rebuild_hash_cache_flush_failed",
                        job_id=job.job_id, error=str(e))

    update_status(job.job_id, "completed")
    log.info(
        "rebuild_done",
        job_id=job.job_id,
        chunks_total=job.chunks_total,
        hash_hit=job.chunks_hash_hit,
        extracted=job.chunks_extracted,
    )
    return job
