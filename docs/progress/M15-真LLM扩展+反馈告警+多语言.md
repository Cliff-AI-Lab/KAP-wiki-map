---
title: M15 真 LLM 扩展 + 反馈告警 + 多语言 进度快照
milestone: M15
version: v1
date: 2026-05-01
commits: 3
tests: +15 backend / +2 live_llm
hours: ~3
opus-estimate: 9-12h
savings: ~75%
status: completed
tags: [kap, m15]
---

> 进程链：[M0 KAP-Lite](M0-KAP-Lite.md) → ... → [M14 大规模优化与端到端补强](M14-大规模优化与端到端补强.md) → **【M15 真 LLM 扩展 + 反馈告警 + 多语言】** → [M16 i18n + 自学习闭环 + 反馈细分 + Wiki 可视化](M16-i18n%2B自学习闭环%2B反馈细分%2BWiki可视化.md)
>
> 设计蓝本：[决策书 §5.3 真 LLM 测试覆盖 + 反馈维度告警 + 国际化](../01-技术决策书.md)

# M15 真 LLM 扩展 + 反馈告警 + 多语言（3 commits / ~3h vs Opus 估 9-12h，节省 ~75%）

## 全景成果

### M15 #1 · W4 抽取 LLM 测试覆盖扩展
- tests/integration/test_live_llm_w4_extraction.py · 2 测试
- 真 LLM 调 extract_entities_and_relations + 弱断言 schema
- 实体列表非空 / type_id 非空 / confidence 在 [0,1]
- 老 mock 测试保留作快速回归
- live_llm 总数：M13 #1 (2) + M14 #1 (3) + M15 #1 (2) = 7
- **关联代码**：[`backend/tests/integration/test_live_llm_w4_extraction.py`](../../backend/tests/integration/test_live_llm_w4_extraction.py)

### M15 #2 · useful_rate 趋势告警
M9 #2 召回率告警模式应用到用户反馈维度：
- `compute_useful_rate_trend(project_id, window_size, lookback_size)`
- 双窗口 useful_rate 对比；跌 > 10pp 触发 useful_alert（双窗口 ≥ 5 条）
- `check_useful_alerts_and_propagate` 把告警追加到当前活跃 PromotionObservation
- POST /queries/{id}/feedback 完成后自动跑趋势检查
- 新端点 `GET /observability/queries/useful-trend`
- **关联代码**：[`packages/observability/query_log.py`](../../backend/packages/observability/query_log.py) 新增函数

### M15 #3 · 多语言 prompt
PromptVersion 加 language 字段（zh/en/...，默认 zh）：
- 同 (condition_type, language) 同时最多一个 active；不同语言独立
- `get_active_version(condition_type, language='zh')` — 精确匹配 + 回退 zh
- `resolve_active_system_prompt(..., language='zh')` 同上
- evolution_proposer 4 函数读 `KAP_LLM_LANG` env 切换语言
- PG DDL 加 language 列 + ALTER TABLE 兼容老库
- INDEX (condition_type, language, activated_at DESC)
- API POST /prompt-versions 加 language；GET 加 language 过滤
- **关联代码**：[`packages/observability/prompt_versions.py`](../../backend/packages/observability/prompt_versions.py) + [`pg_prompt_versions.py`](../../backend/packages/observability/pg_prompt_versions.py)

---

## Commits 时间线

| Commit    | 内容                                                              | 测试           |
|:---|:---|:---:|
| `c086de3` | #1 W4 抽取 live_llm 测试（弱断言端到端）                          | +2 live_llm    |
| `fa37e82` | #2 useful_rate 趋势告警（M9 #2 模式应用反馈维度）                 | +8 后          |
| `fd3eba4` | #3 多语言 prompt（language 字段 + 回退 zh + KAP_LLM_LANG env）    | +7 后          |

---

## 测试基线

`987/989 unit ✓` 后端 + `33 frontend tests passed` + 7 live_llm（默认 deselect）。

---

## M15 已交付

- ✓ W4 抽取 live_llm 测试（M14 #1 + 本批合计 5 大监测/抽取通路全 live_llm 覆盖）
- ✓ useful_rate 跨窗口对比 + 跌破 10pp 自动 propagate alert
- ✓ PromptVersion 多语言（zh/en），KAP_LLM_LANG 切换运行时语言

---

## M16 待启动方向

- 独立物理 Neo4j 实例（部署期 — 需 ops 协调）
- ISS-Job 真实环境联调（接通 JWT + 真 ISS Quartz）
- 前端国际化（i18n 框架 + UI 字符串提取）— 与 M15 #3 后端语言切换配合
- 块② Wiki 编译可视化（V11.2 三层 Wiki 体系前端深耕）
- portal 用户反馈"为什么无用"细分原因（多选标签）
- LLM 自学习的自动 promote / rollback（M11 #4 AB 比较结果转动作）
