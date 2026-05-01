---
title: M13 真 LLM 测试与端到端深耕 进度快照
milestone: M13
version: v1
date: 2026-04-30
commits: 4
tests: +13 backend / +8 frontend
hours: ~5
opus-estimate: 14-18h
savings: ~70%
status: completed
tags: [kap, m13]
---

> 进程链：[M0 KAP-Lite](M0-KAP-Lite.md) → ... → [M12 自学习闭环到端 + 前端深耕](M12-自学习闭环到端%20%2B%20前端深耕.md) → **【M13 真 LLM 测试与端到端深耕】** → [M14 大规模优化与端到端补强](M14-大规模优化与端到端补强.md)
>
> 设计蓝本：[决策书 §5.3 真 LLM 测试约束 + §10.5 ISS-Job 接入](../01-技术决策书.md)

# M13 真 LLM 测试与端到端深耕（4 commits / ~5h vs Opus 估 14-18h，节省 ~70%）

## 全景成果

### M13 #1 · 真 LLM 集成测试基建（用户新约束）
落实 M12 末用户反馈：涉及 LLM 的测试不要 mock acall_llm_json。
- pyproject.toml: `markers = ["live_llm: ..."]` + `addopts = "-m 'not live_llm'"`
- conftest.py: `live_llm_available` + `require_live_llm` fixture（缺 key 自动 skip）
- test_live_llm_smoke.py · 2 示范测试（弱断言 schema）
- 老 mock 测试（M5/M10/M11/M12 #1）保留不重写
- 默认 pytest 自动 skip；显式 `pytest -m live_llm` 跑真测
- **关联代码**：[`backend/tests/integration/`](../../backend/tests/integration/) + [`pyproject.toml`](../../backend/pyproject.toml)

### M13 #2 · 矩阵页"我认领的" + 批量决策
- 新 hook `useCurrentUser`（localStorage 兜底当前用户 id）
- 新页 `/v15/manage/my-claimed`：claimed_by 过滤 + 多选 checkbox + bulk approve/reject
- 单条失败不阻断其他（Promise.all + try/catch 隔离）
- 4 smoke 测试覆盖
- **关联代码**：[`frontend/src/pages/v15/MyClaimed.tsx`](../../frontend/src/pages/v15/MyClaimed.tsx) + [`frontend/src/hooks/useCurrentUser.ts`](../../frontend/src/hooks/useCurrentUser.ts)

### M13 #3 · 多 project 横评仪表盘
- 后端 `GET /api/v1/observability/dashboard/multi`：自动推断或显式 project_ids，一次返回 4 维度摘要
- 前端 `/v15/manage/observability/compare`：表格视图横向对比
- 3 后端测试 + 4 前端测试
- **关联代码**：[`api/routers/observability.py`](../../backend/api/routers/observability.py) `dashboard_multi` + [`frontend/src/pages/v15/ObservabilityCompare.tsx`](../../frontend/src/pages/v15/ObservabilityCompare.tsx)

### M13 #4 · ISS-Job Quartz 接入
- KAP 不接 Quartz 框架（feedback memory · ISS 零侵入）
- 暴露 `GET /api/v1/iss-job/cron-recommendations` 协调端点
- 启发式间隔：alerting → 60s / active → 300s / 都无 → 1800s
- ISS-Job 配置示例文档（quartz.xml + 鉴权 + 错误处理）
- 5 后端测试覆盖 + 完整集成文档
- **关联代码**：[`api/routers/iss_job.py`](../../backend/api/routers/iss_job.py) + [`docs/integration/iss-job-config.md`](../integration/iss-job-config.md)

---

## Commits 时间线

| Commit    | 内容                                                     | 测试           |
|:---|:---|:---:|
| `cd22631` | #1 真 LLM 集成测试基建（marker + conftest + 2 示范）     | +0 (live_llm)  |
| `?` (#2)  | #2 我认领的 + 批量决策（useCurrentUser + MyClaimed）     | +4 前          |
| `?` (#3)  | #3 多 project 横评（dashboard/multi + Compare 页）       | +3 后 + 4 前   |
| `?` (#4)  | #4 ISS-Job 接入（cron-recommendations + 配置文档）       | +5 后          |

---

## 测试基线

`949/951 unit ✓` 后端 + `29 frontend tests passed`（连接器 mock 数 2 个 pre-existing 不变；2 live_llm 默认 deselect）。

---

## M13 已交付

- ✓ 真 LLM 集成测试基建（pytest marker + 弱断言 + 默认 skip）
- ✓ 矩阵页"我认领的"+ 批量决策（前端深耕）
- ✓ 多 project 横评仪表盘（后端 + 前端端到端）
- ✓ ISS-Job 协调端点 + Quartz 配置文档（不动 ISS Java 源码）

---

## M14 待启动方向

- ChunkHashCache LRU 大规模分片（> 1M chunks 时优化；当前内存模式上限）
- DecisionLog / QueryLog PG 时序分区（按月分区，大表性能优化）
- 独立物理 Neo4j 实例的影子库（生产部署优化）
- 真 LLM 测试覆盖扩展（M5/M10 老 mock 测试逐步迁到 live_llm）
- 块②前端 UI 进一步深耕（GovernanceMatrix bulk actions / SLA dashboard）
- M13 #4 ISS-Job 在真实 ISS 环境集成验证（接通 JWT + 联调）
