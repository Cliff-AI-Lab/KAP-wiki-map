"""模板加载器单测（坑 4a 验收）。

覆盖：

- ``templates_root()`` 路径解析（默认 + ``KAP_TEMPLATES_DIR`` 覆盖）
- ``load_yaml`` 行业 → _default → None 加载链
- ``clear_cache`` 重置
"""

from __future__ import annotations

import os

import pytest

from packages.distillation.templates_loader import (
    clear_cache,
    load_yaml,
    templates_root,
)


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    clear_cache()


class TestTemplatesRoot:
    def test_default_path_under_backend(self) -> None:
        """默认路径应指向 backend/templates。"""
        # 临时清掉环境变量
        original = os.environ.pop("KAP_TEMPLATES_DIR", None)
        try:
            root = templates_root()
            assert root.name == "templates"
            assert root.parent.name == "backend"
        finally:
            if original is not None:
                os.environ["KAP_TEMPLATES_DIR"] = original

    def test_env_override(self, tmp_path) -> None:
        """``KAP_TEMPLATES_DIR`` 环境变量应覆盖默认路径。"""
        os.environ["KAP_TEMPLATES_DIR"] = str(tmp_path)
        try:
            assert templates_root() == tmp_path.resolve()
        finally:
            os.environ.pop("KAP_TEMPLATES_DIR", None)


class TestLoadYaml:
    def test_load_existing_industry(self) -> None:
        """加载真实存在的能源 judge-thresholds.yaml。"""
        loaded = load_yaml("energy", "judge-thresholds.yaml")
        assert loaded is not None
        data, source = loaded
        assert "discard_threshold" in data
        assert source.startswith("yaml:")
        assert "energy" in source

    def test_falls_back_to_default(self, tmp_path, monkeypatch) -> None:
        """行业模板缺失时应 fallback 到 _default。"""
        # 构造仅有 _default 模板的临时目录
        default_dir = tmp_path / "_default"
        default_dir.mkdir()
        (default_dir / "judge-thresholds.yaml").write_text(
            "discard_threshold: 0.99\n", encoding="utf-8"
        )
        monkeypatch.setenv("KAP_TEMPLATES_DIR", str(tmp_path))
        clear_cache()  # 路径变了，必须清缓存

        # 请求不存在的行业，应读到 _default 的内容
        loaded = load_yaml("non-existent-industry", "judge-thresholds.yaml")
        assert loaded is not None
        data, source = loaded
        assert data["discard_threshold"] == 0.99
        assert "_default" in source

    def test_returns_none_when_all_missing(self, tmp_path, monkeypatch) -> None:
        """行业 + 默认模板都缺时返回 None。"""
        monkeypatch.setenv("KAP_TEMPLATES_DIR", str(tmp_path))
        clear_cache()
        assert load_yaml("any-industry", "non-existent-file.yaml") is None

    def test_industry_case_insensitive(self) -> None:
        a = load_yaml("ENERGY", "judge-thresholds.yaml")
        b = load_yaml("energy", "judge-thresholds.yaml")
        assert a is not None and b is not None
        # 缓存键基于 (industry, filename)，但内部 strip().lower() 后查找路径相同
        assert a[0] == b[0]
