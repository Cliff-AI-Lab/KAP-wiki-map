"""图数据库存储 — V8 重构：双向索引 + 实体归一化 + 关系去重。

核心理念（对齐书虫五大原则）：
- 图谱不做存储系统，只做实体关系可视化（轻量化定位）
- 图谱按知识体系分支逐层展开（知识图谱逐层展开）
- 双向索引支撑文档关联发现（清晰快捷的知识梳理）

V8 改造要点：
- 新增 _entity_docs 反向索引（entity→docs）
- 新增 _edge_index 关系去重合并（同对实体同关系 → weight++）
- 实体名归一化（NFKC + 同义映射）
- get_entities_by_domain 返回增加 doc_ids, weight
- 新增 get_docs_by_entity, get_shared_entity_docs, get_doc_view_graph
"""

from __future__ import annotations

import unicodedata
from typing import Optional

from packages.common import get_logger, settings
from packages.common.types import EntityRelation, MentionedEntity

log = get_logger("storage.graph")


class GraphStore:
    """V8 知识图谱 — 双向索引 + 实体归一化 + 关系去重。"""

    def __init__(self, use_memory: bool = False):
        self._use_memory = use_memory
        self._driver = None

        # === 节点与边 ===
        self._nodes: dict[str, dict] = {}  # entity_name -> {type, domain_id, doc_ids}
        self._edges: list[dict] = []        # {source, relation, target, weight}

        # === V7 保留：正向索引（检索评分用） ===
        self._doc_entities: dict[str, list[str]] = {}  # doc_id -> [entity_names]

        # === V8 新增：反向索引 ===
        self._entity_docs: dict[str, list[str]] = {}   # entity_name -> [doc_ids]

        # === V8 新增：关系去重索引 ===
        self._edge_index: dict[str, dict] = {}  # "source|target|relation" -> {weight, doc_ids}

        # === V8 新增：同义映射（初始为空，可通过配置扩展） ===
        self._synonym_map: dict[str, str] = {}

    async def initialize(self) -> None:
        if self._use_memory:
            log.info("graph_store_memory_mode_v8")
            return

        try:
            from neo4j import AsyncGraphDatabase

            self._driver = AsyncGraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
            async with self._driver.session() as session:
                await session.run("RETURN 1")
            await self.refresh_counts()
            log.info("graph_store_neo4j_connected_v8")
        except Exception as e:
            log.warning("graph_store_fallback_to_memory", error=str(e))
            self._use_memory = True

    # ── V8: 实体归一化 ──────────────────────────────────────

    def _normalize_entity_name(self, name: str) -> str:
        """V8: 归一化实体名 — 去空格、统一全半角、同义映射。"""
        name = name.strip()
        name = unicodedata.normalize("NFKC", name)  # 全角→半角
        return self._synonym_map.get(name, name)

    # ── 核心方法：添加实体和关系 ────────────────────────────

    async def add_entities_and_relations(
        self,
        doc_id: str,
        entities: list[MentionedEntity],
        relations: list[EntityRelation],
        domain_id: str = "",
    ) -> None:
        """添加实体和关系到图谱。

        V8 改造：
        - 实体名归一化
        - 同步更新正向索引 _doc_entities 和反向索引 _entity_docs
        - 关系去重合并（同对实体同关系 → weight++）
        """
        entity_names = []
        for ent in entities:
            # V8: 实体归一化
            normalized_name = self._normalize_entity_name(ent.name)
            entity_names.append(normalized_name)
            label = _safe_label(ent.type)

            if self._use_memory:
                existing = self._nodes.get(normalized_name, {})
                doc_ids = set(existing.get("doc_ids", []))
                doc_ids.add(doc_id)
                self._nodes[normalized_name] = {
                    "type": label,
                    "domain_id": domain_id or existing.get("domain_id", ""),
                    "doc_ids": list(doc_ids),
                }
            else:
                async with self._driver.session() as session:
                    await session.run(
                        f"""
                        MERGE (e:{label} {{name: $name}})
                        SET e.domain_id = COALESCE($domain_id, e.domain_id, '')
                        SET e.doc_ids = CASE
                            WHEN e.doc_ids IS NULL THEN [$doc_id]
                            WHEN NOT $doc_id IN e.doc_ids THEN e.doc_ids + $doc_id
                            ELSE e.doc_ids
                        END
                        """,
                        name=normalized_name,
                        domain_id=domain_id,
                        doc_id=doc_id,
                    )

            # V8: 更新反向索引
            if normalized_name not in self._entity_docs:
                self._entity_docs[normalized_name] = []
            if doc_id not in self._entity_docs[normalized_name]:
                self._entity_docs[normalized_name].append(doc_id)

        # 更新正向索引 _doc_entities
        existing_ents = self._doc_entities.get(doc_id, [])
        self._doc_entities[doc_id] = list(set(existing_ents + entity_names))

        # V8: 关系去重合并
        for rel in relations:
            src = self._normalize_entity_name(rel.source)
            tgt = self._normalize_entity_name(rel.target)

            # 确保端点节点存在
            for name in (src, tgt):
                if name not in self._nodes:
                    self._nodes[name] = {
                        "type": "Entity",
                        "domain_id": domain_id,
                        "doc_ids": [doc_id],
                    }
                    if name not in self._entity_docs:
                        self._entity_docs[name] = []
                    if doc_id not in self._entity_docs[name]:
                        self._entity_docs[name].append(doc_id)

            edge_key = f"{src}|{tgt}|{rel.relation}"

            if edge_key in self._edge_index:
                # 已有同样的关系 → weight++
                self._edge_index[edge_key]["weight"] += 1
                self._edge_index[edge_key]["doc_ids"].add(doc_id)
                # 更新 _edges 中对应项的 weight
                for edge in self._edges:
                    if (edge["source"] == src and edge["target"] == tgt
                            and edge["relation"] == rel.relation):
                        edge["weight"] = self._edge_index[edge_key]["weight"]
                        break
            else:
                # 新关系
                self._edge_index[edge_key] = {"weight": 1, "doc_ids": {doc_id}}
                self._edges.append({
                    "source": src,
                    "relation": rel.relation,
                    "target": tgt,
                    "weight": 1,
                })

            if not self._use_memory and self._driver:
                async with self._driver.session() as session:
                    await session.run(
                        """
                        MERGE (a {name: $src})
                        MERGE (b {name: $tgt})
                        MERGE (a)-[r:RELATES {type: $rel}]->(b)
                        """,
                        src=src,
                        tgt=tgt,
                        rel=rel.relation,
                    )

    # ── 查询方法 ────────────────────────────────────────────

    async def get_doc_entities(self, doc_id: str) -> list[str]:
        """获取文档提到的实体列表（正向索引）。"""
        return self._doc_entities.get(doc_id, [])

    async def get_docs_by_entity(self, entity_name: str) -> list[str]:
        """V8: 反向查询 — 通过实体名获取所有关联文档ID。"""
        normalized = self._normalize_entity_name(entity_name)
        return self._entity_docs.get(normalized, [])

    async def get_shared_entity_docs(self, doc_id: str) -> list[dict]:
        """V8: 查找与指定文档共享实体的其他文档。

        返回: [{"doc_id": "xxx", "shared_entities": ["实体A", "实体B"], "count": 2}]
        """
        my_entities = self._doc_entities.get(doc_id, [])
        doc_shared: dict[str, set[str]] = {}
        for ent in my_entities:
            for other_doc in self._entity_docs.get(ent, []):
                if other_doc != doc_id:
                    doc_shared.setdefault(other_doc, set()).add(ent)
        return [
            {"doc_id": d, "shared_entities": list(ents), "count": len(ents)}
            for d, ents in sorted(doc_shared.items(), key=lambda x: -len(x[1]))
        ]

    async def find_related_docs(self, entity_name: str, max_hops: int = 2) -> list[str]:
        """通过实体查找关联文档。V8: 利用反向索引加速。"""
        normalized = self._normalize_entity_name(entity_name)
        related = set()

        # 直接关联（V8: 用反向索引）
        related.update(self._entity_docs.get(normalized, []))

        # 扩展一跳关系
        if max_hops > 1:
            related_entities = set()
            if self._use_memory:
                for edge in self._edges:
                    if edge["source"] == normalized:
                        related_entities.add(edge["target"])
                    elif edge["target"] == normalized:
                        related_entities.add(edge["source"])
            else:
                node_info = await self._get_neo4j_neighbors(normalized)
                related_entities = set(node_info)
            for neighbor_ent in related_entities:
                related.update(self._entity_docs.get(neighbor_ent, []))
        return list(related)

    async def find_entity_by_keyword(self, keyword: str) -> list[str]:
        """通过关键词模糊匹配实体名。"""
        if self._use_memory:
            return [name for name in self._nodes if keyword in name]

        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (e) WHERE e.name CONTAINS $kw RETURN e.name LIMIT 10",
                kw=keyword,
            )
            return [record["e.name"] async for record in result]

    async def get_entities_by_domain(self, domain_id: str) -> tuple[list[dict], list[dict]]:
        """获取某知识体系分支下的所有实体和关系。

        V8 增强：返回 nodes 含 doc_ids, edges 含 weight。
        对齐核心理念：图谱按体系分支逐层展开。
        """
        if self._use_memory:
            nodes = []
            node_names = set()
            for name, info in self._nodes.items():
                nd = info.get("domain_id", "")
                if not domain_id or nd == domain_id or nd.startswith(domain_id + "/"):
                    nodes.append({
                        "id": name,
                        "label": name,
                        "type": info.get("type", "Entity"),
                        "domain_id": nd,
                        "doc_count": len(info.get("doc_ids", [])),
                        "doc_ids": info.get("doc_ids", []),  # V8 新增
                    })
                    node_names.add(name)
            edges = []
            for edge in self._edges:
                if edge["source"] in node_names and edge["target"] in node_names:
                    edges.append({
                        "source": edge["source"],
                        "target": edge["target"],
                        "relation": edge["relation"],
                        "weight": edge.get("weight", 1),  # V8 新增
                    })
            return nodes, edges

        # Neo4j 模式
        nodes = []
        edges = []
        async with self._driver.session() as session:
            if domain_id:
                result = await session.run(
                    """
                    MATCH (e) WHERE e.domain_id = $did OR e.domain_id STARTS WITH $prefix
                    RETURN e.name AS name, labels(e)[0] AS type, e.domain_id AS domain_id,
                           e.doc_ids AS doc_ids
                    LIMIT 200
                    """,
                    did=domain_id,
                    prefix=domain_id + "/",
                )
            else:
                result = await session.run(
                    """
                    MATCH (e) RETURN e.name AS name, labels(e)[0] AS type,
                           e.domain_id AS domain_id, e.doc_ids AS doc_ids
                    LIMIT 200
                    """,
                )
            async for r in result:
                doc_ids = r["doc_ids"] or []
                nodes.append({
                    "id": r["name"],
                    "label": r["name"],
                    "type": r["type"] or "Entity",
                    "domain_id": r["domain_id"] or "",
                    "doc_count": len(doc_ids),
                    "doc_ids": doc_ids,
                })

            node_names = {n["id"] for n in nodes}
            if node_names:
                result = await session.run(
                    """
                    MATCH (a)-[r:RELATES]->(b)
                    WHERE a.name IN $names AND b.name IN $names
                    RETURN a.name AS source, r.type AS relation, b.name AS target
                    LIMIT 500
                    """,
                    names=list(node_names),
                )
                async for r in result:
                    edges.append({
                        "source": r["source"],
                        "target": r["target"],
                        "relation": r["relation"] or "RELATES",
                        "weight": 1,
                    })

        return nodes, edges

    async def get_doc_view_graph(self, domain_id: str = "") -> tuple[list[dict], list[dict]]:
        """V8 新增：文档视角图谱 — 节点=文档，边=共享实体数。

        对齐核心理念：让用户看到文档之间通过共享实体形成的关联网络。
        """
        # 收集域内文档
        domain_docs: set[str] = set()
        for name, info in self._nodes.items():
            nd = info.get("domain_id", "")
            if not domain_id or nd == domain_id or nd.startswith(domain_id + "/"):
                for doc_id in info.get("doc_ids", []):
                    domain_docs.add(doc_id)

        if not domain_docs:
            return [], []

        # 构建文档节点
        nodes = []
        for doc_id in domain_docs:
            entities = self._doc_entities.get(doc_id, [])
            nodes.append({
                "id": doc_id,
                "label": doc_id,  # 前端可替换为文档标题
                "entity_count": len(entities),
                "domain_id": domain_id,
            })

        # 计算文档间共享实体
        doc_list = list(domain_docs)
        edges = []
        for i in range(len(doc_list)):
            for j in range(i + 1, len(doc_list)):
                doc_a, doc_b = doc_list[i], doc_list[j]
                ents_a = set(self._doc_entities.get(doc_a, []))
                ents_b = set(self._doc_entities.get(doc_b, []))
                shared = ents_a & ents_b
                if shared:
                    edges.append({
                        "source": doc_a,
                        "target": doc_b,
                        "shared_entities": list(shared),
                        "weight": len(shared),
                    })

        return nodes, edges

    # ── 图谱路径计算 ───────────────────────────────────────

    async def shortest_path_length(
        self, entity_a: str, entity_b: str, max_hops: int = 4
    ) -> int | None:
        """计算两个实体之间的最短路径长度。"""
        a = self._normalize_entity_name(entity_a)
        b = self._normalize_entity_name(entity_b)

        if self._use_memory:
            return self._memory_bfs(a, b, max_hops)

        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH p = shortestPath((a {name: $src})-[*..4]-(b {name: $tgt}))
                RETURN length(p) AS dist
                """,
                src=a,
                tgt=b,
            )
            record = await result.single()
            return record["dist"] if record else None

    def _memory_bfs(self, start: str, end: str, max_hops: int) -> int | None:
        """内存图谱的 BFS 最短路径。"""
        if start == end:
            return 0
        adj: dict[str, set[str]] = {}
        for edge in self._edges:
            s, t = edge["source"], edge["target"]
            adj.setdefault(s, set()).add(t)
            adj.setdefault(t, set()).add(s)

        visited = {start}
        queue = [(start, 0)]
        while queue:
            node, depth = queue.pop(0)
            if depth >= max_hops:
                continue
            for neighbor in adj.get(node, []):
                if neighbor == end:
                    return depth + 1
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, depth + 1))
        return None

    async def _get_neo4j_neighbors(self, entity_name: str) -> list[str]:
        """获取 Neo4j 中实体的一跳邻居。"""
        if not self._driver:
            return []
        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (e {name: $name})-[:RELATES]-(n) RETURN n.name LIMIT 20",
                name=entity_name,
            )
            return [r["n.name"] async for r in result]

    # ── 统计与管理 ──────────────────────────────────────────

    @property
    def node_count(self) -> int:
        if self._use_memory:
            return len(self._nodes)
        return self._neo4j_node_count

    @property
    def edge_count(self) -> int:
        if self._use_memory:
            return len(self._edges)
        return self._neo4j_edge_count

    _neo4j_node_count: int = 0
    _neo4j_edge_count: int = 0

    async def refresh_counts(self) -> None:
        """从 Neo4j 刷新计数。"""
        if self._use_memory or not self._driver:
            return
        try:
            async with self._driver.session() as session:
                result = await session.run("MATCH (n) RETURN count(n) AS cnt")
                record = await result.single()
                self._neo4j_node_count = record["cnt"] if record else 0

                result = await session.run("MATCH ()-[r]->() RETURN count(r) AS cnt")
                record = await result.single()
                self._neo4j_edge_count = record["cnt"] if record else 0
        except Exception as e:
            log.warning("graph_count_refresh_failed", error=str(e))

    async def clear_all(self) -> None:
        """清除所有图谱数据。"""
        if self._use_memory:
            self._nodes.clear()
            self._edges.clear()
            self._doc_entities.clear()
            self._entity_docs.clear()      # V8
            self._edge_index.clear()        # V8
            log.info("graph_store_cleared_memory_v8")
            return
        if self._driver:
            async with self._driver.session() as session:
                await session.run("MATCH (n) DETACH DELETE n")
            log.info("graph_store_cleared_neo4j")

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()


def _safe_label(label: str) -> str:
    """将中文类型名转换为安全的 Neo4j 标签。V8: 扩展8种类型。"""
    mapping = {
        "人物": "Person",
        "部门": "Department",
        "项目": "Project",
        "制度": "Regulation",
        "产品": "Product",
        "流程": "Process",
        # V8 新增类型
        "设备装置": "Equipment",
        "制度法规": "Regulation",
        "流程工艺": "Process",
        "物料化学品": "Material",
        "标准规范": "Standard",
        "位置区域": "Location",
    }
    return mapping.get(label, "Entity")
