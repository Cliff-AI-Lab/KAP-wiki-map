"""M4 全量重抽影子库 lite（决策书 §5.3 工程闭环）。

当 SME 批准本体演化提议（M3 #1）后，本模块负责：
1. 启动重抽任务（``rebuild_orchestrator``）
2. 把所有已入库 chunks 按新本体抽取实体（影子图谱）
3. 增量哈希跳过未变 chunks（``incremental_hash``）
4. SME 对比新旧版本（``switch_orchestrator``）
5. 灰度切换 / 一键回滚

模块组成（M4 lite 范围 — 增量交付）：
- 批 1 ``shadow_graph`` + ``incremental_hash`` — 影子图谱抽象 + chunk 哈希
- 批 2 ``rebuild_orchestrator``                — 重抽编排器
- 批 3 ``switch_orchestrator``                 — 灰度切换 + 回滚
- 批 4 API endpoints
- 批 5 监测条件 2-4 stub

M5 增量（已交付）：
- M5 #1 监测条件 2/3/4 完整 LLM 实现（packages.ontology.evolution_proposer）
- M5 #2 7 天观察期 + 指标采集（``promotion_observer`` + ``metrics_collector``）

M5 后续：
- 独立物理 Neo4j 实例
- as_of 历史回溯查询
- ChunkHashCache PG 持久化
"""

from packages.rebuild.incremental_hash import (
    ChunkHashCache,
    ChunkHashStore,
    PgChunkHashCache,
    compute_chunk_hash,
    get_chunk_hash_cache,
    should_reextract,
)
from packages.rebuild.metrics_collector import collect_metrics, compute_drift
from packages.rebuild.promotion_observer import (
    OBSERVATION_DAYS,
    get_current_observation,
    get_observation,
    list_observations,
    mark_rolled_back,
    reset_observations_for_test,
    start_observation,
    tick_all_observations,
    tick_observation,
)
from packages.rebuild.rebuild_orchestrator import (
    arun_rebuild,
    get_job,
    list_jobs,
    reset_jobs_for_test,
    start_rebuild,
)
from packages.rebuild.shadow_graph import (
    ShadowGraphStore,
    get_shadow_store,
    reset_shadow_store_for_test,
)
from packages.rebuild.switch_orchestrator import (
    PromoteRefused,
    compare_versions,
    promote_shadow,
    rollback_promotion,
)

__all__ = [
    "OBSERVATION_DAYS",
    "ChunkHashCache",
    "ChunkHashStore",
    "PgChunkHashCache",
    "PromoteRefused",
    "ShadowGraphStore",
    "arun_rebuild",
    "collect_metrics",
    "compare_versions",
    "compute_chunk_hash",
    "compute_drift",
    "get_chunk_hash_cache",
    "get_current_observation",
    "get_job",
    "get_observation",
    "get_shadow_store",
    "list_jobs",
    "list_observations",
    "mark_rolled_back",
    "promote_shadow",
    "reset_jobs_for_test",
    "reset_observations_for_test",
    "reset_shadow_store_for_test",
    "rollback_promotion",
    "should_reextract",
    "start_observation",
    "start_rebuild",
    "tick_all_observations",
    "tick_observation",
]
