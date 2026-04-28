"""KPI_retain 知识保留指数计算。

公式：KPI_retain = (D * w_d + (1 - ΔT/T_max) * w_t) / (R + 1)

- D:   信息密度 (0-1)
- ΔT:  文档年龄（天）
- T_max: 最大参考年龄（默认 730 天 = 2 年）
- R:   冗余度 (0-1)
- w_d, w_t: 加权系数

本模块提供 KPI_retain 知识保留指数的核心计算逻辑。该指数综合考虑三个维度：
  - 信息密度（D）：文档内容的知识含量，由 LLM 评分归一化得到
  - 时效性（timeliness）：基于文档更新时间计算的衰减值，越新越高
  - 冗余度（R）：文档与同类目其他文档的重复程度，作为分母惩罚项

KPI 值域为 [0.0, 1.0]，值越高表示文档越值得保留。Judge Agent 根据
DISCARD_THRESHOLD 和 ARCHIVE_THRESHOLD 两个阈值将文档分为三档处理。
"""

from __future__ import annotations

from datetime import datetime, timezone

from packages.common import get_logger, settings

log = get_logger("scoring.kpi_retain")

# 默认加权系数：信息密度权重 0.6，时效性权重 0.4
W_DENSITY = 0.6
W_TIMELINESS = 0.4
# 最大参考年龄：730 天（2 年），超过此年龄的文档时效性视为零
T_MAX_DAYS = 730

# 决策阈值（从配置读取，支持运行时调整）
# KPI 低于 DISCARD_THRESHOLD → 候选丢弃
# KPI 低于 ARCHIVE_THRESHOLD → 候选归档
DISCARD_THRESHOLD: float = settings.kpi_discard_threshold
ARCHIVE_THRESHOLD: float = settings.kpi_archive_threshold


def compute_kpi_retain(
    density_score: float,
    updated_at: datetime | None,
    redundancy_score: float = 0.0,
    w_density: float = W_DENSITY,
    w_timeliness: float = W_TIMELINESS,
    t_max: int = T_MAX_DAYS,
) -> float:
    """计算单个文档的 KPI_retain 知识保留指数。

    公式：KPI = (D * w_d + timeliness * w_t) / (R + 1)

    Args:
        density_score: LLM 评定的信息密度分数（0-10 分制）。
        updated_at: 文档最后更新时间（带时区或 naive UTC）。
            若为 None，视为最老文档（时效性为零）。
        redundancy_score: 冗余度分数（0-1），值越高惩罚越大。默认 0 表示无冗余。
        w_density: 信息密度的加权系数，默认 0.6。
        w_timeliness: 时效性的加权系数，默认 0.4。
        t_max: 最大参考年龄（天），超过此值时效性为零，默认 730 天。

    Returns:
        KPI_retain 值，范围 [0.0, 1.0]，精确到小数点后 4 位。
    """
    # 归一化密度到 0-1（原始分数为 0-10 分制）
    d = min(max(density_score / 10.0, 0.0), 1.0)

    # 计算文档年龄（统一使用 UTC）
    if updated_at:
        now = datetime.now(timezone.utc)
        # 若传入 naive datetime（无时区信息），假定为 UTC
        if updated_at.tzinfo is None:
            log.debug("kpi_naive_datetime_assumed_utc", updated_at=str(updated_at))
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        delta_days = max((now - updated_at).days, 0)  # 防止未来日期产生负数
    else:
        delta_days = t_max  # 无日期信息视为最老

    # 时效性：线性衰减，从 1.0（刚更新）衰减到 0.0（超过 t_max 天）
    timeliness = 1.0 - min(delta_days / t_max, 1.0)

    # 冗余度：限制在 [0, 1] 范围内
    r = min(max(redundancy_score, 0.0), 1.0)

    # 核心公式：分子为密度和时效性的加权和，分母为冗余惩罚项（R+1 确保不除以零）
    kpi = (d * w_density + timeliness * w_timeliness) / (r + 1.0)

    # Clamp 到 [0.0, 1.0] 区间
    kpi = max(0.0, min(kpi, 1.0))

    log.debug(
        "kpi_retain_computed",
        density=d,
        timeliness=round(timeliness, 3),
        redundancy=r,
        kpi=round(kpi, 4),
    )
    return round(kpi, 4)
