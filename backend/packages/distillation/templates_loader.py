"""KAP 行业模板包加载器（坑 4a 共享基础设施）。

把"按行业 + 按文件名查找 templates 目录下的 YAML"这套通用机制抽出来，
让 judge_thresholds / domain_inference / 未来的 ontology / refiner-prompt
等模块统一使用，避免每个特性都自带一份 ``_read_yaml`` / ``_templates_root``。

模板目录结构（决策书 §7.4）：

```
templates/
    _default/                  # 兜底模板，所有行业未覆盖时使用
        judge-thresholds.yaml
        domain-keywords.yaml
        ontology-l1.yaml       (M1)
        refiner-prompt.tmpl    (M1)
    energy/
        judge-thresholds.yaml
        domain-keywords.yaml
        ...
    manufacturing/
        ...
```

加载链：``industry/<file>`` → ``_default/<file>`` → None（调用方决定 fallback）

环境变量：

- ``KAP_TEMPLATES_DIR``：覆盖默认路径（默认 ``backend/templates``）
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from packages.common import get_logger

log = get_logger("templates_loader")

DEFAULT_INDUSTRY = "_default"


def templates_root() -> Path:
    """模板包根目录。优先 ``$KAP_TEMPLATES_DIR``，否则 ``backend/templates``。

    Notes:
        - 路径解析按"当前文件向上 3 级 → backend/" 推算，避免依赖 cwd
        - 调用方不应缓存返回值，本函数已足够便宜
    """
    env_path = os.environ.get("KAP_TEMPLATES_DIR")
    if env_path:
        return Path(env_path).resolve()
    # 当前文件：backend/packages/distillation/templates_loader.py
    # 向上三级 → backend/，加 templates
    return (Path(__file__).resolve().parent.parent.parent / "templates").resolve()


def _read_yaml(path: Path) -> dict[str, Any] | None:
    """读 YAML 文件，返回顶层 dict；不存在或解析失败返回 None。"""
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if data is None:
            return {}
        if not isinstance(data, dict):
            log.warning("template_yaml_not_dict", path=str(path))
            return None
        return data
    except yaml.YAMLError as e:
        log.error("template_yaml_parse_failed", path=str(path), error=str(e))
        return None


@lru_cache(maxsize=128)
def load_yaml(industry: str | None, filename: str) -> tuple[dict[str, Any], str] | None:
    """加载 ``templates/<industry>/<filename>``（fallback 到 ``_default``）。

    Args:
        industry: 行业名（如 ``"energy"``）；为 None 或空走 ``_default``
        filename: 文件名（含扩展名，如 ``"judge-thresholds.yaml"``）

    Returns:
        ``(data_dict, source_path)`` 元组（成功）；``None`` 表示行业模板和默认都缺失。

    Notes:
        - 用 ``lru_cache`` 缓存命中的 (industry, filename)
        - 失败不缓存（None 也会缓存？lru_cache 会缓存 None 返回值！）

    Caveat:
        lru_cache 会缓存 None。这是有意为之 —— 调用方不应反复探测不存在的模板。
        如需强制重读，调用 ``load_yaml.cache_clear()`` 或 ``clear_cache()``。
    """
    industry_clean = (industry or DEFAULT_INDUSTRY).strip().lower()
    root = templates_root()

    # 1. 行业专属模板
    if industry_clean != DEFAULT_INDUSTRY:
        industry_path = root / industry_clean / filename
        data = _read_yaml(industry_path)
        if data is not None:
            log.debug(
                "template_loaded",
                industry=industry_clean,
                filename=filename,
                source=str(industry_path),
            )
            return data, f"yaml:{industry_path}"

    # 2. _default 模板
    default_path = root / DEFAULT_INDUSTRY / filename
    data = _read_yaml(default_path)
    if data is not None:
        log.debug(
            "template_loaded_default",
            industry=industry_clean,
            filename=filename,
            source=str(default_path),
        )
        return data, f"yaml:{default_path}"

    # 3. 全部缺失
    log.warning(
        "template_missing",
        industry=industry_clean,
        filename=filename,
        templates_root=str(root),
    )
    return None


def clear_cache() -> None:
    """清空 ``load_yaml`` 缓存。配置热更新或测试间需要时调用。"""
    load_yaml.cache_clear()
