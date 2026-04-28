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

from dataclasses import dataclass
from functools import lru_cache

from packages.common import get_logger
from packages.distillation.templates_loader import load_yaml

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


@lru_cache(maxsize=32)
def load_thresholds(industry: str | None = None) -> JudgeThresholds:
    """加载指定行业的 Judge 阈值；失败逐级 fallback 到 _default 或代码常量。

    Args:
        industry: 行业名（如 ``"energy"`` / ``"manufacturing"``）；为 None 走 ``_default``。

    Returns:
        ``JudgeThresholds`` 实例（不可变）。caller 不应修改返回值。

    Notes:
        - 用 ``lru_cache`` 缓存；配置热更新后调用 ``load_thresholds.cache_clear()``
        - YAML 加载本身已被 ``templates_loader.load_yaml`` 缓存，本函数二次缓存只为
          避免每次都构造 ``JudgeThresholds`` 对象
    """
    target_industry = (industry or "_default").strip().lower()

    loaded = load_yaml(target_industry, "judge-thresholds.yaml")
    if loaded is None:
        log.warning(
            "judge_thresholds_fallback_to_code",
            industry=target_industry,
        )
        return JudgeThresholds(industry=target_industry, source="code-fallback")

    data, source = loaded
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
        "industry": target_industry,
        "source": source,
    }
    try:
        thresholds = JudgeThresholds(**fields)
        log.info("judge_thresholds_loaded", industry=target_industry, source=source)
        return thresholds
    except (ValueError, TypeError) as e:
        log.error(
            "judge_thresholds_invalid",
            industry=target_industry,
            source=source,
            error=str(e),
        )
        return JudgeThresholds(industry=target_industry, source=f"code-fallback:invalid({source})")
