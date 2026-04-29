---
title: M1 企业级 v1 进度快照
milestone: M1
version: v1
date: 2026-04-29
commits: 10
tests: +177
hours: ~7.5
opus-estimate: 60-80h
savings: ~90%
status: completed
tags: [kap, m1]
---

> [← M0 KAP-Lite](M0-snapshot.md) · 设计蓝本：[决策书 §8.1 RBAC + §5.2 D6 矩阵](../01-技术决策书.md) / [PRD §6.1 + §10.4](../02-产品需求PRD.md) · [→ M2 AI native](M2-snapshot.md)

# M1 企业级 v1（10 commits / ~7.5h vs Opus 估 60-80h，节省 ~90%）

> ISS 集成 + 4×6 矩阵审核台 + W4 写入侧 + 敏感脱敏 + 制造 Facet + 矩阵 UI

---

## 全景成果

### ISS 集成（零侵入）
决策书 §9.1 写"100% 复用 iss-common-*"假设 Java 业务层，但 KAP backend 是 Python — 改走**协议层接入**：
- HS512 JWT 验签 + 共享 ISS Redis 拿 LoginUser
- HTTP 调 RemoteUser/Dept
- 不改 ISS 任何 Java 源码 / 数据库 schema / 二方包
- AuthMiddleware 三模式 dispatch（dev=API Key / sandbox=JWT 验签 / prod=网关 header 信任）
- **关联代码**：[`packages/auth/`](../../backend/packages/auth/)（iss_jwt / iss_session / iss_models / iss_remote_client / data_scope）
- **关联部署文档**：[M1-iss-integration.md](../M1-iss-integration.md)

### DataScope 5 级（决策书 §8.1）
Python 函数式等价（不复刻 ISS MyBatis SQL 拼接）；retriever 后过滤 RBAC 循环里激活；W4 写入侧补 dept_id/created_by 后真生效，老文档透明放行保 M0 兼容。
- **关联代码**：[`packages/auth/data_scope.py`](../../backend/packages/auth/data_scope.py) / [`retrieval/retriever.py`](../../backend/packages/retrieval/retriever.py)

### 4×6 矩阵审核台（决策书 §5.2 D6）
4 角色（DG/SME/SEC/AIOps）× 6 工位（W1-W6）R/C/I 表代码化；GovernanceQueueItem 加 8 字段；claim/escalate/list_matrix/find_overdue 操作；D12 SLA sweep 自动升级（AIOps→SME→DG，DG 顶级触发"积压告警"）。
- **关联代码**：[`packages/governance/matrix.py`](../../backend/packages/governance/matrix.py) / [`sla.py`](../../backend/packages/governance/sla.py) / [`distillation_hook.py`](../../backend/packages/governance/distillation_hook.py)
- **关联前端**：[`frontend/src/pages/v15/GovernanceMatrix.tsx`](../../frontend/src/pages/v15/GovernanceMatrix.tsx)

### W4 写入侧蒸馏 hook
M0 坑 3 已标 `needs_review`，M1 在 [`api/routers/knowledge.py`](../../backend/api/routers/knowledge.py) 双写到 4×6 矩阵；workstation=W4 → assigned_role=SME（必审锁定）；priority 与 confidence 反相关。

### 敏感脱敏管线 lite（决策书 §5.4 D10/D11）
NER 三类（人名 / 工艺参数 / 客户名）+ Redactor 三策略（角色化 / 三级降精度 / 代码化）+ AES-256-GCM 加密 KV。
- **关联代码**：[`packages/sensitive/`](../../backend/packages/sensitive/)（ner / redactor / mapping_store）

### 制造 Facet schema（[PRD §10.4 1129](../02-产品需求PRD.md)）
4 套（equipment_fault / process_standard / sop / quality_record），每套 6-10 字段 + 敏感字段标记 + primary_role；通过 IndustryTemplate.facets dict 注册。
- **关联代码**：[`packages/templates/facets_manufacturing.py`](../../backend/packages/templates/facets_manufacturing.py)

### 矩阵审核台前端 UI
4×6 网格（CSS Grid）+ R/C/I 标记 + 角色染色（DG=蓝/SME=橙/SEC=红/AIOps=绿，柔光发光）+ 待办>0 脉冲动画 + 抽屉滑入工单列表 + 5 操作（认领/通过/驳回/改/升级）+ SLA Tag。

---

## Commits 时间线

| Commit | 内容 | 测试 |
|---|---|:---:|
| `4a4206a` | **ISS 集成 批 1** · JWT 验签 + UserContext + AuthMiddleware 三模式 dispatch | +21 ✓ |
| `f942a1c` | **ISS 集成 批 2-4 合并** · DataScope 5 级 + dept descendants + 部署文档 | +19 ✓ |
| `3faf120` | **矩阵审核台 批 1** · types 扩展 + 4×6 R/C/I 规则函数 | +49 ✓ |
| `8435c8a` | **矩阵审核台 批 2** · Store 扩展 + SLA 超时升级 sweep | +16 ✓ |
| `bc7daba` | **矩阵审核台 批 3** · API 端点 (matrix/claim/escalate) | +10 ✓ |
| `f73dbe1` | **W4 写入侧 hook** · 蒸馏管线 → 4×6 矩阵双写 | +7 ✓  |
| `99a2101` | **DataScope 激活** · documents.dept_id/created_by 落地 | +5 ✓  |
| `8f97725` | **#1 敏感脱敏管线** · NER + Redactor + AES-256-GCM 加密 KV | +29 ✓ |
| `92fd61c` | **#2 制造 Facet 模板** · 4 套 schema (设备故障/工艺/SOP/质量) | +21 ✓ |
| `6a6e73a` | **#3 矩阵审核台前端 UI** · 4×6 网格 + 抽屉 + 角色染色 | —     |

---

## 测试基线

`427/429 unit ✓`（V15 dingtalk/wecom mock drift 仍 2 个）

---

## M2 启动条件（M1 已交付）

- ✓ ISS 三模式认证 + DataScope 5 级激活
- ✓ 4×6 矩阵审核台后端 + 前端
- ✓ W4 写入侧 dept_id / created_by 持久化
- ✓ 敏感脱敏离线工具集（NER + Redactor + 加密 KV）
- ✓ 制造行业 Facet schema 4 套
