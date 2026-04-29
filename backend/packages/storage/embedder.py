"""Embedding 顶层入口（M0-tech-debt 坑 6 改造）。

把原硬编码的 OpenAI / mock 二选一逻辑剥离到 ``embedding_provider.py``，
本模块只保留薄包装，路由到 ``EmbeddingProvider`` 单例。

入口：

- ``embed_texts(texts)`` / ``embed_query(text)``：同步入口（M0 兼容）
- ``aembed_texts(texts)`` / ``aembed_query(text)``：**异步入口**（坑 6 主要交付物）
- ``current_model_version()``：返回当前 provider 的模型版本，写入 Milvus metadata 用

兼容期：原 ``embed_texts`` / ``embed_query`` 调用方可继续使用，
内部已切到新 Provider；待全部迁移到 async 后 M1 删除同步版本。
"""

from __future__ import annotations

from packages.common import get_logger
from packages.common.exceptions import EmbeddingError
from packages.storage.embedding_provider import (
    EmbeddingProvider,
    get_embedding_provider,
    reset_embedding_provider,
)

log = get_logger("storage.embedder")


def current_model_version() -> str:
    """当前 provider 的模型版本标识。写入 Milvus chunk metadata，模型升级后增量重嵌入用。"""
    return get_embedding_provider().model_version


def current_dim() -> int:
    """当前 provider 的向量维度。"""
    return get_embedding_provider().dim


# ── 同步入口（M0 兼容期）────────────


def embed_texts(texts: list[str]) -> list[list[float]]:
    """将文本列表转换为向量（同步）。"""
    if not texts:
        return []
    return get_embedding_provider().embed(texts)


def embed_query(text: str) -> list[float]:
    """将单条查询文本转换为向量（同步）。"""
    return embed_texts([text])[0]


# ── 异步入口（坑 6 主要交付物）────────────


async def aembed_texts(texts: list[str]) -> list[list[float]]:
    """将文本列表转换为向量（**异步**）。

    Ruidong provider 走真异步（AsyncOpenAI），不阻塞 event loop；
    BGE local / Mock 默认用 ``asyncio.to_thread`` 包装。
    """
    if not texts:
        return []
    return await get_embedding_provider().aembed(texts)


async def aembed_query(text: str) -> list[float]:
    """将单条查询文本转换为向量（**异步**）。"""
    out = await aembed_texts([text])
    return out[0]


__all__ = [
    "embed_texts",
    "embed_query",
    "aembed_texts",
    "aembed_query",
    "current_model_version",
    "current_dim",
    "reset_embedding_provider",
    "EmbeddingError",
]
