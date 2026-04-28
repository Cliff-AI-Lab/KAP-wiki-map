"""FastAPI 依赖注入 — 单例存储实例管理。

本模块管理所有后端存储组件和业务服务的单例生命周期。
在应用启动时由 lifespan 回调调用 init_stores() 完成三阶段初始化：
  阶段1: 核心存储并行初始化（MetadataStore/VectorStore/GraphStore/ArchiveStore）
  阶段2: 依赖 PG 连接的存储（ProjectStore/DomainStore）
  阶段3: 检索组件组装（BM25/Reranker/Retriever/QAEngine/Cache）

各路由通过 get_xxx_store() 工厂函数获取单例实例（依赖注入模式）。
单个组件初始化失败不会阻塞其他组件（带超时保护），支持降级运行。
"""

from __future__ import annotations

import asyncio

import structlog

from packages.common.audit import AuditLogger
from packages.retrieval.cache import ResultCache
from packages.retrieval.keyword_scorer import BM25Scorer
from packages.retrieval.qa_engine import QAEngine
from packages.retrieval.reranker import BaseReranker, create_reranker
from packages.retrieval.retriever import BookwormRetriever
from packages.storage.archive_store import ArchiveStore
from packages.storage.domain_store import DomainStore
from packages.storage.governance_queue_store import GovernanceQueueStore
from packages.storage.graph_store import GraphStore
from packages.storage.metadata_store import MetadataStore
from packages.storage.project_store import ProjectStore
from packages.storage.raw_store import RawStore
from packages.storage.vector_store import VectorStore
from packages.storage.wiki_store import WikiStore

log = structlog.get_logger(__name__)

# 单个存储初始化的超时秒数（防止某个组件卡住阻塞整体启动）
_INIT_TIMEOUT = 30

# 追踪需要在 shutdown 时关闭的 PG 连接
_pg_connections: list = []

# ── 全局单例变量 ──
# 每个组件在 init_stores() 中初始化一次，后续通过 get_xxx() 函数访问
_vector_store: VectorStore | None = None          # 向量存储（Milvus）
_graph_store: GraphStore | None = None            # 知识图谱存储（内存模式/Neo4j）
_metadata_store: MetadataStore | None = None      # 元数据存储（PostgreSQL）
_archive_store: ArchiveStore | None = None        # 归档存储（MinIO/本地文件）
_domain_store: DomainStore | None = None          # 领域分类存储
_project_store: ProjectStore | None = None        # 项目管理存储
_keyword_scorer: BM25Scorer | None = None         # BM25 关键词评分器
_reranker: BaseReranker | None = None             # 重排序器（交叉编码器/模拟）
_retriever: BookwormRetriever | None = None       # 核心检索器（融合向量+图谱+关键词）
_qa_engine: QAEngine | None = None                # 问答引擎（检索+生成）
_result_cache: ResultCache | None = None          # 结果缓存（Redis，不可用时自动降级）
_audit_logger: AuditLogger | None = None          # 审计日志记录器
_raw_store: RawStore | None = None                # V11: 原始文档库（不可变层）
_wiki_store: WikiStore | None = None              # V11: Wiki页存储（编译产物层）
_governance_queue_store: GovernanceQueueStore | None = None  # V15: 治理工单队列


async def _safe_init(name: str, coro) -> None:
    """带超时保护的初始化，超时或异常不阻塞其他组件。

    每个存储组件独立超时，确保单个组件故障不会影响整体启动流程。
    """
    try:
        await asyncio.wait_for(coro, timeout=_INIT_TIMEOUT)
        log.info("store_initialized", store=name)
    except asyncio.TimeoutError:
        log.error("store_init_timeout", store=name, timeout=_INIT_TIMEOUT)
    except Exception as e:
        log.error("store_init_failed", store=name, error=str(e))


async def init_stores() -> None:
    """初始化所有存储。在应用启动时调用。

    每个存储组件有独立超时保护，单个组件不可用不会阻塞整体启动。
    初始化顺序：核心存储 -> PG 依赖存储 -> 业务组件。
    """
    global _vector_store, _graph_store, _metadata_store, _archive_store
    global _domain_store, _project_store, _result_cache
    global _keyword_scorer, _reranker, _retriever, _qa_engine, _audit_logger
    global _raw_store, _wiki_store, _governance_queue_store

    # ── 阶段 1: 核心存储并行初始化 ──
    _metadata_store = MetadataStore(use_memory=False)     # 使用真实 PostgreSQL
    _vector_store = VectorStore(use_memory=False)         # 使用真实 Milvus
    # V7: 图谱默认用内存模式（轻量 GraphRAG），不依赖 Neo4j
    # V15: GraphStore 暂保留 memory 模式 — graph_view.py / build_enhanced_graph_view
    # 直接读 _nodes / _edges 内存索引, 切 Neo4j 后图谱视图会变空.
    # 待 graph_view.py 适配 Neo4j Cypher 查询后再切 use_memory=False.
    _graph_store = GraphStore(use_memory=True)
    _archive_store = ArchiveStore(use_local=False)        # 使用 MinIO 对象存储

    await asyncio.gather(
        _safe_init("metadata_store", _metadata_store.initialize()),
        _safe_init("vector_store", _vector_store.initialize()),
        _safe_init("graph_store", _graph_store.initialize()),  # V7: 内存模式，瞬间完成
        _safe_init("archive_store", _archive_store.initialize()),
    )

    # ── 阶段 2: 依赖 PG 连接的存储 ──
    # 安全判断: MetadataStore 初始化可能失败并降级为内存模式
    _pg_available = hasattr(_metadata_store, '_conn') and _metadata_store._conn is not None
    _use_memory_fallback = not _pg_available or getattr(_metadata_store, '_use_memory', True)

    _project_store = ProjectStore(use_memory=_use_memory_fallback)
    _domain_store = DomainStore(use_memory=_use_memory_fallback)
    _raw_store = RawStore(use_memory=_use_memory_fallback)
    _wiki_store = WikiStore(use_memory=_use_memory_fallback)

    import psycopg
    from packages.common import settings

    async def _create_pg_conn(name: str):
        try:
            conn = await psycopg.AsyncConnection.connect(settings.postgres_dsn)
            _pg_connections.append(conn)
            return conn
        except Exception as e:
            log.warning("pg_connect_failed", store=name, error=str(e))
            return None

    if _pg_available:
        _domain_pg_conn = await _create_pg_conn("domain_store")
        await _safe_init("project_store", _project_store.initialize(pg_conn=_metadata_store._conn))
        await _safe_init("domain_store", _domain_store.initialize(pg_conn=_domain_pg_conn))

        _raw_pg_conn = await _create_pg_conn("raw_store")
        _wiki_pg_conn = await _create_pg_conn("wiki_store")
        await _safe_init("raw_store", _raw_store.initialize(pg_conn=_raw_pg_conn))
        await _safe_init("wiki_store", _wiki_store.initialize(pg_conn=_wiki_pg_conn))

        if hasattr(_project_store, '_pg_conn') and _project_store._pg_conn is not None:
            await _safe_init("default_project", _project_store.ensure_default_project())
    else:
        log.warning("pg_unavailable_all_stores_memory_mode")
        await _safe_init("project_store", _project_store.initialize())
        await _safe_init("domain_store", _domain_store.initialize())
        await _safe_init("raw_store", _raw_store.initialize())
        await _safe_init("wiki_store", _wiki_store.initialize())

    # V15: 治理工单队列（暂仅 memory 模式）
    _governance_queue_store = GovernanceQueueStore(use_memory=True)
    await _safe_init("governance_queue_store", _governance_queue_store.initialize())

    # ── 阶段 3: 不依赖外部服务的组件 ──
    _keyword_scorer = BM25Scorer()
    _reranker = create_reranker()    # 根据配置自动选择重排序器实现

    # 从现有向量库恢复 BM25 索引（冷启动时重建关键词索引）
    try:
        existing_chunks = _vector_store.get_all_chunks_for_bm25()
        if existing_chunks:
            _keyword_scorer.build_index(existing_chunks)
            log.info("bm25_index_restored", chunk_count=len(existing_chunks))
    except Exception as e:
        log.warning("bm25_index_restore_failed", error=str(e))

    # OPT-13: 结果缓存层（Redis 不可用时自动降级为无缓存模式）
    _result_cache = ResultCache()

    # 组装核心检索器：融合向量检索 + 图谱检索 + BM25 关键词检索 + 重排序
    _retriever = BookwormRetriever(
        _vector_store,
        _graph_store,
        _metadata_store,
        domain_store=_domain_store,
        keyword_scorer=_keyword_scorer,
        reranker=_reranker,
        cache=_result_cache,
    )
    # V11: 查询路由器（双路径: Wiki快路径 / RAG深路径）
    from packages.retrieval.query_router import QueryRouter
    _query_router = QueryRouter(_wiki_store) if _wiki_store else None
    # 问答引擎：在检索结果基础上调用 LLM 生成回答（V11: 集成 QueryRouter）
    _qa_engine = QAEngine(_retriever, cache=_result_cache,
                          query_router=_query_router, wiki_store=_wiki_store)
    # 审计日志：记录用户查询和系统操作
    _audit_logger = AuditLogger(metadata_store=_metadata_store)


# ── 以下为 FastAPI Depends() 注入用的工厂函数 ──
# 用 raise 而非 assert（assert 在 python -O 下会被移除）


def _require(instance, name: str):
    """安全的单例获取 — 不依赖 assert，生产环境 (-O) 也有效。"""
    if instance is None:
        from fastapi import HTTPException
        raise HTTPException(503, f"{name} 未初始化，服务暂不可用")
    return instance


def get_vector_store() -> VectorStore:
    return _require(_vector_store, "VectorStore")

def get_graph_store() -> GraphStore:
    return _require(_graph_store, "GraphStore")

def get_metadata_store() -> MetadataStore:
    return _require(_metadata_store, "MetadataStore")

def get_retriever() -> BookwormRetriever:
    return _require(_retriever, "Retriever")

def get_archive_store() -> ArchiveStore:
    return _require(_archive_store, "ArchiveStore")

def get_domain_store() -> DomainStore:
    return _require(_domain_store, "DomainStore")

def get_qa_engine() -> QAEngine:
    return _require(_qa_engine, "QAEngine")

def get_keyword_scorer() -> BM25Scorer:
    return _require(_keyword_scorer, "BM25Scorer")

def get_result_cache() -> ResultCache:
    return _require(_result_cache, "ResultCache")

def get_audit_logger() -> AuditLogger:
    return _require(_audit_logger, "AuditLogger")

def get_project_store() -> ProjectStore:
    return _require(_project_store, "ProjectStore")

def get_raw_store() -> RawStore:
    return _require(_raw_store, "RawStore")

def get_wiki_store() -> WikiStore:
    return _require(_wiki_store, "WikiStore")

def get_governance_queue_store() -> GovernanceQueueStore:
    return _require(_governance_queue_store, "GovernanceQueueStore")


async def shutdown_stores() -> None:
    """关闭所有存储连接。在应用退出时调用。"""
    for conn in _pg_connections:
        try:
            await conn.close()
        except Exception as e:
            log.warning("pg_conn_close_failed", error=str(e))
    _pg_connections.clear()

    # 关闭 MetadataStore 自己持有的连接
    if _metadata_store and hasattr(_metadata_store, '_conn') and _metadata_store._conn:
        try:
            await _metadata_store._conn.close()
        except Exception:
            pass

    log.info("all_stores_shutdown")
