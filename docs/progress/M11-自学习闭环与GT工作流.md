---
title: M11 自学习闭环与 GT 工作流 进度快照
milestone: M11
version: v1
date: 2026-04-30
commits: 4
tests: +24 backend / +8 frontend
hours: ~5
opus-estimate: 14-18h
savings: ~70%
status: completed
tags: [kap, m11]
---

> 进程链：[M0 KAP-Lite](M0-KAP-Lite.md) → [M1 企业级 v1](M1-企业级v1.md) → [M2 AI native](M2-AI-native.md) → [M3 高级治理](M3-高级治理.md) → [M4 重抽影子库](M4-重抽影子库.md) → [M5 演化机制完整版](M5-演化机制完整版.md) → [M6 演化收尾](M6-演化收尾.md) → [M7 运营观察持久化](M7-运营观察持久化.md) → [M8 反馈与召回评估](M8-反馈与召回评估.md) → [M9 评估持久化与趋势告警](M9-评估持久化与趋势告警.md) → [M10 评估深化与前端仪表盘](M10-评估深化与前端仪表盘.md) → **【M11 自学习闭环与 GT 工作流】** → M12⬜
>
> 设计蓝本：[决策书 §5.3 GT 工作流闭环 + LLM 自学习](../01-技术决策书.md)

# M11 自学习闭环与 GT 工作流（4 commits / ~5h vs Opus 估 14-18h，节省 ~70%）

## 参考项目引用

### 🟠 [Wiki-map V15](../../_refs/wiki-map/bookworm-agent/)
- M11 #2/#3 前端单测 + GT 审批 UI 沿用 V15 [`pages/v15/`](../../frontend/src/pages/v15/) 的 Tailwind theme + Lucide icons
- 路由 `/v15/manage/ground-truth` 复用 V15 一体化布局

### 🔴 [ISS 参考项目](../../_refs/iss-kb/) — M11 不直接引用代码

> 自学习闭环 + GT 工作流闭环 — M10 #1 的 lite 缺口收口 + 前端测试基建 + LLM 调优追踪

---

## 全景成果

### M11 #1 · QueryEvent retrieved_doc_ids + GT 自动构造完整化
- QueryEvent 加 `retrieved_doc_ids: list[str]`（M10 #1 lite 留的缺口）
- qa.ask_question hook 传 `[s.doc_id for s in result.sources]`
- PG ALTER TABLE ADD COLUMN IF NOT EXISTS（兼容老库）
- `_compute_proposed_doc_ids` 三策略：
  - 交集（≥ 2 useful 实例）
  - 频次降序 union（交集为空兜底）
  - 空兜底（老数据无 retrieved_doc_ids）
- candidate.reasoning 标注 strategy 来源
- **关联代码**：[`packages/observability/query_log.py`](../../backend/packages/observability/query_log.py) + [`recall_eval.py`](../../backend/packages/observability/recall_eval.py)

### M11 #2 · 前端单测框架 + Dashboard smoke
- vitest 4 + @testing-library/react 16 + happy-dom 20
- vite.config.ts 加 `test: { environment: 'happy-dom', globals, setupFiles }`
- src/test/setup.ts 引入 `@testing-library/jest-dom/vitest`
- npm `test` / `test:watch` scripts
- ObservabilityDashboard.test.tsx · 4 测试（mock 三 fetch + 6 卡片渲染 + 单卡片失败容错）
- **关联代码**：[`frontend/vite.config.ts`](../../frontend/vite.config.ts) + [`pages/v15/ObservabilityDashboard.test.tsx`](../../frontend/src/pages/v15/ObservabilityDashboard.test.tsx)

### M11 #3 · GT 候选确认入库 UI（决策书 §5.3 SME 工作流闭环）
- 新页 `/v15/manage/ground-truth`
- 拉 `auto-construct` 候选 → SME inline-edit `expected_doc_ids` → Confirm 入库 / Skip 隐藏
- 已入库 GT 列表 + 删除按钮
- min_useful_rate / min_samples 阈值实时调节
- observabilityApi 扩展 4 个 fetch（candidates / list / add / delete）
- 4 smoke 测试覆盖
- **关联代码**：[`frontend/src/pages/v15/GroundTruthReview.tsx`](../../frontend/src/pages/v15/GroundTruthReview.tsx)

### M11 #4 · LLM 自学习闭环 lite（决策书 §5.3 prompt 调优追踪）
M10 #2 给的是建议；M11 #4 让 SME 真切换 prompt 后能 AB 比较新旧 prompt SME 接受率：
- PromptVersion (condition_type / excerpt / activated_at / deactivated_at | None)
- 4 条件每个同时最多一个 active；create 时自动停用旧 active
- compute_prompt_ab_score：把 proposals.created_at 落到对应版本时间窗算 approve_rate
- 不实际改 evolution_proposer 硬编码 prompt（仅元数据 + 比较层）
- 4 API 端点（GET 列表 / POST 创建 / POST 停用 / GET AB 比较）
- **关联代码**：[`packages/observability/prompt_versions.py`](../../backend/packages/observability/prompt_versions.py)

---

## Commits 时间线

| Commit    | 内容                                                                  | 测试     |
|:---|:---|:---:|
| `d9cea29` | #1 QueryEvent retrieved_doc_ids + GT 自动构造完整化（三策略）         | +7 ✓     |
| `d4bc1e2` | #2 前端单测框架（vitest + RTL + happy-dom）+ Dashboard smoke          | +4 前端  |
| `2d3297e` | #3 GT 候选确认入库 UI + 4 fetch + 4 smoke 测试                        | +4 前端  |
| `a01ccb9` | #4 LLM 自学习闭环（PromptVersion + AB 比较 + 4 端点）                 | +17 ✓    |

---

## 测试基线

`928/930 unit ✓` (+24 后端) + `8 frontend tests passed`（连接器 mock 数 2 个 pre-existing 不变）。

- M11 #1：[`test_query_log.py`](../../backend/tests/unit/test_query_log.py) +3 + [`test_recall_eval.py`](../../backend/tests/unit/test_recall_eval.py) +4
- M11 #2：[`ObservabilityDashboard.test.tsx`](../../frontend/src/pages/v15/ObservabilityDashboard.test.tsx) · 4 测试
- M11 #3：[`GroundTruthReview.test.tsx`](../../frontend/src/pages/v15/GroundTruthReview.test.tsx) · 4 测试
- M11 #4：[`test_prompt_versions.py`](../../backend/tests/unit/test_prompt_versions.py) · 12 + [`test_observability_api.py`](../../backend/tests/unit/test_observability_api.py) · +5

---

## M11 已交付

- ✓ QueryEvent retrieved_doc_ids（M10 #1 lite 缺口收口）
- ✓ GT 自动构造完整化（交集 / union / 空 三策略）
- ✓ 前端单测框架（vitest + RTL + happy-dom）+ Dashboard smoke
- ✓ GT 候选确认入库 UI + SME 完整工作流
- ✓ LLM 自学习闭环 lite（PromptVersion + AB 比较）
- ✓ 8 前端测试 + npm test 一键运行

---

## M12 待启动方向

- PromptVersion PG 持久化（同 pg_decision_log 模式）
- LLM 自学习闭环完整版（evolution_proposer 在调 LLM 时根据 active version 动态拼 prompt）
- 块② 4×6 矩阵审核 UI 完整收尾（前端进度仍落后于后端）
- portal "有用 / 无用" 按钮埋点（前端，对接 M8 #1 后端反馈端点）
- 前端 ObservabilityDashboard 加趋势曲线图（chart 库选型）
- 独立物理 Neo4j 实例的影子库（生产部署优化）
- ChunkHashCache LRU 大规模分片（> 1M chunks 优化）
- DecisionLog / QueryLog PG 时序分区
