"""Embedding Provider 抽象与三实现（M0-tech-debt 坑 6 主要交付物）。

设计动机：原 ``embedder.py`` 只支持 OpenAI 和 mock，且静默 fallback；
本模块引入抽象层 + 三种实现，便于私有化场景灵活切换：

- **MockEmbeddingProvider**：哈希确定性伪向量（仅 dev 测试用）
- **RuidongEmbeddingProvider**：通过睿动 OpenAI 兼容接口（``qwen3-embedding`` 等）
- **BGELocalEmbeddingProvider**：本地 sentence-transformers（``BAAI/bge-large-zh-v1.5`` 等）

所有 Provider 都暴露：

- ``embed(texts) -> list[list[float]]``：同步入口
- ``aembed(texts) -> list[list[float]]``：异步入口（默认用 ``asyncio.to_thread`` 包装）
- ``model_version: str``：写入 Milvus metadata，便于模型升级后增量重嵌入

调用流：``settings.embedding_provider`` → ``get_embedding_provider()`` lazy 单例
→ ``provider.embed()`` / ``aembed()`` → 返回向量列表

关键约束（坑 6 + 坑 F 联动）：

- mock provider / API 失败 / 无 Key 时**不静默回落**，抛 ``EmbeddingError``
- ``settings.allow_mock_embedding`` 门控 mock 路径，sandbox/prod 强制禁用
- 写入 Milvus 时同时写 ``embedding_model_version`` 字段（升级 / 重嵌入用）
"""

from __future__ import annotations

import asyncio
import hashlib
from abc import ABC, abstractmethod
from typing import ClassVar

import numpy as np

from packages.common import get_logger, settings
from packages.common.exceptions import EmbeddingError

log = get_logger("storage.embedding_provider")


class EmbeddingProvider(ABC):
    """Embedding 提供方抽象基类。

    子类必须实现 ``embed``；``aembed`` 默认用 ``asyncio.to_thread`` 包装同步实现，
    需要真异步（如调睿动 AsyncOpenAI）的子类应 override。
    """

    name: ClassVar[str] = "abstract"
    model_version: ClassVar[str] = "unknown"
    dim: ClassVar[int] = 0

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """同步批量 embed。空列表必须返回空列表。"""

    async def aembed(self, texts: list[str]) -> list[list[float]]:
        """异步批量 embed。默认用 ``asyncio.to_thread`` 包装 ``embed``；
        真异步实现应 override。"""
        if not texts:
            return []
        return await asyncio.to_thread(self.embed, texts)


# ──────────── Mock ────────────


class MockEmbeddingProvider(EmbeddingProvider):
    """哈希确定性伪向量（仅 dev / 测试用）。

    M0-tech-debt 坑 6：sandbox/prod 由 ``Settings.model_post_init`` 强制禁用。
    伪向量保证同输入同输出（便于测试可复现），但**完全无语义区分能力**。
    """

    name = "mock"
    model_version = "mock-md5-v1"

    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not settings.allow_mock_embedding:
            raise EmbeddingError(
                f"mock embedding 被禁用（kap_env={settings.kap_env}, "
                f"allow_mock_embedding=False）。如需 dev 阶段使用，"
                f"设置 KAP_ALLOW_MOCK_EMBEDDING=true。"
            )
        out: list[list[float]] = []
        for text in texts:
            seed = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16) % (2**32)
            rng = np.random.RandomState(seed)
            vec = rng.randn(self.dim).astype(np.float32)
            vec = vec / np.linalg.norm(vec)
            out.append(vec.tolist())
        return out


# ──────────── Ruidong (OpenAI compat via 睿动)────────────


class RuidongEmbeddingProvider(EmbeddingProvider):
    """睿动网关 embedding（OpenAI 兼容接口，模型如 ``qwen3-embedding``）。

    - 同步路径用 ``OpenAI``，异步路径用 ``AsyncOpenAI``，分别懒加载单例
    - ``verify`` 由 ``settings.llm_verify_ssl`` 控制（与 LLM 客户端共享配置）
    - 批量分片：超过 ``settings.embedding_batch_size`` 自动分批
    """

    name = "ruidong"

    def __init__(self, model: str | None = None, dim: int | None = None) -> None:
        self.model_version = model or settings.embedding_model
        self.dim = dim or settings.embedding_dim
        self._sync_client = None
        self._async_client = None

    def _get_sync(self):
        if self._sync_client is None:
            from openai import OpenAI
            import httpx
            http_client = httpx.Client(verify=settings.llm_verify_ssl)
            self._sync_client = OpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                http_client=http_client,
            )
        return self._sync_client

    def _get_async(self):
        if self._async_client is None:
            from openai import AsyncOpenAI
            import httpx
            http_client = httpx.AsyncClient(verify=settings.llm_verify_ssl)
            self._async_client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                http_client=http_client,
            )
        return self._async_client

    @staticmethod
    def _check_key() -> None:
        if not settings.openai_api_key or not settings.openai_api_key.strip():
            raise EmbeddingError(
                "ruidong embedding 需要 OPENAI_API_KEY（睿动 Key）。"
                "请配置环境变量 OPENAI_API_KEY。"
            )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._check_key()
        client = self._get_sync()
        out: list[list[float]] = []
        batch = settings.embedding_batch_size
        for i in range(0, len(texts), batch):
            chunk = texts[i:i + batch]
            try:
                resp = client.embeddings.create(model=self.model_version, input=chunk)
            except Exception as e:
                raise EmbeddingError(f"ruidong embedding 调用失败: {e}") from e
            out.extend([item.embedding for item in resp.data])
        return out

    async def aembed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._check_key()
        client = self._get_async()
        out: list[list[float]] = []
        batch = settings.embedding_batch_size
        for i in range(0, len(texts), batch):
            chunk = texts[i:i + batch]
            try:
                resp = await client.embeddings.create(model=self.model_version, input=chunk)
            except Exception as e:
                raise EmbeddingError(f"ruidong embedding 异步调用失败: {e}") from e
            out.extend([item.embedding for item in resp.data])
        return out


# ──────────── BGE Local（懒加载 sentence-transformers）────────────


class BGELocalEmbeddingProvider(EmbeddingProvider):
    """本地 sentence-transformers BGE 系列。

    - 默认模型：``BAAI/bge-large-zh-v1.5``（dim=1024）
    - 懒加载：首次 ``embed`` 时下载/加载模型（大约 1GB）
    - 依赖 ``sentence-transformers``（pyproject ``[local-models]`` extra）
    """

    name = "bge"

    def __init__(self, model: str | None = None, dim: int | None = None) -> None:
        self.model_version = model or settings.embedding_model or "BAAI/bge-large-zh-v1.5"
        self.dim = dim or settings.embedding_dim or 1024
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise EmbeddingError(
                    f"BGE 本地 embedding 需要 sentence-transformers："
                    f"`pip install -e .[local-models]`。原始错误：{e}"
                ) from e
            log.info("bge_loading_model", model=self.model_version)
            self._model = SentenceTransformer(self.model_version)
            actual_dim = self._model.get_sentence_embedding_dimension()
            if actual_dim != self.dim:
                log.warning(
                    "bge_dim_mismatch",
                    configured=self.dim,
                    actual=actual_dim,
                )
                self.dim = actual_dim
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        try:
            arr = model.encode(
                texts,
                batch_size=settings.embedding_batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except Exception as e:
            raise EmbeddingError(f"BGE 本地 embedding 推理失败: {e}") from e
        return arr.tolist() if hasattr(arr, "tolist") else [list(v) for v in arr]


# ──────────── Provider 路由 ────────────


_provider_singleton: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """根据 ``settings.embedding_provider`` 返回单例 Provider。

    支持值：mock / openai / ruidong / bge。
    openai 走与 ruidong 相同的 OpenAI 兼容客户端（区别仅在 base_url 由 settings 控制）。
    """
    global _provider_singleton
    if _provider_singleton is not None:
        return _provider_singleton

    provider_name = settings.embedding_provider.strip().lower()
    if provider_name == "mock":
        _provider_singleton = MockEmbeddingProvider(dim=settings.embedding_dim)
    elif provider_name in ("ruidong", "openai"):
        _provider_singleton = RuidongEmbeddingProvider()
    elif provider_name == "bge":
        _provider_singleton = BGELocalEmbeddingProvider()
    else:
        raise EmbeddingError(
            f"不支持的 embedding_provider: {provider_name}。"
            f"合法值：mock / openai / ruidong / bge"
        )

    log.info(
        "embedding_provider_initialized",
        provider=_provider_singleton.name,
        model_version=_provider_singleton.model_version,
        dim=_provider_singleton.dim,
    )
    return _provider_singleton


def reset_embedding_provider() -> None:
    """重置 Provider 单例。配置热更新或测试间需要时调用。"""
    global _provider_singleton
    _provider_singleton = None
