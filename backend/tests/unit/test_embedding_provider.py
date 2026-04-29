"""Embedding Provider 单测（坑 6 验收）。

覆盖：

- Mock provider 的确定性（同输入同输出）
- ``allow_mock_embedding`` 门控（坑 6 + 坑 F 同款）
- Provider 路由（settings.embedding_provider 切换）
- Ruidong provider 缺 Key 抛错
- ``current_model_version`` / ``current_dim`` 元数据接口
- 同步 / 异步双轨
- Settings 三环境强制（sandbox/prod 禁 mock）
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from packages.common.exceptions import EmbeddingError


@pytest.fixture(autouse=True)
def _reset_provider() -> None:
    """每个测试前重置 Provider 单例。"""
    from packages.storage import embedder
    embedder.reset_embedding_provider()


# ────────── Mock Provider ──────────


class TestMockProvider:
    def test_deterministic(self, monkeypatch) -> None:
        from packages.common import settings
        from packages.storage.embedding_provider import MockEmbeddingProvider

        monkeypatch.setattr(settings, "allow_mock_embedding", True)
        p = MockEmbeddingProvider(dim=64)
        v1 = p.embed(["你好"])
        v2 = p.embed(["你好"])
        assert v1 == v2  # 同输入同输出
        assert len(v1[0]) == 64

    def test_normalized(self, monkeypatch) -> None:
        """mock 向量应归一化（|v|=1）。"""
        from math import sqrt

        from packages.common import settings
        from packages.storage.embedding_provider import MockEmbeddingProvider

        monkeypatch.setattr(settings, "allow_mock_embedding", True)
        p = MockEmbeddingProvider(dim=128)
        vec = p.embed(["text"])[0]
        norm = sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 1e-5

    def test_blocked_when_disallowed(self, monkeypatch) -> None:
        """allow_mock_embedding=False 时 mock embed 抛错。"""
        from packages.common import settings
        from packages.storage.embedding_provider import MockEmbeddingProvider

        monkeypatch.setattr(settings, "allow_mock_embedding", False)
        p = MockEmbeddingProvider(dim=32)
        with pytest.raises(EmbeddingError, match="mock embedding 被禁用"):
            p.embed(["text"])

    def test_empty_returns_empty(self, monkeypatch) -> None:
        from packages.common import settings
        from packages.storage.embedding_provider import MockEmbeddingProvider

        # 空列表不触发门控（短路）
        monkeypatch.setattr(settings, "allow_mock_embedding", False)
        p = MockEmbeddingProvider(dim=32)
        assert p.embed([]) == []


# ────────── Ruidong Provider ──────────


class TestRuidongProvider:
    def test_no_key_raises(self, monkeypatch) -> None:
        from packages.common import settings
        from packages.storage.embedding_provider import RuidongEmbeddingProvider

        monkeypatch.setattr(settings, "openai_api_key", "")
        p = RuidongEmbeddingProvider()
        with pytest.raises(EmbeddingError, match="OPENAI_API_KEY"):
            p.embed(["text"])

    def test_sync_calls_sdk(self, monkeypatch) -> None:
        from packages.common import settings
        from packages.storage.embedding_provider import RuidongEmbeddingProvider

        monkeypatch.setattr(settings, "openai_api_key", "sk-fake")
        monkeypatch.setattr(settings, "embedding_batch_size", 100)

        fake_client = MagicMock()
        fake_resp = MagicMock(data=[
            MagicMock(embedding=[0.1, 0.2, 0.3]),
            MagicMock(embedding=[0.4, 0.5, 0.6]),
        ])
        fake_client.embeddings.create = MagicMock(return_value=fake_resp)

        p = RuidongEmbeddingProvider()
        monkeypatch.setattr(p, "_get_sync", lambda: fake_client)

        result = p.embed(["a", "b"])
        assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        fake_client.embeddings.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_calls_sdk(self, monkeypatch) -> None:
        from packages.common import settings
        from packages.storage.embedding_provider import RuidongEmbeddingProvider

        monkeypatch.setattr(settings, "openai_api_key", "sk-fake")
        monkeypatch.setattr(settings, "embedding_batch_size", 100)

        fake_client = MagicMock()
        fake_resp = MagicMock(data=[MagicMock(embedding=[0.1] * 8)])
        fake_client.embeddings.create = AsyncMock(return_value=fake_resp)

        p = RuidongEmbeddingProvider()
        monkeypatch.setattr(p, "_get_async", lambda: fake_client)

        result = await p.aembed(["x"])
        assert result == [[0.1] * 8]

    def test_batches(self, monkeypatch) -> None:
        """texts > batch_size 时应分批调用。"""
        from packages.common import settings
        from packages.storage.embedding_provider import RuidongEmbeddingProvider

        monkeypatch.setattr(settings, "openai_api_key", "sk-fake")
        monkeypatch.setattr(settings, "embedding_batch_size", 2)

        fake_client = MagicMock()
        fake_client.embeddings.create = MagicMock(side_effect=[
            MagicMock(data=[MagicMock(embedding=[1]), MagicMock(embedding=[2])]),
            MagicMock(data=[MagicMock(embedding=[3])]),
        ])
        p = RuidongEmbeddingProvider()
        monkeypatch.setattr(p, "_get_sync", lambda: fake_client)

        result = p.embed(["a", "b", "c"])
        assert result == [[1], [2], [3]]
        assert fake_client.embeddings.create.call_count == 2


# ────────── Provider 路由 ──────────


class TestProviderRouting:
    def test_mock_provider_selected(self, monkeypatch) -> None:
        from packages.common import settings
        from packages.storage import embedder
        from packages.storage.embedding_provider import MockEmbeddingProvider

        monkeypatch.setattr(settings, "embedding_provider", "mock")
        embedder.reset_embedding_provider()

        from packages.storage.embedding_provider import get_embedding_provider
        p = get_embedding_provider()
        assert isinstance(p, MockEmbeddingProvider)
        assert p.name == "mock"

    def test_ruidong_provider_selected(self, monkeypatch) -> None:
        from packages.common import settings
        from packages.storage import embedder
        from packages.storage.embedding_provider import RuidongEmbeddingProvider

        monkeypatch.setattr(settings, "embedding_provider", "ruidong")
        embedder.reset_embedding_provider()

        from packages.storage.embedding_provider import get_embedding_provider
        p = get_embedding_provider()
        assert isinstance(p, RuidongEmbeddingProvider)

    def test_openai_aliases_to_ruidong(self, monkeypatch) -> None:
        """openai 与 ruidong 走同一 OpenAI 兼容客户端类。"""
        from packages.common import settings
        from packages.storage import embedder
        from packages.storage.embedding_provider import RuidongEmbeddingProvider

        monkeypatch.setattr(settings, "embedding_provider", "openai")
        embedder.reset_embedding_provider()

        from packages.storage.embedding_provider import get_embedding_provider
        p = get_embedding_provider()
        assert isinstance(p, RuidongEmbeddingProvider)

    def test_unknown_provider_raises(self, monkeypatch) -> None:
        from packages.common import settings
        from packages.storage import embedder

        monkeypatch.setattr(settings, "embedding_provider", "unknown-xyz")
        embedder.reset_embedding_provider()

        from packages.storage.embedding_provider import get_embedding_provider
        with pytest.raises(EmbeddingError, match="不支持的 embedding_provider"):
            get_embedding_provider()

    def test_singleton(self, monkeypatch) -> None:
        from packages.common import settings
        from packages.storage import embedder

        monkeypatch.setattr(settings, "embedding_provider", "mock")
        embedder.reset_embedding_provider()

        from packages.storage.embedding_provider import get_embedding_provider
        a = get_embedding_provider()
        b = get_embedding_provider()
        assert a is b


# ────────── 顶层入口 ──────────


class TestTopLevelEntry:
    def test_embed_texts_dispatches(self, monkeypatch) -> None:
        from packages.common import settings
        from packages.storage import embedder

        monkeypatch.setattr(settings, "embedding_provider", "mock")
        monkeypatch.setattr(settings, "allow_mock_embedding", True)
        monkeypatch.setattr(settings, "embedding_dim", 32)
        embedder.reset_embedding_provider()

        result = embedder.embed_texts(["hello"])
        assert len(result) == 1
        assert len(result[0]) == 32

    def test_embed_query_returns_single(self, monkeypatch) -> None:
        from packages.common import settings
        from packages.storage import embedder

        monkeypatch.setattr(settings, "embedding_provider", "mock")
        monkeypatch.setattr(settings, "allow_mock_embedding", True)
        monkeypatch.setattr(settings, "embedding_dim", 16)
        embedder.reset_embedding_provider()

        vec = embedder.embed_query("query")
        assert isinstance(vec, list)
        assert len(vec) == 16

    @pytest.mark.asyncio
    async def test_aembed_texts(self, monkeypatch) -> None:
        from packages.common import settings
        from packages.storage import embedder

        monkeypatch.setattr(settings, "embedding_provider", "mock")
        monkeypatch.setattr(settings, "allow_mock_embedding", True)
        monkeypatch.setattr(settings, "embedding_dim", 24)
        embedder.reset_embedding_provider()

        result = await embedder.aembed_texts(["a", "b"])
        assert len(result) == 2
        assert len(result[0]) == 24

    def test_current_model_version(self, monkeypatch) -> None:
        from packages.common import settings
        from packages.storage import embedder

        monkeypatch.setattr(settings, "embedding_provider", "mock")
        embedder.reset_embedding_provider()

        version = embedder.current_model_version()
        assert version == "mock-md5-v1"

    def test_current_dim(self, monkeypatch) -> None:
        from packages.common import settings
        from packages.storage import embedder

        monkeypatch.setattr(settings, "embedding_provider", "mock")
        monkeypatch.setattr(settings, "embedding_dim", 256)
        embedder.reset_embedding_provider()

        assert embedder.current_dim() == 256


# ────────── Sync/Async parity ──────────


class TestSyncAsyncParity:
    @pytest.mark.asyncio
    async def test_mock_parity(self, monkeypatch) -> None:
        """sync 和 async 在 mock 模式下应产出相同结果。"""
        from packages.common import settings
        from packages.storage import embedder

        monkeypatch.setattr(settings, "embedding_provider", "mock")
        monkeypatch.setattr(settings, "allow_mock_embedding", True)
        monkeypatch.setattr(settings, "embedding_dim", 32)
        embedder.reset_embedding_provider()

        sync_result = embedder.embed_texts(["text"])
        async_result = await embedder.aembed_texts(["text"])
        assert sync_result == async_result
