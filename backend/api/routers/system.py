"""V15 系统组件状态 API.

设计原则: 重组件 (Milvus / Neo4j / Redis / MinIO) 可选, 失败 fallback memory.
此端点暴露每个 store 的当前 mode + 后端依赖连通状态, 供前端可视化展示和故障诊断.
"""

from __future__ import annotations

from fastapi import APIRouter

from packages.common import get_logger, settings as app_settings
from api.deps import (
    get_metadata_store, get_vector_store, get_graph_store, get_archive_store,
    get_project_store, get_domain_store, get_raw_store, get_wiki_store,
    get_governance_queue_store,
)

log = get_logger("api.system")

router = APIRouter(prefix="/system", tags=["系统"])


@router.get("/components")
async def list_components() -> dict:
    """返回基础设施 + 应用层 Store 的运行状态.

    返回:
        {
          "infra": [{name, status, addr, required, optional}],
          "stores": [{name, category, mode, count, status}],
          "summary": {total, ok, fallback, unavailable}
        }
    """
    # === 基础设施层 ===
    deps = app_settings.validate_dependencies()
    infra = []
    for key, label, required, opt in [
        ("postgresql", "PostgreSQL",   True,  False),
        ("neo4j",      "Neo4j",        False, True),
        ("milvus",     "Milvus",       False, True),
        ("redis",      "Redis",        False, True),
        ("minio",      "MinIO",        False, True),
    ]:
        info = deps.get(key, {})
        status = info.get("status", "unknown")
        infra.append({
            "key": key,
            "name": label,
            "status": status,             # ok / unavailable
            "addr": info.get("addr") or (info.get("error") or "")[:120],
            "required": required,         # True 表示必选; False 表示可选 (fallback)
            "optional": opt,
        })

    # === Store 层 (从单例读 mode) ===
    def store_mode(store, real_label: str = "pg", attr: str = "_use_memory") -> str:
        """统一返回 store 后端: memory / 真后端标签 (pg/neo4j/milvus/minio).
        attr 区分不同 store 的 fallback 标志名."""
        try:
            return "memory" if getattr(store, attr, False) else real_label
        except Exception:
            return "unknown"

    def safe_count(store, count_attr: str | None = None) -> int | None:
        if count_attr:
            try:
                v = getattr(store, count_attr, None)
                return len(v) if hasattr(v, "__len__") else (int(v) if v is not None else None)
            except Exception:
                return None
        return None

    stores = []
    try:
        s = get_metadata_store()
        stores.append({"name": "MetadataStore", "category": "core",
                       "desc": "文档元数据", "mode": store_mode(s),
                       "depends": "PostgreSQL"})
    except Exception as e:
        stores.append({"name": "MetadataStore", "category": "core", "status": "error", "error": str(e)[:80]})

    try:
        s = get_project_store()
        stores.append({"name": "ProjectStore", "category": "core",
                       "desc": "项目库", "mode": store_mode(s),
                       "count": safe_count(s, "_projects"),
                       "depends": "PostgreSQL"})
    except Exception as e:
        stores.append({"name": "ProjectStore", "category": "core", "status": "error", "error": str(e)[:80]})

    try:
        s = get_domain_store()
        stores.append({"name": "DomainStore", "category": "core",
                       "desc": "知识体系四级", "mode": store_mode(s),
                       "depends": "PostgreSQL"})
    except Exception as e:
        stores.append({"name": "DomainStore", "category": "core", "status": "error", "error": str(e)[:80]})

    try:
        s = get_raw_store()
        stores.append({"name": "RawStore", "category": "core",
                       "desc": "原始文档库 (不可变)", "mode": store_mode(s),
                       "depends": "PostgreSQL"})
    except Exception as e:
        stores.append({"name": "RawStore", "category": "core", "status": "error", "error": str(e)[:80]})

    try:
        s = get_wiki_store()
        stores.append({"name": "WikiStore", "category": "core",
                       "desc": "Karpathy 三层 Wiki 编译产物", "mode": store_mode(s),
                       "depends": "PostgreSQL"})
    except Exception as e:
        stores.append({"name": "WikiStore", "category": "core", "status": "error", "error": str(e)[:80]})

    try:
        s = get_vector_store()
        stores.append({"name": "VectorStore", "category": "optional",
                       "desc": "向量检索 (RAG 路径)", "mode": store_mode(s, "milvus"),
                       "depends": "Milvus"})
    except Exception as e:
        stores.append({"name": "VectorStore", "category": "optional", "status": "error", "error": str(e)[:80]})

    try:
        s = get_graph_store()
        stores.append({"name": "GraphStore", "category": "optional",
                       "desc": "知识图谱 (实体关系)", "mode": store_mode(s, "neo4j"),
                       "depends": "Neo4j"})
    except Exception as e:
        stores.append({"name": "GraphStore", "category": "optional", "status": "error", "error": str(e)[:80]})

    try:
        s = get_archive_store()
        stores.append({"name": "ArchiveStore", "category": "optional",
                       "desc": "归档存储", "mode": store_mode(s, "minio", attr="_use_local"),
                       "depends": "MinIO"})
    except Exception as e:
        stores.append({"name": "ArchiveStore", "category": "optional", "status": "error", "error": str(e)[:80]})

    try:
        s = get_governance_queue_store()
        stores.append({"name": "GovernanceQueueStore", "category": "v15",
                       "desc": "治理 Agent 工单池", "mode": store_mode(s),
                       "depends": "PostgreSQL (待落库)"})
    except Exception as e:
        stores.append({"name": "GovernanceQueueStore", "category": "v15", "status": "error", "error": str(e)[:80]})

    # === 汇总 ===
    ok = sum(1 for x in infra if x["status"] == "ok")
    fallback = sum(1 for s in stores if s.get("mode") == "memory")
    persistent = sum(1 for s in stores if s.get("mode") not in ("memory", None, "unknown"))
    total_components = len(infra) + len(stores)

    return {
        "infra": infra,
        "stores": stores,
        "summary": {
            "infra_total": len(infra),
            "infra_ok": ok,
            "infra_unavailable": len(infra) - ok,
            "store_total": len(stores),
            "store_persistent": persistent,   # 真后端模式数 (pg/neo4j/milvus/minio)
            "store_pg_mode": sum(1 for s in stores if s.get("mode") == "pg"),
            "store_memory_mode": fallback,
            "total": total_components,
        },
    }


@router.get("/health")
async def deep_health() -> dict:
    """详细健康检查 (非简单 200/500), 兼容 monitoring 探针."""
    deps = app_settings.validate_dependencies()
    healthy = all(d.get("status") == "ok" or k != "postgresql" for k, d in deps.items())
    return {
        "status": "healthy" if healthy else "degraded",
        "dependencies": deps,
    }
