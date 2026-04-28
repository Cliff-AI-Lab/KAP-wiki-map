"""
健康检查路由模块。

提供系统健康状态的详细检查接口，逐一探测各下游组件（元数据存储、向量存储、
图谱存储、归档存储、Redis 缓存）的可用性，汇总后返回整体健康状态。

路由: GET /health
"""

import datetime

from fastapi import APIRouter

from api.deps import (
    get_archive_store,
    get_graph_store,
    get_metadata_store,
    get_vector_store,
)

router = APIRouter(tags=["健康检查"])


@router.get("/health")
async def health_check():
    """详细健康检查，包含各下游组件状态。

    依次检查以下组件并返回各自的运行模式和关键指标：
    - metadata_store: 元数据存储（PostgreSQL/内存），返回文档数量
    - vector_store: 向量存储（Milvus/内存），返回分块数量
    - graph_store: 图谱存储（Neo4j/内存），返回节点和边数量
    - archive_store: 归档存储（MinIO/本地文件系统）
    - redis_cache: Redis 缓存（可选组件，不影响整体状态）

    整体状态为 "ok"（所有核心组件正常）或 "degraded"（存在异常组件）。
    """
    components: dict[str, dict] = {}
    overall_ok = True

    # ── 元数据存储（PostgreSQL） ─────────────────────────
    try:
        meta = get_metadata_store()
        doc_count = len(await meta.list_documents())
        components["metadata_store"] = {
            "status": "ok",
            "mode": "memory" if meta._use_memory else "postgresql",
            "doc_count": doc_count,
        }
    except Exception as e:
        overall_ok = False
        components["metadata_store"] = {"status": "error", "error": str(e)}

    # ── 向量存储（Milvus） ───────────────────────────────
    try:
        vec = get_vector_store()
        components["vector_store"] = {
            "status": "ok",
            "mode": "memory" if vec._use_memory else "milvus",
            "chunk_count": vec.chunk_count,
        }
    except Exception as e:
        overall_ok = False
        components["vector_store"] = {"status": "error", "error": str(e)}

    # ── 图谱存储（Neo4j / 内存） ────────────────────────
    try:
        graph = get_graph_store()
        await graph.refresh_counts()  # 刷新节点/边计数缓存
        components["graph_store"] = {
            "status": "ok",
            "mode": "memory" if graph._use_memory else "neo4j",
            "node_count": graph.node_count,
            "edge_count": graph.edge_count,
        }
    except Exception as e:
        overall_ok = False
        components["graph_store"] = {"status": "error", "error": str(e)}

    # ── 归档存储（MinIO / 本地） ─────────────────────────
    try:
        archive = get_archive_store()
        components["archive_store"] = {
            "status": "ok",
            "mode": "local" if archive._use_local else "minio",
        }
    except Exception as e:
        overall_ok = False
        components["archive_store"] = {"status": "error", "error": str(e)}

    # ── Redis 缓存（可选，降级不影响整体状态） ───────────
    try:
        from packages.retrieval.cache import ResultCache
        cache = ResultCache()
        if cache._redis:
            cache._redis.ping()  # 发送 PING 命令检测 Redis 连通性
            components["redis_cache"] = {"status": "ok", "mode": "redis"}
        else:
            components["redis_cache"] = {"status": "ok", "mode": "disabled"}
    except Exception as e:
        components["redis_cache"] = {"status": "degraded", "error": str(e)}

    # ── 计算应用启动时间 ─────────────────────────────────
    from api.main import _STARTED_AT
    started_at = (
        datetime.datetime.fromtimestamp(_STARTED_AT, tz=datetime.timezone.utc).isoformat()
        if _STARTED_AT > 0 else None
    )

    return {
        "status": "ok" if overall_ok else "degraded",
        "service": "bookworm-agent",
        "version": "0.4.0",
        "started_at": started_at,
        "components": components,
    }
