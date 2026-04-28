"""Judge 决策阈值配置加载（按行业模板包外置）。

M0-tech-debt 坑 3 改造：把硬编码在 ``judge.py`` / ``kpi_retain.py`` 里的
``DISCARD_THRESHOLD`` / ``ARCHIVE_THRESHOLD`` 等魔数外置为 YAML 配置，
按行业模板包加载（``templates/<industry>/judge-thresholds.yaml``），
支持项目级 / 行业级覆盖与默认 fallback。

加载优先级（从高到低）：
  1. 调用方显式传入 ``JudgeThresholds``（测试 / 临时调优）
  2. 行业模板：``$KAP_TEMPLATES_DIR/<industry>/judge-thresholds.yaml``
  3. 默认模板：``$KAP_TEMPLATES_DIR/_default/judge-thresholds.yaml``
  4. 代码内硬编码 fallback（仅当模板包都缺失时使用）

阈值字段说明：
  - ``discard_threshold``：KPI 低于此值 + LLM 也判 DISCARD → 丢弃
  - ``archive_threshold``：KPI 低于此值 或 LLM 判 ARCHIVE → 归档
  - ``confidence_floor``：LLM DISCARD 决策的最低置信度门槛（高于此 → 尊重 LLM）
  - ``review_band_low / high``：KPI 落在此区间且置信度 < ``review_confidence_max``
    时，自动标记 ``needs_review``（进 W4 SME 复核队列）
  - ``review_confidence_max``：低于此置信度时进入 review 通道
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from packages.common import get_logger

log = get_logger("scoring.judge_thresholds")


@dataclass(frozen=True, slots=True)
class JudgeThresholds:
    """Judge 决策阈值集（不可变，便于跨线程共享与缓存）。"""

    discard_threshold: float = 0.20
    archive_threshold: float = 0.45
    confidence_floor: float = 0.80
    redundancy_weight: float = 1.0
    review_band_low: float = 0.30        # KPI 居中带下界
    review_band_high: float = 0.55       # KPI 居中带上界
    review_confidence_max: float = 0.60  # 低于此置信度，居中带的文档进 review
    industry: str = "_default"
    source: str = "code-fallback"        # 来源标识，便于审计

    def __post_init__(self) -> None:
        # 简单一致性校验，越界配置直接报错（启动期就发现问题）
        if not (0.0 <= self.discard_threshold <= self.archive_threshold <= 1.0):
            raise ValueError(
                f"阈值不一致：discard ({self.discard_threshold}) 必须 ≤ "
                f"archive ({self.archive_threshold}) 且都在 [0, 1]"
            )
        if not (self.review_band_low <= self.review_band_high):
            raise ValueError(
                f"review 带：low ({self.review_band_low}) 必须 ≤ high ({self.review_band_high})"
            )
        if not (0.0 <= self.confidence_floor <= 1.0):
            raise ValueError(f"confidence_floor 越界：{self.confidence_floor}")


# 默认 fallback（与 V15 行为兼容）
DEFAULT_THRESHOLDS = JudgeThresholds(
    discard_threshold=0.20,
    archive_threshold=0.45,
    confidence_floor=0.80,
    redundancy_weight=1.0,
    review_band_low=0.30,
    review_band_high=0.55,
    review_confidence_max=0.60,
    industry="_default",
    source="code-fallback",
)


def _templates_root() -> Path:
    """模板根目录。优先 KAP_TEMPLATES_DIR 环境变量，否则回到 backend/templates。"""
    env_path = os.environ.get("KAP_TEMPLATES_DIR")
    if env_path:
        return Path(env_path)
    # 当前文件位于 backend/packages/distillation/scoring/judge_thresholds.py
    # 向上四级 → backend/，再加 templates/
    return Path(__file__).resolve().parent.parent.parent.parent / "templates"


def _read_yaml(path: Path) -> dict[str, Any] | None:
    """读 YAML，返回顶层 dict；不存在或解析失败返回 None。"""
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if isinstance(data, dict):
                return data
            log.warning("judge_thresholds_yaml_not_dict", path=str(path))
            return None
    except yaml.YAMLError as e:
        log.error("judge_thresholds_yaml_parse_failed", path=str(path), error=str(e))
        return None


def _from_yaml(path: Path, industry: str, source: str) -> JudgeThresholds | None:
    """从 YAML 加载阈值。文件不存在或字段缺失时返回 None，由调用方决定 fallback。"""
    data = _read_yaml(path)
    if not data:
        return None
    # 字段缺失则用默认值（dataclass 的字段默认）
    fields = {
        "discard_threshold": data.get("discard_threshold", DEFAULT_THRESHOLDS.discard_threshold),
        "archive_threshold": data.get("archive_threshold", DEFAULT_THRESHOLDS.archive_threshold),
        "confidence_floor": data.get("confidence_floor", DEFAULT_THRESHOLDS.confidence_floor),
        "redundancy_weight": data.get("redundancy_weight", DEFAULT_THRESHOLDS.redundancy_weight),
        "review_band_low": data.get("review_band_low", DEFAULT_THRESHOLDS.review_band_low),
        "review_band_high": data.get("review_band_high", DEFAULT_THRESHOLDS.review_band_high),
        "review_confidence_max": data.get(
            "review_confidence_max", DEFAULT_THRESHOLDS.review_confidence_max
        ),
        "industry": industry,
        "source": source,
    }
    try:
        return JudgeThresholds(**fields)
    except (ValueError, TypeError) as e:
        log.error(
            "judge_thresholds_invalid",
            path=str(path),
            industry=industry,
            error=str(e),
        )
        return None


@lru_cache(maxsize=32)
def load_thresholds(industry: str | None = None) -> JudgeThresholds:
    """加载指定行业的 Judge 阈值；失败逐级 fallback。

    Args:
        industry: 行业名（如 "energy" / "manufacturing"）；为 None 走 ``_default``。

    Returns:
        ``JudgeThresholds`` 实例（不可变）。caller 不应修改返回值。

    Notes:
        - 用 ``lru_cache`` 缓存，进程内同一 industry 只加载一次
        - 配置变更后调用 ``load_thresholds.cache_clear()`` 强制重读
    """
    target_industry = (industry or "_default").strip().lower()
    root = _templates_root()

    # 1. 行业专属模板
    if target_industry != "_default":
        path = root / target_industry / "judge-thresholds.yaml"
        thresholds = _from_yaml(path, industry=target_industry, source=f"yaml:{path}")
        if thresholds is not None:
            log.info(
                "judge_thresholds_loaded",
                industry=target_industry,
                source=thresholds.source,
            )
            return thresholds
        log.warning(
            "judge_thresholds_industry_template_missing",
            industry=target_industry,
            tried=str(path),
        )

    # 2. _default 模板
    default_path = root / "_default" / "judge-thresholds.yaml"
    thresholds = _from_yaml(default_path, industry=target_industry, source=f"yaml:{default_path}")
    if thresholds is not None:
        log.info(
            "judge_thresholds_loaded",
            industry=target_industry,
            source=thresholds.source,
        )
        return thresholds

    # 3. 代码内硬编码 fallback
    log.warning(
        "judge_thresholds_fallback_to_code",
        industry=target_industry,
        templates_root=str(root),
    )
    return JudgeThresholds(industry=target_industry, source="code-fallback")
