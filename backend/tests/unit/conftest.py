"""Unit 测试公共 fixture。

M0-tech-debt 坑 6 引入后，settings 默认 ``allow_mock_embedding=False``（生产安全默认）。
但 unit 测试是 dev 环境且需要 mock 行为，因此本 conftest 自动放开 mock 门控。

M22 #8 起额外隔离 ``backend/configs/llm_settings.json`` —— M21 #11 的
``_apply_llm_settings_json`` 让 Settings() 在初始化时叠加该 JSON, 开发机上
若该文件存在（含真实 API Key / embedding_dim=4096 / 真模型名）会污染测试：
- test_multi_tenant: 1536 维 embedding 被 4096 维 dim 过滤
- test_parsers (video): 真 API Key 让 VideoParser 走 whisper 转写而非 mock
所有 unit 测试默认隔离, 单测纯净 default。

集成 / sandbox / prod 测试不应继承本 conftest 的覆盖。
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_llm_settings_json(monkeypatch) -> None:
    """M22 #8 · 隔离 llm_settings.json 污染。

    两层隔离:
    1. 重定向 _LLM_SETTINGS_JSON 路径 — 测试内 *新建* Settings() 不会再叠加 JSON
       （让 test_settings.py 这类 default 验证保持纯净）
    2. 重置全局 `settings` 单例的关键字段回 KAP 默认值 — 解决 Settings 在
       config.py 模块加载时已经被 JSON 污染的"过去时"问题
       （test_multi_tenant.embedding_dim / test_parsers.video API Key 等)

    M21 #11 的 _apply_llm_settings_json 让 Settings.__init__ 叠加本地 JSON,
    开发机若有真实 API Key + embedding_dim=4096 + 真模型名 会污染:
    - test_multi_tenant: 1536 维 embedding 被 4096 维 dim 过滤
    - test_parsers (video): 真 API Key 让 VideoParser 走 whisper 转写而非 mock
    """
    from packages.common import config as config_mod
    from packages.common import settings as _settings

    monkeypatch.setattr(
        config_mod, "_LLM_SETTINGS_JSON",
        Path("/__nonexistent__/llm.json"),
    )

    # 重置全局单例关键字段到 KAP 默认值（模拟"无 llm_settings.json"状态）
    monkeypatch.setattr(_settings, "openai_api_key", "", raising=False)
    monkeypatch.setattr(_settings, "anthropic_api_key", "", raising=False)
    monkeypatch.setattr(_settings, "llm_model", "gpt-4o-mini", raising=False)
    monkeypatch.setattr(_settings, "embedding_provider", "mock", raising=False)
    monkeypatch.setattr(_settings, "embedding_model", "", raising=False)
    monkeypatch.setattr(_settings, "embedding_dim", 1536, raising=False)
    monkeypatch.setattr(_settings, "llm_provider", "openai", raising=False)


@pytest.fixture(autouse=True)
def _allow_mock_in_unit_tests(monkeypatch) -> None:
    """unit 测试默认放开 mock LLM / mock embedding 门控。

    个别测试若需测"mock 被禁用"行为，应在测试内部显式 monkeypatch 覆盖回 False。
    """
    from packages.common import settings

    # 仅 dev 模式下能放开（sandbox/prod 由 model_post_init 保护）
    if settings.kap_env == "dev":
        monkeypatch.setattr(settings, "allow_mock_llm", True)
        monkeypatch.setattr(settings, "allow_mock_embedding", True)
