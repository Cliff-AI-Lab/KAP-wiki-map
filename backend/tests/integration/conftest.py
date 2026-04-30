"""Integration tests 共享 fixture。

M13 #1 · live_llm 测试需要真实 LLM 端点：
- 默认 ``addopts = "-m 'not live_llm'"`` 已在 pyproject.toml 排除
- 显式 ``pytest -m live_llm`` 才跑
- 仍需 ``settings.openai_api_key`` 非空才执行；空时单测自己 skip
"""

from __future__ import annotations

import pytest

from packages.common.config import settings


@pytest.fixture(scope="session")
def live_llm_available() -> bool:
    """快速判定真实 LLM 是否可用（API key 非空 + base_url 非空）。"""
    return bool(
        settings.openai_api_key and settings.openai_api_key.strip()
        and settings.openai_base_url and settings.openai_base_url.strip()
    )


@pytest.fixture
def require_live_llm(live_llm_available):
    """供 live_llm 测试使用：API key 缺失时 skip 而非失败。"""
    if not live_llm_available:
        pytest.skip(
            "LIVE LLM 测试需要 settings.openai_api_key 非空 "
            "(KAP_OPENAI_API_KEY 环境变量) + base_url 非空"
        )
