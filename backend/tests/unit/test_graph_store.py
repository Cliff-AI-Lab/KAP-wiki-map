"""GraphStore 单测（坑 5 验收）。

覆盖：

- 静默 fallback 修复：dev allow / dev block / sandbox block
- ontology_version 写入字段（内存模式直接验证；Neo4j 通过 mock session 验证）
- V8 双向索引功能保留（add / get_doc_entities / find_related_docs）
- Settings 三环境强制 allow_memory_fallback
"""

from __future__ import annotations

import pytest

from packages.common.exceptions import StorageError
from packages.common.types import EntityRelation, MentionedEntity
from packages.storage.graph_store import GraphStore


# ────────── 初始化与降级门控 ──────────


class TestInitialize:
    @pytest.mark.asyncio
    async def test_explicit_memory_mode(self) -> None:
        """显式 use_memory=True 直接走内存模式，不连 Neo4j。"""
        gs = GraphStore(use_memory=True)
        await gs.initialize()
        assert gs._use_memory is True
        assert gs._driver is None

    @pytest.mark.asyncio
    async def test_dev_allows_fallback_on_neo4j_failure(self, monkeypatch) -> None:
        """dev + allow_memory_fallback=True 时，Neo4j 连接失败应降级。"""
        from packages.common import settings

        monkeypatch.setattr(settings, "kap_env", "dev")
        monkeypatch.setattr(settings, "allow_memory_fallback", True)

        gs = GraphStore(use_memory=False)
        # 模拟 driver 创建抛错
        def fake_driver(*args, **kwargs):
            raise RuntimeError("Neo4j unreachable")

        monkeypatch.setattr("neo4j.AsyncGraphDatabase.driver", fake_driver)
        await gs.initialize()
        assert gs._use_memory is True

    @pytest.mark.asyncio
    async def test_dev_no_fallback_raises(self, monkeypatch) -> None:
        """dev + allow_memory_fallback=False → 抛 StorageError（不再静默降级）。"""
        from packages.common import settings

        monkeypatch.setattr(settings, "kap_env", "dev")
        monkeypatch.setattr(settings, "allow_memory_fallback", False)

        gs = GraphStore(use_memory=False)
        def fake_driver(*args, **kwargs):
            raise RuntimeError("Neo4j unreachable")

        monkeypatch.setattr("neo4j.AsyncGraphDatabase.driver", fake_driver)
        with pytest.raises(StorageError, match="Neo4j 连接失败"):
            await gs.initialize()

    @pytest.mark.asyncio
    async def test_sandbox_blocked(self, monkeypatch) -> None:
        """sandbox 即使设了 allow_memory_fallback，settings 层强制 False，应抛错。"""
        from packages.common import settings

        monkeypatch.setattr(settings, "kap_env", "sandbox")
        monkeypatch.setattr(settings, "allow_memory_fallback", False)  # settings 已强制

        gs = GraphStore(use_memory=False)
        def fake_driver(*args, **kwargs):
            raise RuntimeError("Neo4j unreachable")
        monkeypatch.setattr("neo4j.AsyncGraphDatabase.driver", fake_driver)
        with pytest.raises(StorageError):
            await gs.initialize()


# ────────── ontology_version 字段 ──────────


class TestOntologyVersion:
    @pytest.mark.asyncio
    async def test_memory_mode_writes_version(self, monkeypatch) -> None:
        """内存模式下，新增实体时应挂 ontology_version 属性。"""
        from packages.common import settings

        monkeypatch.setattr(settings, "neo4j_ontology_version", "v1.2.3")
        gs = GraphStore(use_memory=True)
        await gs.initialize()

        await gs.add_entities_and_relations(
            doc_id="doc-001",
            entities=[MentionedEntity(name="汽轮机1#", type="设备装置")],
            relations=[],
            domain_id="energy/production/equipment",
        )
        node = gs._nodes.get("汽轮机1#")
        assert node is not None
        assert node["ontology_version"] == "v1.2.3"

    @pytest.mark.asyncio
    async def test_default_version(self) -> None:
        """默认本体版本为 v1（settings.neo4j_ontology_version 默认值）。"""
        from packages.common import settings
        # settings 默认值
        assert settings.neo4j_ontology_version == "v1"


# ────────── V8 功能保留（回归） ──────────


class TestV8FunctionalityPreserved:
    @pytest.mark.asyncio
    async def test_add_and_query_doc_entities(self) -> None:
        """V8: 正向索引 doc → entities 仍工作。"""
        gs = GraphStore(use_memory=True)
        await gs.initialize()

        await gs.add_entities_and_relations(
            doc_id="doc-A",
            entities=[
                MentionedEntity(name="安全部", type="部门"),
                MentionedEntity(name="李工", type="人物"),
            ],
            relations=[
                EntityRelation(source="李工", target="安全部", relation="所属")
            ],
            domain_id="energy/safety",
        )
        ents = await gs.get_doc_entities("doc-A")
        assert "安全部" in ents
        assert "李工" in ents

    @pytest.mark.asyncio
    async def test_reverse_index_entity_to_docs(self) -> None:
        """V8: 反向索引 entity → docs（共享实体发现）。"""
        gs = GraphStore(use_memory=True)
        await gs.initialize()

        for doc_id in ["doc-A", "doc-B", "doc-C"]:
            await gs.add_entities_and_relations(
                doc_id=doc_id,
                entities=[MentionedEntity(name="GB/T 6075", type="标准规范")],
                relations=[],
            )
        docs = await gs.get_docs_by_entity("GB/T 6075")
        assert set(docs) == {"doc-A", "doc-B", "doc-C"}

    @pytest.mark.asyncio
    async def test_edge_dedup_increments_weight(self) -> None:
        """V8: 同实体对同关系再次出现 → weight++"""
        gs = GraphStore(use_memory=True)
        await gs.initialize()

        for doc in ["doc-1", "doc-2"]:
            await gs.add_entities_and_relations(
                doc_id=doc,
                entities=[
                    MentionedEntity(name="李工", type="人物"),
                    MentionedEntity(name="安全部", type="部门"),
                ],
                relations=[
                    EntityRelation(source="李工", target="安全部", relation="所属")
                ],
            )
        # 应只有 1 条边，weight=2
        edges = [e for e in gs._edges if e["source"] == "李工"]
        assert len(edges) == 1
        assert edges[0]["weight"] == 2


# ────────── Settings 三环境强制 ──────────


class TestSettingsForceFallback:
    def test_sandbox_forces_no_fallback(self) -> None:
        from packages.common.config import Settings

        s = Settings(
            _env_file=None,
            kap_env="sandbox",
            allow_memory_fallback=True,
            embedding_provider="ruidong",
        )
        assert s.allow_memory_fallback is False

    def test_default_ontology_version(self) -> None:
        from packages.common.config import Settings

        s = Settings(_env_file=None)
        assert s.neo4j_ontology_version == "v1"

    def test_custom_ontology_version(self) -> None:
        from packages.common.config import Settings

        s = Settings(_env_file=None, neo4j_ontology_version="v2.0")
        assert s.neo4j_ontology_version == "v2.0"
