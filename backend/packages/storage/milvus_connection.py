"""Milvus 连接管理器（M0-tech-debt 坑 2 主要交付物）。

V15 实测的"连接断开 → 重连超时 → 整批回滚"问题，根因是直接用
``pymilvus.connections.connect()`` 没有任何健康检查 / 重连 / 熔断机制。

本模块封装：

- **连接生命周期**：lazy connect + alias 别名 + close
- **健康检查**：``utility.get_server_version()`` 探活（间隔 ``milvus_health_check_interval``）
- **自动重连**：检测到断连时尝试重连，指数退避
- **熔断**：连续失败 ≥ ``milvus_max_reconnect_attempts`` 抛 ``StorageError``
- **降级门控**：``settings.allow_memory_fallback`` 控制是否退化到内存（sandbox/prod 禁用）

使用：

```python
mgr = MilvusConnectionManager()
await mgr.initialize()                    # 启动连接
await mgr.ensure_healthy()                # 每次操作前调用
col = mgr.get_collection("knowledge_chunks")
col.search(...)
```
"""

from __future__ import annotations

import threading
import time

from packages.common import get_logger, settings
from packages.common.exceptions import StorageError

log = get_logger("storage.milvus_connection")


class MilvusConnectionManager:
    """Milvus 连接生命周期管理（线程安全）。

    设计为单例：进程内只有一个 alias 对应一个 Milvus 连接，
    所有 collection 共用此连接。

    Attributes:
        alias: pymilvus connection alias（默认 "default"）
        is_memory_mode: 当前是否退化到内存模式（仅 dev allow_memory_fallback=True 时为 True）
    """

    def __init__(self, alias: str | None = None) -> None:
        self.alias = alias or settings.milvus_alias
        self.is_memory_mode: bool = False
        self._connected: bool = False
        self._last_health_check: float = 0.0
        self._consecutive_failures: int = 0
        self._lock = threading.Lock()

    async def initialize(self) -> None:
        """启动连接。失败时按 ``allow_memory_fallback`` 决定是否降级。"""
        try:
            self._connect()
            self._verify()
            self._connected = True
            self._consecutive_failures = 0
            self._last_health_check = time.monotonic()
            log.info(
                "milvus_connected",
                alias=self.alias,
                host=settings.milvus_host,
                port=settings.milvus_port,
            )
        except Exception as e:  # noqa: BLE001
            self._handle_init_failure(e)

    def _connect(self) -> None:
        """实际建立连接（同步 pymilvus.connections）。"""
        from pymilvus import connections
        # 如果已存在连接，先断开避免脏状态
        try:
            connections.disconnect(self.alias)
        except Exception:  # noqa: BLE001
            pass
        connections.connect(
            alias=self.alias,
            host=settings.milvus_host,
            port=str(settings.milvus_port),
        )

    def _verify(self) -> str:
        """探活，返回服务端版本。失败抛异常。"""
        from pymilvus import utility
        version = utility.get_server_version(using=self.alias)
        return version

    def _handle_init_failure(self, err: Exception) -> None:
        """初始化失败处理：dev 允许降级 / sandbox/prod 直接抛错。"""
        if settings.allow_memory_fallback and settings.kap_env == "dev":
            log.warning(
                "milvus_unavailable_fallback_memory",
                alias=self.alias,
                error=str(err),
                kap_env=settings.kap_env,
            )
            self.is_memory_mode = True
            self._connected = False
            return
        raise StorageError(
            f"Milvus 连接失败（kap_env={settings.kap_env}, "
            f"allow_memory_fallback={settings.allow_memory_fallback}）："
            f"{err}。如需 dev 阶段降级到内存，设置 KAP_ALLOW_MEMORY_FALLBACK=true。"
        ) from err

    async def ensure_healthy(self) -> None:
        """探活 + 必要时重连。每次 search/insert 前调用。

        优化：``milvus_health_check_interval`` 内不重复探活，避免高频调用。
        """
        if self.is_memory_mode:
            return  # 内存模式跳过

        now = time.monotonic()
        if self._connected and (now - self._last_health_check) < settings.milvus_health_check_interval:
            return  # 还在健康窗口内，跳过

        with self._lock:
            # 双重检查（其他线程可能已经探活）
            if self._connected and (now - self._last_health_check) < settings.milvus_health_check_interval:
                return
            try:
                self._verify()
                self._consecutive_failures = 0
                self._last_health_check = now
                self._connected = True
                log.debug("milvus_health_ok", alias=self.alias)
            except Exception as e:  # noqa: BLE001
                self._connected = False
                log.warning("milvus_health_failed", alias=self.alias, error=str(e))
                self._reconnect_with_backoff()

    def _reconnect_with_backoff(self) -> None:
        """指数退避重连。失败次数累计；超过上限熔断。"""
        max_attempts = settings.milvus_max_reconnect_attempts
        base = settings.milvus_reconnect_backoff_base

        for attempt in range(1, max_attempts + 1):
            wait = base ** attempt  # 指数退避：1.5, 2.25, 3.375, ...
            log.info("milvus_reconnect_attempt", attempt=attempt, wait_seconds=wait)
            time.sleep(wait)
            try:
                self._connect()
                self._verify()
                self._connected = True
                self._consecutive_failures = 0
                self._last_health_check = time.monotonic()
                log.info("milvus_reconnect_ok", attempt=attempt)
                return
            except Exception as e:  # noqa: BLE001
                self._consecutive_failures += 1
                log.warning(
                    "milvus_reconnect_failed",
                    attempt=attempt,
                    error=str(e),
                    consecutive_failures=self._consecutive_failures,
                )

        # 所有重连失败 → 熔断
        raise StorageError(
            f"Milvus 重连 {max_attempts} 次全部失败。"
            f"累计连续失败 {self._consecutive_failures} 次。"
            f"请检查 Milvus 服务状态或网络连通性。"
        )

    def get_collection(self, name: str):
        """获取 Collection 对象（不在内存模式时）。"""
        if self.is_memory_mode:
            raise StorageError(
                f"内存模式下不应调用 get_collection({name})。"
                f"请检查 manager.is_memory_mode 后再决定路径。"
            )
        from pymilvus import Collection
        return Collection(name, using=self.alias)

    def has_collection(self, name: str) -> bool:
        """是否存在指定 collection。内存模式返回 False。"""
        if self.is_memory_mode:
            return False
        from pymilvus import utility
        return utility.has_collection(name, using=self.alias)

    def disconnect(self) -> None:
        """主动断开连接（用于测试 / shutdown）。"""
        if self._connected:
            try:
                from pymilvus import connections
                connections.disconnect(self.alias)
            except Exception:  # noqa: BLE001
                pass
            self._connected = False
        log.info("milvus_disconnected", alias=self.alias)


# ──────── 全局单例 ────────


_manager_singleton: MilvusConnectionManager | None = None


def get_connection_manager() -> MilvusConnectionManager:
    """返回全局单例 MilvusConnectionManager。"""
    global _manager_singleton
    if _manager_singleton is None:
        _manager_singleton = MilvusConnectionManager()
    return _manager_singleton


def reset_connection_manager() -> None:
    """重置单例（测试用）。"""
    global _manager_singleton
    if _manager_singleton is not None:
        _manager_singleton.disconnect()
    _manager_singleton = None
