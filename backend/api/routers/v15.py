"""V15 专属路由集合 — Phase L 起.

/graph/view  — 实体级图谱视图 (community + centrality + inferred)
/wiki-map    — Wiki 页级关系网 (cross_refs 作为边)
/code-graph  — 代码模块依赖图 (Phase M, 借鉴 GitNexus)
/code-graph/blast-radius?target=X  — 改 target 时受影响的上游模块
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from packages.common import get_logger
from packages.governance.code_graph import blast_radius, build_code_graph
from packages.governance.graph_view import build_enhanced_graph_view
from packages.storage.graph_store import GraphStore
from packages.storage.wiki_store import WikiStore

from api.deps import get_graph_store, get_wiki_store

# 仓库根 (api/routers/v15.py → 上溯 3 层 = repo root)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# 模块级缓存 (代码图谱不随项目变, 只随代码改, 进程内缓存即可)
_code_graph_cache: dict | None = None


def _get_code_graph(force: bool = False) -> dict:
    global _code_graph_cache
    if _code_graph_cache is None or force:
        _code_graph_cache = build_code_graph(_REPO_ROOT)
    return _code_graph_cache

log = get_logger("api.v15")

router = APIRouter(prefix="/v15", tags=["V15"])


@router.get("/graph/view")
async def graph_view(
    project_id: str,
    max_nodes: int = 200,
    graph: GraphStore = Depends(get_graph_store),
) -> dict:
    """V15 Phase L: 返回带 community / centrality / inferred 的增强图谱数据。"""
    data = build_enhanced_graph_view(graph, project_id, max_nodes=max_nodes)
    log.info("v15_graph_view",
             project=project_id,
             nodes=data["stats"]["node_count"],
             edges=data["stats"]["edge_count"],
             communities=data["stats"]["community_count"])
    return data


# 域顶层颜色色环 (Nord palette + Tailwind extras)
_DOMAIN_PALETTE = [
    "#88c0d0",  # frost
    "#a3be8c",  # aurora green
    "#bf616a",  # aurora red
    "#ebcb8b",  # aurora yellow
    "#b48ead",  # aurora purple
    "#d08770",  # aurora orange
    "#5e81ac",  # frost dark
    "#8fbcbb",  # frost cyan
]


def _domain_root(page_id: str) -> str:
    """从 page_id 提取顶层域用于配色，如 'domain/energy/safety/hazard' → 'energy'"""
    parts = (page_id or "").split("/")
    # 形如 domain/<root>/...; 或 src/<doc_id>; 或裸 page_id
    if len(parts) >= 2 and parts[0] == "domain":
        return parts[1]
    if len(parts) >= 1 and parts[0] == "src":
        return "src"
    return parts[0] if parts else "misc"


@router.get("/wiki-map")
async def wiki_map(
    project_id: str,
    wiki_store: WikiStore = Depends(get_wiki_store),
) -> dict:
    """V15: Wiki 页级关系网。节点=Wiki页, 边=cross_refs。

    返回:
      {
        nodes: [{id, title, page_type, version, source_doc_count, cross_ref_count, domain_root, color, size}],
        edges: [{source, target, kind: 'cross_ref' | 'parent'}],
        domain_colors: {root: hex_color},
        stats: {nodes, edges, domain_count}
      }
    """
    pages = await wiki_store.list_pages(project_id)
    page_ids = {p.page_id for p in pages}

    # 1. 颜色按 domain root 染色
    roots = sorted({_domain_root(p.page_id) for p in pages})
    domain_colors = {r: _DOMAIN_PALETTE[i % len(_DOMAIN_PALETTE)] for i, r in enumerate(roots)}

    # 2. 节点
    nodes = []
    for p in pages:
        root = _domain_root(p.page_id)
        # 节点大小 = base + cross_ref_count + source_doc_count
        size = 5 + min(20, len(p.cross_refs or []) + min(8, len(p.source_doc_ids or [])))
        nodes.append({
            "id": p.page_id,
            "title": p.title,
            "page_type": p.page_type,
            "version": p.version,
            "source_doc_count": len(p.source_doc_ids or []),
            "cross_ref_count": len(p.cross_refs or []),
            "domain_root": root,
            "color": domain_colors[root],
            "size": size,
        })

    # 3. 边: cross_refs（仅当对方也在 pages 集合中才连）
    edges = []
    for p in pages:
        for ref in p.cross_refs or []:
            if ref in page_ids and ref != p.page_id:
                edges.append({"source": p.page_id, "target": ref, "kind": "cross_ref"})
        # parent 关系
        if p.parent_page_id and p.parent_page_id in page_ids:
            edges.append({"source": p.parent_page_id, "target": p.page_id, "kind": "parent"})

    log.info("v15_wiki_map", project=project_id, nodes=len(nodes), edges=len(edges))
    return {
        "nodes": nodes,
        "edges": edges,
        "domain_colors": domain_colors,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "domain_count": len(roots),
        },
    }


@router.get("/code-graph")
async def code_graph(force: bool = False) -> dict:
    """V15 Phase M (借鉴 GitNexus): 扫 packages/ + api/ 产出模块级依赖图.

    用例:
      • 改一处看影响 → 配合 /code-graph/blast-radius
      • 找 dead code → 看 is_dead=True 的节点
      • 看产品架构 → community 染色 + centrality 大小
    """
    g = _get_code_graph(force=force)
    log.info("v15_code_graph", **g["stats"])
    return g


@router.get("/code-graph/blast-radius")
async def code_blast_radius(target: str, max_hops: int = 3) -> dict:
    """改 target 模块时, 反向 BFS 找出受影响的上游模块.

    示例:
      target=packages.distillation.llm_client → 列出所有 import 它的模块, 按 hops 分层
    """
    g = _get_code_graph()
    result = blast_radius(g, target, max_hops=max_hops)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
