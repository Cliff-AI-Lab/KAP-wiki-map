"""Settings 三环境配置单测（坑 1 批 0 验收）。

覆盖：

- kap_env 枚举校验（合法 / 非法 / 大小写）
- sandbox/prod 强制 verify_ssl=True（坑 D）
- sandbox/prod 强制 allow_mock_llm=False（坑 F）
- dev 保留用户配置
- sandbox_api_base 仍正确覆盖 openai_base_url
"""

from __future__ import annotations

import pytest

from packages.common.config import (
    KAP_ENV_DEV,
    KAP_ENV_PROD,
    KAP_ENV_SANDBOX,
    Settings,
)


# ────────── kap_env 枚举校验 ──────────


class TestKapEnvValidation:
    """注意：sandbox/prod 强制非 mock embedding（坑 6），所以这些 case 显式传 ruidong。"""

    def test_default_is_dev(self) -> None:
        s = Settings(_env_file=None)  # 不读 .env，避免外部干扰
        assert s.kap_env == KAP_ENV_DEV

    def test_explicit_sandbox(self) -> None:
        s = Settings(_env_file=None, kap_env="sandbox", embedding_provider="ruidong")
        assert s.kap_env == KAP_ENV_SANDBOX

    def test_explicit_prod(self) -> None:
        s = Settings(_env_file=None, kap_env="prod", embedding_provider="ruidong")
        assert s.kap_env == KAP_ENV_PROD

    def test_case_insensitive_normalize(self) -> None:
        """大写 / 混合大小写应被规范化为小写。"""
        s = Settings(_env_file=None, kap_env="PROD", embedding_provider="ruidong")
        assert s.kap_env == KAP_ENV_PROD

    def test_invalid_env_raises(self) -> None:
        with pytest.raises(ValueError, match="非法 kap_env"):
            Settings(_env_file=None, kap_env="staging")  # 不在枚举中

    def test_sandbox_with_mock_embedding_raises(self) -> None:
        """坑 6：sandbox/prod 强制非 mock embedding。"""
        with pytest.raises(ValueError, match="禁止使用 mock embedding"):
            Settings(_env_file=None, kap_env="sandbox", embedding_provider="mock")


# ────────── 坑 D：verify_ssl 三环境强制 ──────────


class TestVerifySslPolicy:
    def test_dev_allows_false(self) -> None:
        """dev 环境用户可关闭 SSL 校验（睿动 sandbox 证书宽容）。"""
        s = Settings(_env_file=None, kap_env="dev", llm_verify_ssl=False)
        assert s.llm_verify_ssl is False

    def test_sandbox_forces_true(self) -> None:
        """sandbox 环境无视用户输入，强制 verify_ssl=True。"""
        s = Settings(
            _env_file=None,
            kap_env="sandbox",
            llm_verify_ssl=False,
            embedding_provider="ruidong",
        )
        assert s.llm_verify_ssl is True

    def test_prod_forces_true(self) -> None:
        s = Settings(
            _env_file=None,
            kap_env="prod",
            llm_verify_ssl=False,
            embedding_provider="ruidong",
        )
        assert s.llm_verify_ssl is True

    def test_dev_default_true(self) -> None:
        """dev 环境默认仍是 True，更安全的默认。"""
        s = Settings(_env_file=None, kap_env="dev")
        assert s.llm_verify_ssl is True


# ────────── 坑 F：allow_mock_llm 三环境强制 ──────────


class TestAllowMockLlmPolicy:
    def test_dev_allows_true(self) -> None:
        """dev 环境允许 mock LLM 加速本地调试。"""
        s = Settings(_env_file=None, kap_env="dev", allow_mock_llm=True)
        assert s.allow_mock_llm is True

    def test_sandbox_forces_false(self) -> None:
        """sandbox 环境无视用户输入，强制 allow_mock_llm=False。"""
        s = Settings(
            _env_file=None,
            kap_env="sandbox",
            allow_mock_llm=True,
            embedding_provider="ruidong",
        )
        assert s.allow_mock_llm is False

    def test_prod_forces_false(self) -> None:
        s = Settings(
            _env_file=None,
            kap_env="prod",
            allow_mock_llm=True,
            embedding_provider="ruidong",
        )
        assert s.allow_mock_llm is False

    def test_default_is_false(self) -> None:
        """默认禁止 mock fallback，需显式开启。"""
        s = Settings(_env_file=None)
        assert s.allow_mock_llm is False


# ────────── sandbox_api_base 覆盖（保留行为）──────────


class TestSandboxApiBaseOverride:
    def test_sandbox_url_overrides_base(self) -> None:
        """SANDBOX_API_BASE 环境变量应覆盖 openai_base_url（睿动规范 MUST-2）。"""
        s = Settings(
            _env_file=None,
            kap_env="sandbox",
            sandbox_api_base="https://sandbox.iruidong.internal/v1",
            openai_base_url="https://api.openai.com/v1",
            embedding_provider="ruidong",
        )
        assert s.openai_base_url == "https://sandbox.iruidong.internal/v1"

    def test_no_override_when_empty(self) -> None:
        """sandbox_api_base 为空则不覆盖。"""
        s = Settings(
            _env_file=None,
            sandbox_api_base="",
            openai_base_url="https://iruidong.com/v1",
        )
        assert s.openai_base_url == "https://iruidong.com/v1"


# ────────── 新字段默认值 ──────────


class TestNewFieldDefaults:
    def test_llm_http_timeout_default(self) -> None:
        s = Settings(_env_file=None)
        assert s.llm_http_timeout == 60.0

    def test_llm_max_concurrency_default(self) -> None:
        s = Settings(_env_file=None)
        assert s.llm_max_concurrency == 4

    def test_existing_pipeline_max_workers_preserved(self) -> None:
        """旧字段 pipeline_max_workers 保留兼容。"""
        s = Settings(_env_file=None)
        assert s.pipeline_max_workers == 4
