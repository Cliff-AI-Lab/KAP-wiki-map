---
title: M18 Wiki 质量闭环 + 前端管理面板 进度快照
milestone: M18
version: v1
date: 2026-05-01
commits: 4
tests: +4 backend / +10 frontend
hours: ~4
opus-estimate: 14-18h
savings: ~75%
status: completed
tags: [kap, m18]
---

> 进程链：[M0 KAP-Lite](M0-KAP-Lite.md) → ... → [M17 i18n 铺开 + 自动 tune + Wiki 质量评分](M17-i18n铺开%2B自动tune%2BWiki质量.md) → **【M18 Wiki 质量闭环 + 前端管理面板】** → M19⬜

# M18 Wiki 质量闭环 + 前端管理面板（4 commits / ~4h vs Opus 估 14-18h，节省 ~75%）

## 全景成果

### M18 #1 · WikiCompiler 自动评分（编译即评分）
- `wiki_compiler.WikiCompiler.__init__` 加 `auto_score: bool = True`
- 抽 `_try_score_page(page, project_id)`：调 M17 #3 `score_wiki_page` + LLM 失败兜底（log warning，不阻塞编译）
- `compile_source` / `compile_domain` upsert 后挂自动评分
- `quality_alert` 命中时 log warning，接告警链
- 4 单测：自动评分挂上 / 评分失败兜底 / 关闭开关 / domain 也触发

### M18 #2 · 前端 Wiki 质量看板（6 维雷达图）
- `observabilityApi.ts` 加 2 API：`fetchWikiQualityAggregate` / `fetchWikiQualityList` + 类型
- 新页 `WikiQualityDashboard`：
  - 聚合卡（total_scored / alerting_count / avg_overall）
  - recharts RadarChart 6 维雷达
  - 告警清单表（quality_alert=true 高亮 + 只看告警过滤）
- i18n 加 23 个 wq.* TranslationKey + zh/en 双语
- 路由 `/v15/manage/observability/wiki-quality`
- 3 smoke 测试（render / empty / error）

### M18 #3 · 前端 PromptVersion 管理 UI
- `observabilityApi.ts` 加 5 个 API：list / create / deactivate / AB / auto-tune + 类型
- 新页 `PromptVersionManager`：
  - 顶部 condition / language 过滤 + 新建 / auto-tune 按钮
  - 版本列表（active 高亮 + 停用按钮 + confirm 弹窗）
  - AB 比较 tab（sample_size + approve_rate 表）
  - 内嵌 CreateForm（condition / language / system_prompt / note）
  - AutoTuneBanner（promote / rollback / noop）
- i18n 加 28 个 pv.* TranslationKey + zh/en 双语
- 路由 `/v15/manage/observability/prompts`
- 5 smoke 测试（list / AB / auto-tune / deactivate / error）

### M18 #4 · portal 反馈原因 Top 5 前端可视化
- `QueriesAggregate` 加 feedback_reasons / top_reasons（M16 #3 后端已聚合）
- ObservabilityDashboard 内嵌 `FeedbackReasonsPanel`：
  - top 5 反馈原因横条（按频次降序，宽度比例填充）
  - 显示总负反馈样本数
  - feedback_reasons 为空时整个面板隐藏（不破坏既有布局）
- i18n 加 3 个 observ.feedbackReasons.* TranslationKey + zh/en
- 既有 4 个 dashboard 测试不破 + 2 新（present / hidden）

---

## Commits 时间线

| Commit    | 内容                                         | 测试      |
|:---|:---|:---:|
| `4784af2` | #1 WikiCompiler 自动评分（编译即评分）        | +4 后     |
| `d42186d` | #2 前端 Wiki 质量看板（6 维雷达图）           | +3 前     |
| `106ba12` | #3 前端 PromptVersion 管理 UI                 | +5 前     |
| `ebed2b8` | #4 portal 反馈原因 Top 5 前端可视化           | +2 前     |

---

## 测试基线

`1016/1018 unit ✓` 后端 + `51 frontend tests passed` + 8 live_llm（默认 deselect）。

---

## M18 已交付

- ✓ Wiki 编译流水线内置自动 6 维质量评分（M17 #3 → 闭合到 wiki_compiler）
- ✓ 前端 Wiki 质量看板（recharts 雷达图 + 告警清单）
- ✓ 前端 PromptVersion 管理 UI（list / AB / auto-tune / 创建 / 停用）
- ✓ portal 反馈原因 Top 5 横条统计（接 M16 #3 后端聚合）

---

## M19 待启动方向

- 独立物理 Neo4j 实例（部署期 — ops 协调）
- ISS-Job 真实环境联调（接通 JWT + 真 ISS Quartz 跑 cron）
- W4 抽取 / chunk 处理流程内置 wiki_quality 链式触发（不仅 wiki 编译，全流程"自动诊断"）
- Wiki 质量评分 PG 持久化（_scores 当前是内存字典；M19 上 PG 落库 + 历史趋势）
- Wiki 质量趋势图 / 对比版本（接 M18 #2 雷达图 + 时间序列）
- prompt_versions 进一步 UI 增强（多版本 diff / system_prompt 全文对比）
- 真 LLM 测试覆盖继续扩展（迁老 mock：condition_health / evolution_proposer 等）
- DecisionLog/QueryLog 时序分区生产环境实际迁移（M14 已备 DDL 工具）
