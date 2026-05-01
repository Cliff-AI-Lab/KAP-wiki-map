---
title: M17 i18n 铺开 + 自动 tune + Wiki 质量评分 进度快照
milestone: M17
version: v1
date: 2026-05-01
commits: 3
tests: +10 backend / +1 live_llm
hours: ~4
opus-estimate: 12-15h
savings: ~75%
status: completed
tags: [kap, m17]
---

> 进程链：[M0 KAP-Lite](M0-KAP-Lite.md) → ... → [M16 i18n + 自学习闭环 + 反馈细分 + Wiki 可视化](M16-i18n%2B自学习闭环%2B反馈细分%2BWiki可视化.md) → **【M17 i18n 铺开 + 自动 tune + Wiki 质量评分】** → M18⬜

# M17 i18n 铺开 + 自动 tune + Wiki 质量评分（3 commits / ~4h vs Opus 估 12-15h，节省 ~75%）

## 全景成果

### M17 #1 · 前端 i18n 全量铺开
- lib/i18n.ts 加 33 个 TranslationKey + zh/en 双语
- 4 主页面接入 + LanguageSwitcher：
  - GovernanceMatrix（标题 / R/C/I 图例 / 总数模板）
  - MyClaimed（批量按钮 / 全选 / 计数模板 / 空状态模板）
  - GroundTruthReview（标题 / 候选 / 已入库 / 空）
  - ObservabilityCompare（标题 / 8 列表头 / 空）
- 测试 mock useLocale 提供静态翻译表（含变量插值）

### M17 #2 · 自动 tune 定时器接入
- iss_job.py cron-recommendations 端点扩展：
  - decisions_total ≥ 50 时推荐 4 个 auto_tune_prompt_{condition_type} jobs
  - 周度间隔 7 天（604800s）
  - 每条件分别推荐：new_entity_type / relation_solidification / relation_split / standard_upgrade
- 接通 M16 #2 闭环：ISS-Job 注册 Quartz cron → KAP 自动 evaluate → promote/rollback
- 文档 docs/integration/iss-job-config.md 加 "Auto-tune prompt 周度任务" 章节

### M17 #3 · Wiki 编译质量评分
新模块 packages/observability/wiki_quality.py：
- 6 维 LLM-Critic（一致性 / 完整性 / 证据 / 去重 / 时效 / 跨域）
- DIMENSION_WEIGHTS 加权平均得 overall；< 0.6 触发 quality_alert
- LLM 失败返回带 error 字段的 score（不入聚合）
- 维度分越界 → clamp [0, 1]
- 3 API 端点（POST score / GET list / GET aggregate）
- 7 unit 测试（mock）+ 1 live_llm 测试（弱断言）

---

## Commits 时间线

| Commit    | 内容                                                              | 测试           |
|:---|:---|:---:|
| `add1c7b` | #1 前端 i18n 全量铺开（4 页 + 33 keys）                           | +0（既有适配）  |
| `3413494` | #2 自动 tune 定时器接入（ISS-Job 周度推荐 4 jobs）                | +3 后          |
| `(3)`    | #3 Wiki 编译质量评分（6 维 + 3 API）                              | +7 后 +1 live  |

---

## 测试基线

`1012/1014 unit ✓` 后端 + `41 frontend tests passed` + 8 live_llm（默认 deselect）。

---

## M17 已交付

- ✓ 前端 i18n 4 主页面铺开（GovernanceMatrix / MyClaimed / GroundTruthReview / ObservabilityCompare）
- ✓ ISS-Job 周度自动 tune（M11/M12/M16 自学习链 + 定时触发完整闭环）
- ✓ Wiki 6 维质量评分（一致性 / 完整性 / 证据 / 去重 / 时效 / 跨域）

---

## M18 待启动方向

- 独立物理 Neo4j 实例（部署期 — ops 协调）
- ISS-Job 真实环境联调（接通 JWT + 真 ISS Quartz 跑 cron）
- W4 抽取流程 / WikiPage 编译流程接入 wiki_quality 自动评分
- 前端 Wiki 质量看板（接 M17 #3 API + 6 维雷达图）
- 前端 PromptVersion 管理 UI（手动 create / activate / 看 AB 比较）
- portal 反馈原因前端可视化（top_reasons 渲染到 dashboard）
- DecisionLog/QueryLog 时序分区在生产环境实际迁移
