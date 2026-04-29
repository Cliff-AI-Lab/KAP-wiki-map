"""MilvusConnectionManager 单测（坑 2 验收）。

覆盖：

- 初始化失败 + 降级门控（dev 允许 / sandbox/prod 抛 StorageError）
- 健康检查间隔（短期内不重复探活）
- 重连指数退避 + 熔断（连续失败上限）
- is_memory_mode 状态
- 单例 + reset

注：不连真实 Milvus，全部用 monkeypatch 模拟 pymilvus 行为。
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from packages.common.exceptions import StorageError


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    from packages.storage import milvus_connection
    milvus_connection._manager_singleton = None


# ────────── 初始化与降级门控 ──────────


class TestInitialize:
    @pytest.mark.asyncio
    async def test_dev_allows_fallback(self, monkeypatch) -> None:
        """dev + allow_memory_fallback=True 时，连接失败应降级为内存模式。"""
        from packages.common import settings
        from packages.storage.milvus_connection import MilvusConnectionManager

        monkeypatch.setattr(settings, "kap_env", "dev")
        monkeypatch.setattr(settings, "allow_memory_fallback", True)

        mgr = MilvusConnectionManager()
        # 模拟 _connect 抛错
        monkeypatch.setattr(mgr, "_connect", lambda: (_ for _ in ()).throw(RuntimeError("Milvus down")))

        await mgr.initialize()
        assert mgr.is_memory_mode is True

    @pytest.mark.asyncio
    async def test_dev_no_fallback_raises(self, monkeypatch) -> None:
        """dev + allow_memory_fallback=False → 抛 StorageError。"""
        from packages.common import settings
        from packages.storage.milvus_connection import MilvusConnectionManager

        monkeypatch.setattr(settings, "kap_env", "dev")
        monkeypatch.setattr(settings, "allow_memory_fallback", False)

        mgr = MilvusConnectionManager()
        monkeypatch.setattr(mgr, "_connect", lambda: (_ for _ in ()).throw(RuntimeError("Milvus down")))

        with pytest.raises(StorageError, match="Milvus 连接失败"):
            await mgr.initialize()

    @pytest.mark.asyncio
    async def test_sandbox_blocked_even_with_fallback(self, monkeypatch) -> None:
        """sandbox 即使设了 allow_memory_fallback=True，仍应被强制 False（settings 层）。

        本测试验证 manager 在 sandbox 不会降级（行为靠 settings 防线）。
        """
        from packages.common import settings
        from packages.storage.milvus_connection import MilvusConnectionManager

        # 模拟 settings 已被 model_post_init 强制 False
        monkeypatch.setattr(settings, "kap_env", "sandbox")
        monkeypatch.setattr(settings, "allow_memory_fallback", False)

        mgr = MilvusConnectionManager()
        monkeypatch.setattr(mgr, "_connect", lambda: (_ for _ in ()).throw(RuntimeError("Milvus down")))

        with pytest.raises(StorageError):
            await mgr.initialize()

    @pytest.mark.asyncio
    async def test_successful_init(self, monkeypatch) -> None:
        from packages.storage.milvus_connection import MilvusConnectionManager

        mgr = MilvusConnectionManager()
        monkeypatch.setattr(mgr, "_connect", lambda: None)
        monkeypatch.setattr(mgr, "_verify", lambda: "v2.4.17")

        await mgr.initialize()
        assert mgr._connected is True
        assert mgr.is_memory_mode is False
        assert mgr._consecutive_failures == 0


# ────────── 健康检查间隔 ──────────


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_skip_within_interval(self, monkeypatch) -> None:
        """同一 interval 内不重复探活。"""
        from packages.common import settings
        from packages.storage.milvus_connection import MilvusConnectionManager

        monkeypatch.setattr(settings, "milvus_health_check_interval", 60.0)

        mgr = MilvusConnectionManager()
        verify_calls = []
        monkeypatch.setattr(mgr, "_connect", lambda: None)
        monkeypatch.setattr(mgr, "_verify", lambda: verify_calls.append(1) or "v2.4.17")

        await mgr.initialize()  # 第一次 verify
        assert len(verify_calls) == 1

        # 立即再调 ensure_healthy 应跳过（在 interval 内）
        await mgr.ensure_healthy()
        assert len(verify_calls) == 1  # 不变

    @pytest.mark.asyncio
    async def test_skip_in_memory_mode(self, monkeypatch) -> None:
        """内存模式下 ensure_healthy 应短路返回。"""
        from packages.storage.milvus_connection import MilvusConnectionManager

        mgr = MilvusConnectionManager()
        mgr.is_memory_mode = True
        # 不设置任何 _verify mock，若被调用会抛错
        await mgr.ensure_healthy()  # 应静默跳过


# ────────── 重连熔断 ──────────


class TestReconnectAndCircuitBreaker:
    @pytest.mark.asyncio
    async def test_reconnect_after_failure(self, monkeypatch) -> None:
        """探活失败 → 触发重连。"""
        from packages.common import settings
        from packages.storage.milvus_connection import MilvusConnectionManager

        monkeypatch.setattr(settings, "milvus_health_check_interval", 0.0)
        monkeypatch.setattr(settings, "milvus_max_reconnect_attempts", 2)
        monkeypatch.setattr(settings, "milvus_reconnect_backoff_base", 1.001)  # 几乎不等

        mgr = MilvusConnectionManager()
        connect_calls = []
        verify_calls = [0]

        def fake_connect():
            connect_calls.append(1)

        def fake_verify():
            verify_calls[0] += 1
            # 第二次（重连阶段第一次）verify 成功
            if verify_calls[0] == 1:
                raise RuntimeError("dropped")  # 触发重连
            return "v2.4.17"

        monkeypatch.setattr(mgr, "_connect", fake_connect)
        monkeypatch.setattr(mgr, "_verify", fake_verify)
        # initialize 跳过 verify 失败的处理（直接进入 connected 状态以测试 ensure_healthy）
        mgr._connected = True
        mgr._last_health_check = 0.0
        # 减少等待时间
        monkeypatch.setattr("time.sleep", lambda s: None)

        await mgr.ensure_healthy()
        assert mgr._connected is True

    @pytest.mark.asyncio
    async def test_circuit_breaker_after_max_attempts(self, monkeypatch) -> None:
        """连续重连失败 ≥ max → 抛 StorageError。"""
        from packages.common import settings
        from packages.storage.milvus_connection import MilvusConnectionManager

        monkeypatch.setattr(settings, "milvus_health_check_interval", 0.0)
        monkeypatch.setattr(settings, "milvus_max_reconnect_attempts", 2)

        mgr = MilvusConnectionManager()

        def always_fail():
            raise RuntimeError("永远连不上")

        monkeypatch.setattr(mgr, "_connect", always_fail)
        monkeypatch.setattr(mgr, "_verify", always_fail)
        mgr._connected = True
        mgr._last_health_check = 0.0
        monkeypatch.setattr("time.sleep", lambda s: None)

        with pytest.raises(StorageError, match="重连"):
            await mgr.ensure_healthy()

        assert mgr._consecutive_failures >= 2


# ────────── 单例 ──────────


class TestSingleton:
    def test_get_manager_returns_same_instance(self) -> None:
        from packages.storage.milvus_connection import (
            get_connection_manager,
            reset_connection_manager,
        )
        reset_connection_manager()
        a = get_connection_manager()
        b = get_connection_manager()
        assert a is b

    def test_reset_creates_new(self) -> None:
        from packages.storage.milvus_connection import (
            get_connection_manager,
            reset_connection_manager,
        )
        a = get_connection_manager()
        reset_connection_manager()
        b = get_connection_manager()
        assert a is not b


# ────────── Settings 三环境强制 ──────────


class TestSettingsForceFallback:
    def test_sandbox_forces_no_fallback(self) -> None:
        from packages.common.config import Settings

        s = Settings(
            _env_file=None,
            kap_env="sandbox",
            allow_memory_fallback=True,  # 用户尝试启用
            embedding_provider="ruidong",  # 满足 embedding 校验
        )
        assert s.allow_memory_fallback is False  # 被强制覆盖

    def test_prod_forces_no_fallback(self) -> None:
        from packages.common.config import Settings

        s = Settings(
            _env_file=None,
            kap_env="prod",
            allow_memory_fallback=True,
            embedding_provider="ruidong",
        )
        assert s.allow_memory_fallback is False
