---
title: M16 i18n + 自学习闭环 + 反馈细分 + Wiki 可视化 进度快照
milestone: M16
version: v1
date: 2026-05-01
commits: 4
tests: +15 backend / +12 frontend
hours: ~5
opus-estimate: 14-18h
savings: ~70%
status: completed
tags: [kap, m16]
---

> 进程链：[M0 KAP-Lite](M0-KAP-Lite.md) → ... → [M15 真 LLM 扩展 + 反馈告警 + 多语言](M15-真LLM扩展%2B反馈告警%2B多语言.md) → **【M16 i18n + 自学习闭环 + 反馈细分 + Wiki 可视化】** → M17⬜

# M16 i18n + 自学习闭环 + 反馈细分 + Wiki 可视化（4 commits / ~5h vs Opus 估 14-18h，节省 ~70%）

## 全景成果

### M16 #1 · 前端 i18n 框架
发现既有 LocaleContext + lib/i18n.ts 字典；扩展不重复造轮：
- lib/i18n.ts 新增 13 个 TranslationKey + zh/en 双语
- 新组件 LanguageSwitcher（中 / EN 紧凑按钮组）
- ObservabilityDashboard 接入：6 卡片 title + 标题 + 副标题 + 刷新按钮全 i18n
- 测试 mock useLocale；3 LanguageSwitcher 测试

### M16 #2 · LLM 自学习自动 promote / rollback
M11 #4 / M12 #1 已有 PromptVersion + AB 比较；M16 #2 把分数转动作：
- `auto_promote_best_prompt`：候选 approve_rate ≥ current + 5pp 阈值 → 自动激活
- `auto_rollback_alerting_prompt`：active 跌破 30% 阈值 + 找历史更优版本 → 自动切回
- AutoTuneResult Pydantic（promote / rollback / noop + reason + 旧/新 version_id）
- API POST /prompt-versions/auto-tune（先尝试 rollback，再尝试 promote）
- 8 测试覆盖

### M16 #3 · portal 反馈细分原因（多选标签）
- QueryEvent 加 feedback_reasons: list[str]（推荐 5 标签：wrong_answer / irrelevant / format_issue / outdated / incomplete）
- 最多 8 个；每项 32 字；自动清洗空串
- aggregate_queries 加 feedback_reasons 频次 + top_reasons (top 5)
- PG ALTER 加 feedback_reasons JSONB
- 前端 QueryFeedbackButton：useful=true 直接提交；useful=false 弹多选 chip popup
- 4 backend + 2 frontend 测试

### M16 #4 · Wiki 编译可视化
新组件 WikiHierarchyTree：
- 决策书 §6 Karpathy 三层 Wiki 体系（index → domain_overview → source_summary）
- 拉 fetchWikiPages 后按 page_type + parent_page_id 构造树
- 默认展开前 2 层；点击折叠/展开
- 三层各自配色 + Lucide icon
- 顶部三计数卡（每层 page 数）
- 节点显示 src / cross_ref 数
- 新页 /v15/read/wiki-tree 挂载 + onSelectPage 跳详情页
- 4 smoke 测试

---

## Commits 时间线

| Commit    | 内容                                                       | 测试        |
|:---|:---|:---:|
| M16 #1   | 前端 i18n 框架（扩展既有 LocaleContext + LanguageSwitcher） | +3 前       |
| `a03ada4` | LLM 自学习自动 promote/rollback                           | +11 后      |
| `b9967a1` | portal 反馈细分原因（多选标签）                           | +4 后 +2 前 |
| `(4)`    | Wiki 编译可视化（三层树形）                                | +4 前       |

---

## 测试基线

`1002/1004 unit ✓` 后端 + `41 frontend tests passed` + 7 live_llm（默认 deselect）。

---

## M16 已交付

- ✓ 前端 i18n（zh/en 切换；ObservabilityDashboard 示范）
- ✓ LLM 自学习闭环到端（AB 分数 → 自动 promote / rollback）
- ✓ portal 反馈细分原因（5 推荐标签 + 频次聚合）
- ✓ Wiki 三层结构可视化（决策书 §6 Karpathy）

---

## M17 待启动方向

- 独立物理 Neo4j 实例（部署期 — ops 协调）
- ISS-Job 真实环境联调（接通 JWT + 真 ISS Quartz）
- 前端 i18n 全面铺开（GovernanceMatrix / MyClaimed / GroundTruthReview 等剩余页面）
- 自动 promote/rollback 接定时器（让 ISS-Job 月度 / 周度自动 tune）
- portal 反馈细分原因前端可视化（top_reasons 渲染到 dashboard）
- Wiki 编译质量评分（每页 LLM-Critic 6 维评分 + 阈值告警）
