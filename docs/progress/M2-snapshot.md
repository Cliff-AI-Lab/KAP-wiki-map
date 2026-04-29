---
title: M2 AI native 进度快照
milestone: M2
version: v2
date: 2026-04-29
commits: 7
tests: +73
hours: ~5
opus-estimate: 30h
savings: 83%
status: completed
tags: [kap, m2]
---

> [← M1 企业级 v1](M1-snapshot.md) · 设计蓝本：[决策书 §5.5 D13 双 Agent + §5.4 脱敏 + §4 块①](../01-技术决策书.md) / [PRD §3 块①](../02-产品需求PRD.md) · [→ M3 高级治理](M3-snapshot.md)

# M2 AI native（7 commits / ~5h vs Opus 估 30h，节省 83%）

> LLM-Critic 6 维 + W1 脱敏 hook + GraphView obsidian 风格 + 块① 咨询智能体（KAP 三块产品形态全部就位）

---

## 全景成果

### LLM-Critic 6 维质疑（[决策书 §5.5 D13 lite](../01-技术决策书.md)）
单 LLM 调用 6 维质疑（一致性/完整性/证据强度/重复性/时效性/跨域），CriticResult 含 findings + overall_severity + has_blocking_issue()；轻量化路线 — 不接 pipeline 主路径，**只在 W4 写入侧 hook（低置信度兜底场景）调用**，符合"AI native + 人工兜底"；critic blocking 触发工单 priority +20。
- **关联代码**：[`packages/distillation/agents/critic.py`](../../backend/packages/distillation/agents/critic.py)

### W1 脱敏接入（[决策书 §5.4 D10](../01-技术决策书.md)）
ingest 主路径在 RawStore 保存原文之后调 `redact_and_persist_doc`，doc.content 就地替换为脱敏文 + mapping 写加密 KV；pipeline 后续基于脱敏文做嵌入 + 入库（向量库不存原文）；新增 `/api/v1/sensitive/decode/{mapping_id}` 高密解码端点（`RequireAccessLevel(CONFIDENTIAL)` + 每次访问写审计日志）。
- **关联代码**：[`packages/sensitive/ingest_hook.py`](../../backend/packages/sensitive/ingest_hook.py) / [`api/routers/sensitive.py`](../../backend/api/routers/sensitive.py)

### GraphView obsidian 升级（用户反馈兑现）
增量改造不重写 — canvas `shadowBlur` 柔光外发光（选中 22 / 聚焦 10）+ 染色维度三模式 toggle（社区 Louvain / 实体类型 8 类 / 中心性 3 档梯度）+ 详情面板 + 图例联动；保留所有既有交互（拖拽 / 1-hop / 搜索 / 推理虚线）。
- **关联前端**：[`frontend/src/pages/v15/GraphView.tsx`](../../frontend/src/pages/v15/GraphView.tsx)

### 块① 知识咨询智能体（[决策书 §4](../01-技术决策书.md) / [PRD §3](../02-产品需求PRD.md) lite，KAP AI native 旗舰）
- 对话状态机 4 阶段：identify → propose → refine → export
- industry_recognizer 两阶段（Stage 1 conf ≥ 0.7 跳过 LLM，省成本；Stage 2 LLM 在 top 3 候选中选）+ 防 LLM 幻觉
- taxonomy_builder 主树提议（只动 L2 不重写 L3/L4，全 drop 兜底保全）+ 自然语言 CRUD（中文 regex：删除/重命名/新增）
- exporter 导出 IndustryTemplate（自动避免覆盖基础模板加 -custom-{uuid}）+ YAML/JSON 序列化
- 5 API 端点（sessions / message / draft / export）+ RequireRole(DG)（决策书 §4.1 锁 DG 主导建体系）
- 不上 LangGraph 等重框架；内存 session store；M3 接 PG 持久化
- **关联代码**：[`packages/architect/`](../../backend/packages/architect/)（agent / industry_recognizer / taxonomy_builder / exporter / prompts） / [`api/routers/architect.py`](../../backend/api/routers/architect.py)

---

## Commits 时间线

| Commit  | 内容                                           | 测试   |
|:---|:---|:---:|
| `6175808` | **#1 LLM-Critic 6 维质疑** · prompt + sync/async 双轨 + 容错 + W4 hook 集成 | +16 ✓ |
| `b9cca04` | **#2 W1 脱敏 ingest hook** · redact_and_persist_doc + /sensitive/decode 高密解码 + 审计日志 | +8 ✓  |
| `ca544be` | **#3 GraphView obsidian 风格升级** · 柔光外发光 + 染色维度切换（社区/类型/中心性） | —     |
| `98e03b0` | **#4 块① 批 1** · ArchitectAgent 状态机骨架 | +14 ✓ |
| `8385745` | **#4 块① 批 2** · industry_recognizer 两阶段 | +11 ✓ |
| `2788acf` | **#4 块① 批 3** · taxonomy_builder + exporter | +18 ✓ |
| `6bdac2d` | **#4 块① 批 4** · API endpoints | +9 ✓  |

---

## 测试基线

`503/505 unit ✓`（V15 mock drift 仍 2 个）

---

## KAP 三块产品形态全部就位

- **块①** 咨询智能体（M2 #4，对话式建体系，旗舰）
- **块②** 治理底座（M0+M1，6 工位 + 4×6 矩阵 + 脱敏）
- **块③** 消费门户（M0+M2，三路召回 + obsidian 图谱）
