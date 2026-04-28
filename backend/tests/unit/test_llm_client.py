"""LLM 客户端单测（坑 1 批 1 验收）。

覆盖：

- 同步 ``call_llm`` / ``call_llm_json`` 行为（M0 兼容入口保留）
- 异步 ``acall_llm`` / ``acall_llm_json`` 行为（坑 1 主要交付物）
- mock fallback 门控（坑 F）：``allow_mock_llm`` 三态
- 异步异常路径：API 失败 / JSON 解析失败 / 不支持 provider
- 异步单例懒加载

不覆盖（依赖真实网络的 case 由 integration 测试处理）：
- 真实 OpenAI / Anthropic API 调用
- httpx 重试与超时实测
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from packages.common.exceptions import LLMCallError


# ────────── mock 门控（坑 F）──────────


class TestMockGate:
    """``settings.allow_mock_llm`` 三态行为。"""

    def test_sync_mock_provider_blocked_when_disallowed(self, monkeypatch) -> None:
        """sync: provider=mock + allow_mock_llm=False → 抛 LLMCallError。"""
        from packages.common import settings
        from packages.distillation.llm_client import call_llm

        monkeypatch.setattr(settings, "llm_provider", "mock")
        monkeypatch.setattr(settings, "allow_mock_llm", False)
        with pytest.raises(LLMCallError, match="mock LLM fallback 被禁用"):
            call_llm("sys", "user")

    def test_sync_mock_provider_allowed_when_enabled(self, monkeypatch) -> None:
        """sync: provider=mock + allow_mock_llm=True → 返回 mock 字符串。"""
        from packages.common import settings
        from packages.distillation.llm_client import call_llm

        monkeypatch.setattr(settings, "llm_provider", "mock")
        monkeypatch.setattr(settings, "allow_mock_llm", True)
        result = call_llm("sys", "user")
        assert isinstance(result, str)

    def test_sync_no_api_key_blocked_when_disallowed(self, monkeypatch) -> None:
        """sync: provider=openai + 无 key + allow_mock_llm=False → 抛错。"""
        from packages.common import settings
        from packages.distillation.llm_client import call_llm

        monkeypatch.setattr(settings, "llm_provider", "openai")
        monkeypatch.setattr(settings, "openai_api_key", "")
        monkeypatch.setattr(settings, "allow_mock_llm", False)
        with pytest.raises(LLMCallError, match="mock LLM fallback 被禁用"):
            call_llm("sys", "user")


class TestAsyncMockGate:
    @pytest.mark.asyncio
    async def test_async_mock_blocked(self, monkeypatch) -> None:
        from packages.common import settings
        from packages.distillation.llm_client import acall_llm

        monkeypatch.setattr(settings, "llm_provider", "mock")
        monkeypatch.setattr(settings, "allow_mock_llm", False)
        with pytest.raises(LLMCallError, match="mock LLM fallback 被禁用"):
            await acall_llm("sys", "user")

    @pytest.mark.asyncio
    async def test_async_mock_allowed(self, monkeypatch) -> None:
        from packages.common import settings
        from packages.distillation.llm_client import acall_llm

        monkeypatch.setattr(settings, "llm_provider", "mock")
        monkeypatch.setattr(settings, "allow_mock_llm", True)
        result = await acall_llm("sys", "user")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_async_no_api_key_blocked(self, monkeypatch) -> None:
        from packages.common import settings
        from packages.distillation.llm_client import acall_llm

        monkeypatch.setattr(settings, "llm_provider", "openai")
        monkeypatch.setattr(settings, "openai_api_key", "")
        monkeypatch.setattr(settings, "allow_mock_llm", False)
        with pytest.raises(LLMCallError, match="mock LLM fallback 被禁用"):
            await acall_llm("sys", "user")


# ────────── 异步路径（mock SDK 拦截）──────────


class TestAsyncOpenAIPath:
    """模拟 AsyncOpenAI SDK 返回，验证 ``acall_llm`` 流程。"""

    @pytest.mark.asyncio
    async def test_async_openai_success(self, monkeypatch) -> None:
        from packages.common import settings
        from packages.distillation import llm_client

        monkeypatch.setattr(settings, "llm_provider", "openai")
        monkeypatch.setattr(settings, "openai_api_key", "sk-fake")
        monkeypatch.setattr(settings, "llm_model", "gpt-4o-mini")

        # 构造一个 AsyncMock 客户端
        fake_message = MagicMock(content="async ok")
        fake_choice = MagicMock(message=fake_message)
        fake_resp = MagicMock(choices=[fake_choice])

        fake_client = MagicMock()
        fake_client.chat = MagicMock()
        fake_client.chat.completions = MagicMock()
        fake_client.chat.completions.create = AsyncMock(return_value=fake_resp)

        # 重置单例后注入 fake
        llm_client.reset_async_clients()
        monkeypatch.setattr(llm_client, "_get_async_openai", lambda: fake_client)

        result = await llm_client.acall_llm("sys", "user")
        assert result == "async ok"
        fake_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_openai_empty_content(self, monkeypatch) -> None:
        """OpenAI 返回 content=None 时退化为空字符串。"""
        from packages.common import settings
        from packages.distillation import llm_client

        monkeypatch.setattr(settings, "llm_provider", "openai")
        monkeypatch.setattr(settings, "openai_api_key", "sk-fake")

        fake_resp = MagicMock(choices=[MagicMock(message=MagicMock(content=None))])
        fake_client = MagicMock()
        fake_client.chat.completions.create = AsyncMock(return_value=fake_resp)

        llm_client.reset_async_clients()
        monkeypatch.setattr(llm_client, "_get_async_openai", lambda: fake_client)

        result = await llm_client.acall_llm("sys", "user")
        assert result == ""


class TestAsyncAnthropicPath:
    @pytest.mark.asyncio
    async def test_async_anthropic_success(self, monkeypatch) -> None:
        from packages.common import settings
        from packages.distillation import llm_client

        monkeypatch.setattr(settings, "llm_provider", "anthropic")
        monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-fake")

        fake_block = MagicMock(text="anthropic async ok")
        fake_resp = MagicMock(content=[fake_block])

        fake_client = MagicMock()
        fake_client.messages = MagicMock()
        fake_client.messages.create = AsyncMock(return_value=fake_resp)

        llm_client.reset_async_clients()
        monkeypatch.setattr(llm_client, "_get_async_anthropic", lambda: fake_client)

        result = await llm_client.acall_llm("sys", "user")
        assert result == "anthropic async ok"


class TestAsyncJsonParse:
    @pytest.mark.asyncio
    async def test_acall_llm_json_success(self, monkeypatch) -> None:
        from packages.distillation import llm_client

        async def fake_acall(*args, **kwargs):
            return '{"key": "value", "n": 42}'

        monkeypatch.setattr(llm_client, "acall_llm", fake_acall)
        result = await llm_client.acall_llm_json("sys", "user")
        assert result == {"key": "value", "n": 42}

    @pytest.mark.asyncio
    async def test_acall_llm_json_with_markdown(self, monkeypatch) -> None:
        """LLM 用 markdown 代码块包裹 JSON 时仍能解析。"""
        from packages.distillation import llm_client

        async def fake_acall(*args, **kwargs):
            return '```json\n{"a": 1}\n```'

        monkeypatch.setattr(llm_client, "acall_llm", fake_acall)
        result = await llm_client.acall_llm_json("sys", "user")
        assert result == {"a": 1}

    @pytest.mark.asyncio
    async def test_acall_llm_json_invalid_raises(self, monkeypatch) -> None:
        """JSON 解析失败抛 LLMCallError（与同步版签名一致）。"""
        from packages.distillation import llm_client

        async def fake_acall(*args, **kwargs):
            return "this is not json"

        monkeypatch.setattr(llm_client, "acall_llm", fake_acall)
        with pytest.raises(LLMCallError, match="JSON 解析失败"):
            await llm_client.acall_llm_json("sys", "user")


class TestUnsupportedProvider:
    @pytest.mark.asyncio
    async def test_async_unsupported_provider(self, monkeypatch) -> None:
        from packages.common import settings
        from packages.distillation.llm_client import acall_llm

        monkeypatch.setattr(settings, "llm_provider", "gemini")  # 不支持
        monkeypatch.setattr(settings, "openai_api_key", "x")  # 绕过 mock 门控
        monkeypatch.setattr(settings, "anthropic_api_key", "x")
        # 让 _has_valid_api_key 返回 False（gemini 不在分支）
        # 实际进入 _check_mock_allowed → 抛错
        monkeypatch.setattr(settings, "allow_mock_llm", True)
        # mock 允许时 _has_valid_api_key=False（gemini 不匹配）→ 走 mock 路径，不会到 unsupported
        # 改测试：把 _has_valid_api_key 直接 monkeypatch
        from packages.distillation import llm_client

        monkeypatch.setattr(llm_client, "_has_valid_api_key", lambda: True)
        with pytest.raises(LLMCallError, match="不支持的 LLM provider"):
            await acall_llm("sys", "user")


# ────────── 单例管理 ──────────


class TestAsyncClientSingleton:
    def test_reset_async_clients(self, monkeypatch) -> None:
        """reset_async_clients 应清空两个单例。"""
        from packages.distillation import llm_client

        # 模拟单例已被赋值
        llm_client._async_openai_client = MagicMock()
        llm_client._async_anthropic_client = MagicMock()

        llm_client.reset_async_clients()

        assert llm_client._async_openai_client is None
        assert llm_client._async_anthropic_client is None
