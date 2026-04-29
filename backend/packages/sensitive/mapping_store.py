"""敏感映射加密 KV 存储（决策书 §5.4 D11）。

存储 ``mapping_id → original_text`` 加密映射，支持反向解码（高密级用户访问原文时）。

实现：
- AES-256-GCM 加密（cryptography 库标准方案）
- Redis 持久化（独立 Redis URL，与 KAP 自身 Redis 解耦）
- dev 环境无 redis_url + 无 aes_key → 内存模式（fallback，仅供单测）

约束（feedback memory · ISS 零侵入 + KAP 轻量化）：
- 不引入 HSM（M3 才考虑），M1 用 ``settings.sensitive_aes_key``（环境变量注入）
- sandbox/prod 强制非空 aes_key（决策书 §8.3 / 全局规约 MUST NOT-2）
- 每次解码写审计日志（决策书 §5.4 "映射表的每次读取都写审计日志"）
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from packages.common import get_logger, settings

log = get_logger("sensitive.mapping_store")


class MappingStoreError(Exception):
    """映射存储读写 / 加解密失败。"""


def _load_aes_key() -> bytes | None:
    """从配置加载 AES-256 密钥（32 字节）。

    支持 hex (64 字符) 或 base64 (44 字符含 padding) 编码。
    """
    raw = settings.sensitive_aes_key
    if not raw:
        return None
    raw = raw.strip()
    try:
        if len(raw) == 64:
            key = bytes.fromhex(raw)
        else:
            key = base64.b64decode(raw)
    except (ValueError, base64.binascii.Error) as e:
        raise MappingStoreError(f"sensitive_aes_key 解码失败 (需 hex64 或 base64): {e}") from e
    if len(key) != 32:
        raise MappingStoreError(f"AES-256 需 32 字节密钥，实际 {len(key)}")
    return key


class SensitiveMappingStore:
    """加密 KV 存储抽象。Redis 模式存盘，内存模式仅 dev 测试用。"""

    def __init__(
        self,
        *,
        redis_url: str = "",
        aes_key: bytes | None = None,
        key_prefix: str = "kap:sensitive:",
    ) -> None:
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._memory: dict[str, bytes] = {}
        self._redis = None

        # AES-GCM 单例（None 表示无加密 — 仅 dev 内存模式允许）
        if aes_key is not None:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            self._aesgcm = AESGCM(aes_key)
        else:
            self._aesgcm = None

    async def initialize(self) -> None:
        """连 Redis（如果配了 URL），否则走内存模式。"""
        if not self._redis_url:
            log.info("sensitive_mapping_memory_mode")
            return
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self._redis_url, decode_responses=False)
            await self._redis.ping()
            log.info("sensitive_mapping_redis_connected", url=self._redis_url)
        except Exception as e:
            raise MappingStoreError(f"Redis 连接失败: {e}") from e

    def _encrypt(self, plaintext: str) -> bytes:
        """AES-256-GCM 加密，返回 nonce(12B) + ciphertext+tag。"""
        if self._aesgcm is None:
            # 内存 fallback 直接存原文（仅 dev）
            return plaintext.encode("utf-8")
        nonce = os.urandom(12)
        ct = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return nonce + ct

    def _decrypt(self, blob: bytes) -> str:
        if self._aesgcm is None:
            return blob.decode("utf-8")
        if len(blob) < 13:
            raise MappingStoreError("密文格式错误")
        nonce, ct = blob[:12], blob[12:]
        plain = self._aesgcm.decrypt(nonce, ct, None)
        return plain.decode("utf-8")

    def _full_key(self, mapping_id: str) -> str:
        return f"{self._key_prefix}{mapping_id}"

    async def put(self, mapping_id: str, original: str, meta: dict[str, Any] | None = None) -> None:
        """存入映射（覆盖语义，跨文档同一 mapping_id 应当对应同一 original）。"""
        payload = json.dumps({"original": original, "meta": meta or {}}, ensure_ascii=False)
        blob = self._encrypt(payload)
        full_key = self._full_key(mapping_id)
        if self._redis is not None:
            await self._redis.set(full_key, blob)
        else:
            self._memory[full_key] = blob

    async def get(self, mapping_id: str) -> dict[str, Any] | None:
        """按 mapping_id 取出原文（解码路由 + 审计入口）。"""
        full_key = self._full_key(mapping_id)
        if self._redis is not None:
            blob = await self._redis.get(full_key)
        else:
            blob = self._memory.get(full_key)
        if blob is None:
            return None
        try:
            payload = self._decrypt(blob)
            data = json.loads(payload)
        except Exception as e:
            raise MappingStoreError(f"映射解码失败 {mapping_id}: {e}") from e
        log.info("sensitive_mapping_decoded", mapping_id=mapping_id)
        return data

    async def has(self, mapping_id: str) -> bool:
        full_key = self._full_key(mapping_id)
        if self._redis is not None:
            return bool(await self._redis.exists(full_key))
        return full_key in self._memory


# ════════════════════════════════════════════════════════════════════════
#  全局单例（懒加载，便于测试 monkeypatch settings）
# ════════════════════════════════════════════════════════════════════════

_global_store: SensitiveMappingStore | None = None


def get_mapping_store() -> SensitiveMappingStore:
    """懒加载单例。生产部署 lifespan 启动时调用 initialize()。"""
    global _global_store
    if _global_store is None:
        aes_key = _load_aes_key()
        # sandbox/prod 强制有 aes_key（决策书 §5.4 D11）
        if settings.kap_env in ("sandbox", "prod") and aes_key is None:
            raise MappingStoreError(
                f"sandbox/prod 环境必须配置 SENSITIVE_AES_KEY（kap_env={settings.kap_env}）"
            )
        _global_store = SensitiveMappingStore(
            redis_url=settings.sensitive_mapping_redis_url,
            aes_key=aes_key,
        )
    return _global_store


def reset_mapping_store_for_test() -> None:
    """测试用：清掉单例。"""
    global _global_store
    _global_store = None
