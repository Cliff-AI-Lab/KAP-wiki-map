"""Embedding 模型封装 — 支持 OpenAI API 和本地简易模拟。"""

from __future__ import annotations

import hashlib

import numpy as np

from packages.common import get_logger, settings
from packages.common.exceptions import StorageError

log = get_logger("storage.embedder")

_openai_client = None


def _get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI

        _openai_client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
    return _openai_client


def embed_texts(texts: list[str]) -> list[list[float]]:
    """将文本列表转换为向量。"""
    if not texts:
        return []

    if settings.embedding_provider == "openai" and settings.openai_api_key and settings.openai_api_key != "sk-xxx":
        return _embed_openai(texts)
    else:
        log.debug("embedding_mock_mode", count=len(texts))
        return _embed_mock(texts)


def embed_query(text: str) -> list[float]:
    """将单条查询文本转换为向量。"""
    return embed_texts([text])[0]


def _embed_openai(texts: list[str]) -> list[list[float]]:
    """使用 OpenAI Embedding API。"""
    client = _get_openai()
    try:
        resp = client.embeddings.create(
            model=settings.embedding_model,
            input=texts,
        )
        return [item.embedding for item in resp.data]
    except Exception as e:
        log.warning("openai_embedding_failed_fallback_mock", error=str(e))
        return _embed_mock(texts)


def _embed_mock(texts: list[str]) -> list[list[float]]:
    """基于哈希的确定性伪向量 — 同样的文本总是得到同样的向量，保证检索可复现。"""
    dim = settings.embedding_dim
    embeddings = []
    for text in texts:
        seed = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16) % (2**32)
        rng = np.random.RandomState(seed)
        vec = rng.randn(dim).astype(np.float32)
        vec = vec / np.linalg.norm(vec)
        embeddings.append(vec.tolist())
    return embeddings
