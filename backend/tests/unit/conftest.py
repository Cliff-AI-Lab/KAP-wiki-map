"""Unit 测试公共 fixture。

M0-tech-debt 坑 6 引入后，settings 默认 ``allow_mock_embedding=False``（生产安全默认）。
但 unit 测试是 dev 环境且需要 mock 行为，因此本 conftest 自动放开 mock 门控。

集成 / sandbox / prod 测试不应继承本 conftest 的覆盖。
"""

from __future__ import annotations

import pytest


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
