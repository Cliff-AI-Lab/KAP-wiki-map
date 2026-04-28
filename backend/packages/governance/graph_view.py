"""V15 Phase L: 图谱视图增强.

在 GraphStore 基础上用 networkx 做:
  - Community Detection (Louvain)
  - Degree / Betweenness Centrality
  - 支持边的 'inferred' 标签区分（Inferer Agent 产出的虚线关系）

借鉴: ai-knowledge-graph 的 community 染色 + centrality 大小 + 虚线推理关系.
"""

from __future__ import annotations

from typing import Any

import networkx as nx

from packages.common import get_logger

log = get_logger("governance.graph_view")


def build_enhanced_graph_view(
    graph_store: Any,
    project_id: str,
    max_nodes: int = 200,
) -> dict[str, Any]:
    """返回增强图谱视图数据.

    结构:
      {
        "nodes": [{id, name, community, centrality, size, type, doc_count}],
        "edges": [{source, target, relation, inferred}],
        "stats": {node_count, edge_count, community_count, max_centrality}
      }
    """
    G: nx.Graph = nx.Graph()

    nodes_dict = getattr(graph_store, "_nodes", {}) or {}
    edges_list = getattr(graph_store, "_edges", []) or []

    # 加节点
    for name, info in nodes_dict.items():
        if not isinstance(info, dict):
            continue
        G.add_node(
            name,
            entity_type=info.get("type", "entity"),
            domain_id=info.get("domain_id", ""),
            doc_count=len(info.get("doc_ids") or []),
        )

    # 加边
    for edge in edges_list:
        if not isinstance(edge, dict):
            continue
        src = edge.get("source")
        tgt = edge.get("target")
        if not src or not tgt:
            continue
        if src not in G or tgt not in G:
            # 跳过指向不存在节点的边
            continue
        G.add_edge(
            src, tgt,
            relation=edge.get("relation") or edge.get("type", ""),
            inferred=bool(edge.get("inferred", False)),
        )

    if G.number_of_nodes() == 0:
        return {
            "nodes": [],
            "edges": [],
            "stats": {"node_count": 0, "edge_count": 0, "community_count": 0, "max_centrality": 0.0},
        }

    # 超大图限流 — 取 degree 前 max_nodes
    if G.number_of_nodes() > max_nodes:
        degs = dict(G.degree())
        keep = sorted(degs, key=lambda n: degs[n], reverse=True)[:max_nodes]
        G = G.subgraph(keep).copy()

    # Community Detection (Louvain, 容错 fallback)
    try:
        communities = list(nx.community.louvain_communities(G, seed=42))
    except Exception as e:
        log.warning("louvain_failed_fallback_cc", error=str(e))
        communities = [set(c) for c in nx.connected_components(G)]

    node_community: dict[str, int] = {}
    for idx, comm in enumerate(communities):
        for n in comm:
            node_community[n] = idx

    # Centrality (度中心性 — 快; 介数太慢大图跳过)
    degree_cent = nx.degree_centrality(G) if G.number_of_nodes() > 0 else {}
    max_cent = max(degree_cent.values()) if degree_cent else 0.0

    # 产出
    out_nodes: list[dict[str, Any]] = []
    for n in G.nodes():
        data = G.nodes[n]
        cent = degree_cent.get(n, 0.0)
        # size: 5 ~ 22 px 线性映射
        size = 5.0 + 17.0 * (cent / max_cent if max_cent > 0 else 0)
        out_nodes.append({
            "id": n,
            "name": n,
            "community": node_community.get(n, 0),
            "centrality": round(cent, 4),
            "size": round(size, 2),
            "type": data.get("entity_type", "entity"),
            "doc_count": data.get("doc_count", 0),
        })

    out_edges: list[dict[str, Any]] = []
    for u, v, data in G.edges(data=True):
        out_edges.append({
            "source": u,
            "target": v,
            "relation": data.get("relation", ""),
            "inferred": bool(data.get("inferred", False)),
        })

    return {
        "nodes": out_nodes,
        "edges": out_edges,
        "stats": {
            "node_count": G.number_of_nodes(),
            "edge_count": G.number_of_edges(),
            "community_count": len(communities),
            "max_centrality": round(max_cent, 4),
        },
    }
