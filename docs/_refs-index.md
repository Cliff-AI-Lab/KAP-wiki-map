---
title: 参考资料索引
type: kap-meta-doc
related-projects:
  - Wiki-map V15
  - ISS 知识库
status: living-document
---

# 参考资料索引（Wiki-map V15 + ISS 知识库）

> **目的**：为 KAP 项目的两个上游参考项目建立 Obsidian 图谱关联节点，
> 修复"乱码 + 孤岛"问题，让所有源文档能被 Obsidian / Claude / 团队成员从单一入口检索。
>
> **使用方式**：本文档是图谱中心节点，所有 `_refs/` 下的关键文档都通过相对链接
> 引用进来，Obsidian 会自动构建反向关系。

## 与 KAP 主线的关系

```
KAP 主线文档                    本索引                  _refs 上游项目
─────────────────────────────────────────────────────────────────
docs/01-技术决策书.md      ──┐
docs/02-产品需求PRD.md     ──┼──> docs/_refs-index.md ──┬──> _refs/wiki-map/...
docs/M0-tech-debt.md       ──┘                          └──> _refs/iss-kb/...
docs/M0-tech-debt-async-plan.md
```

- 决策书 §9 复用清单引用本索引
- M0-tech-debt 的"踩坑分析"基于 [Wiki-map V15 优化记录](#wiki-map-v15-文档总览)
- PRD §10.4 复用细则按本索引的模块清单展开

---

## Wiki-map V15 — KAP 后端 + 前端起点

### 项目定位

[Wiki-map V15（bookworm-agent）](../_refs/wiki-map/bookworm-agent/) 是 KAP **AI 内核原型**。
KAP 后端 / 前端代码起点直接拉自该项目主干（决策书 §9.2 标注 ~35% 复用率）。

**复用现状**：
- `backend/packages/distillation/`、`backend/packages/governance/` 直接演进
- `backend/packages/storage/` 改造（Neo4j 持久化 / 双向量 / EmbeddingProvider）
- `frontend/src/` 直接复用 V15 双模式 + Karpathy Wiki + 力导向图

### Wiki-map V15 文档总览

| 类型 | 文档 | 与 KAP 的关联 |
|---|---|---|
| 架构（V8 历史）| [v8-design.md](../_refs/wiki-map/bookworm-agent/docs/v8-design.md) | V8 是 V15 的前身，含 SkillsRouter / GraphStore 双向索引设计 |
| 架构详细 | [v8-detailed-design.md](../_refs/wiki-map/bookworm-agent/docs/v8-detailed-design.md) | 各模块详细设计，KAP 改造时对照 |
| 架构（V8 全貌）| [architecture.md](../_refs/wiki-map/bookworm-agent/docs/architecture.md) | 全栈分层依赖图，KAP backend/ 起点 |
| 架构（V15 终态）| [v15-summary.md](../_refs/wiki-map/bookworm-agent/docs/v15-summary.md) | V15 完整能力清单（双模式 / 5 治理 Agent / Karpathy Wiki）|
| 系统全景 | [v15-system-map.md](../_refs/wiki-map/bookworm-agent/docs/v15-system-map.md) | Mermaid 全景 + 5 条核心穿透链 |
| 优化日志 | [optimization-log.md](../_refs/wiki-map/bookworm-agent/docs/optimization-log.md) | 已完成与待办优化项，**KAP M0 技术债务地图直接基于此**（[M0-tech-debt.md](./M0-tech-debt.md)）|
| 能源行业实测 | [energy-test-results.md](../_refs/wiki-map/bookworm-agent/docs/energy-test-results.md) | V7 能源 53 域端到端测试，**KAP 能源行业模板基线**（KEEP 率 42% 是坑 3 改造由头）|
| 团队仿真 | [team-simulation.md](../_refs/wiki-map/bookworm-agent/docs/team-simulation.md) | 多角色协作 demo（KAP 4 角色矩阵审核台思想源头之一）|

### Wiki-map V15 测试数据样本（已修复 GBK 乱码）

四个行业各一组制度 / 流程 / 技术 / 应急样本，KAP 行业模板包验证可直接复用：

| 行业 | 路径 | 文件数 | 用途 |
|---|---|---|---|
| 能源（V7 早期）| [test_data/energy](../_refs/wiki-map/bookworm-agent/test_data/energy) | 18（txt/md/docx）| 决策书 §7.2 能源 L1 主树骨架来源 |
| 能源（V15 增补）| [test_data/energy_v15_extra](../_refs/wiki-map/bookworm-agent/test_data/energy_v15_extra) | 5（多格式）| V15 阶段补的真实场景样本 |
| 能源（V12 重制）| [test_docs/energy_v12](../_refs/wiki-map/bookworm-agent/test_docs/energy_v12) | 10（txt/md）| 安全/化工/环保/特种设备/电气/消防/危化/职业健康/节能/设备点检 — KAP 能源 53 域映射对照 |
| 制造 | [test_docs/manufacturing](../_refs/wiki-map/bookworm-agent/test_docs/manufacturing) | 5 | ISO9001 / 供应商评审 / 注塑作业 / 生产安全 / 设备维护 — KAP 制造模板基线 |
| 金融 | [test_docs/finance](../_refs/wiki-map/bookworm-agent/test_docs/finance) | 5 | 灾备 / 信贷 / 反洗钱 / 投诉 / 理财 — KAP 金融模板（M2+ 扩展）|
| IT | [test_docs/it](../_refs/wiki-map/bookworm-agent/test_docs/it) | 5 | 代码审查 / 信息安全 / 微服务 / 敏捷 / DBA — KAP IT 模板（M2+ 扩展）|

> **乱码修复记录**：原始 ZIP 解压时 GBK 文件名被 unzip 误解为 cp437 → unicode 失真。
> [`scripts/fix_refs_mojibake.py`](../scripts/fix_refs_mojibake.py) 用 `zipfile.metadata_encoding='gbk'` 重提取修复。

---

## ISS 知识库 — KAP 企业级底座

### 项目定位

[ISS 知识库（iss-ai-knowledge）](../_refs/iss-kb/iss-ai-knowledge/) 是软通智能 AI 中台，
为 KAP 提供**企业级 RBAC + 数据权限 + 多模态解析 + 微服务底座**（决策书 §9.1 标注 ~20% 复用率）。

**复用现状**：
- `iss-gateway / iss-auth / iss-system / iss-job / iss-monitor / iss-file / iss-common`
  作为 KAP 部署的 Java 微服务底座（私有化必备）
- `iss-knowledge-parser` 作为 W1 工位多模态解析（PDF/Word/Excel/PPT/图/音/视）
- `iss-common-datascope` 5 级数据权限是 KAP RBAC 中间件骨架（坑 7）的对接目标

### ISS 模块清单（按职能分组）

#### 业务核心（KAP 替换 / 部分复用）

| 模块 | 类型 | 文档 | KAP 关系 |
|---|---|---|---|
| `iss-ai-knowledge-management` | Java 业务模块 | _无 README_ | KAP 用 `KAP-Knowledge-Core`（Python，基于 V15 演进）替代 |
| `iss-ai-knowledge-integration` | Java 集成模块 | _无 README_ | KAP 用 Python AI 层替代 |
| `iss-knowledge-parser` | **Python FastAPI 解析服务** | [ARCHITECTURE.md](../_refs/iss-kb/iss-ai-knowledge/iss-knowledge-parser/docs/ARCHITECTURE.md) · [DEVOPS.md](../_refs/iss-kb/iss-ai-knowledge/iss-knowledge-parser/docs/DEVOPS.md) · [README.md](../_refs/iss-kb/iss-ai-knowledge/iss-knowledge-parser/docs/README.md) | **直接复用 W1 工位**：多模态解析（DashScope qwen-vl/audio）+ Milvus 集成 + 多对象存储抽象 |
| `iss-ai-knowladge-web` _(注：原项目拼写错误)_ | Java 前端代理 | [README.md](../_refs/iss-kb/iss-ai-knowledge/iss-ai-knowladge-web/README.md) | KAP 用 React 19 + Vite 前端替代 |

#### 基础设施服务（KAP 直接复用）

| 模块 | 类型 | 文档 | KAP 关系 |
|---|---|---|---|
| `iss-gateway` | Spring Cloud Gateway | _无 README_ | **直接复用**：路由 / 鉴权 / 限流 |
| `iss-auth` | 认证服务 | [项目详细设计文档](../_refs/iss-kb/iss-ai-knowledge/iss-auth/ISS-Auth%20%E8%AE%A4%E8%AF%81%E6%9C%8D%E5%8A%A1%20%E2%80%94%20%E9%A1%B9%E7%9B%AE%E8%AF%A6%E7%BB%86%E8%AE%BE%E8%AE%A1%E6%96%87%E6%A1%A3%20.md) · [二方包详细介绍](../_refs/iss-kb/iss-ai-knowledge/iss-auth/二方包详细介绍.md) | **直接复用**：JWT + Redis 会话 + IP 黑名单 + 重试锁定（决策书 §9.1）|
| `iss-system` | 系统管理（用户/角色/部门）| [项目详细设计](../_refs/iss-kb/iss-ai-knowledge/iss-system/ISS-System项目详细设计文档.md) · [README](../_refs/iss-kb/iss-ai-knowledge/iss-system/README.md) · [AGENTS](../_refs/iss-kb/iss-ai-knowledge/iss-system/AGENTS.md) · [二方包详细介绍](../_refs/iss-kb/iss-ai-knowledge/iss-system/二方包详细介绍.md) | **直接复用**：13 Controller + 111 API + 16 表（用户/角色/部门/菜单/字典/操作日志），KAP 4 角色挂在 `sys_role` |
| `iss-job` | Quartz 定时任务 | _无 README_ | **直接复用**：全量重抽 + Agent 定时触发 |
| `iss-monitor` | Skywalking + OTEL | _无 README_ | **直接复用**：APM + 全链路追踪 |
| `iss-file` | 多对象存储抽象 | _无 README_ | **直接复用**：OBS/OSS/MinIO/S3/COS 切换（私有化必备）|
| `iss-common` | 二方包集合 | [README](../_refs/iss-kb/iss-ai-knowledge/iss-common/README.md) · [二方包介绍](../_refs/iss-kb/iss-ai-knowledge/iss-common/二方包介绍.md) · [二方包详细介绍](../_refs/iss-kb/iss-ai-knowledge/iss-common/二方包详细介绍.md) · [数据权限详解](../_refs/iss-kb/iss-ai-knowledge/iss-common/数据权限详解.md) | **直接复用**：core/redis/security/log/datascope/sensitive/seata/datasource/swagger 全套二方包 |

### ISS 二方包内部依赖（解读）

`iss-common` 的子模块依赖关系（来自 [二方包详细介绍](../_refs/iss-kb/iss-ai-knowledge/iss-common/二方包详细介绍.md)）：

```
iss-common-core            (基石，被所有模块依赖)
   │
   ├──> iss-common-redis        (Redisson 分布式锁 + 缓存)
   ├──> iss-common-swagger      (OpenAPI 3.0)
   ├──> iss-common-security     (JWT + RBAC 注解，依赖 redis + api-system)
   │      ├──> iss-common-datascope    (5 级数据权限 AOP)
   │      └──> iss-common-log          (操作日志 + OTEL)
   ├──> iss-common-sensitive    (Jackson 序列化层数据脱敏 — KAP 坑 D 双层存储基础)
   ├──> iss-common-seata        (分布式事务 — KAP 双库切换用)
   ├──> iss-common-datasource   (Dynamic-DS 多数据源 — KAP 全量重抽影子库切换用)
   └──> iss-common-rabbitmq     (MQ — 暂未在 KAP 主流程使用)
```

**KAP 的对接策略**（决策书 §9.1）：

- 引入 `iss-common-security` + `iss-common-datascope` → 完成 KAP 坑 7 RBAC 骨架的对接
- 引入 `iss-common-sensitive` → KAP 块② 敏感实体脱敏的"展示侧"序列化拦截
- 引入 `iss-common-datasource` → KAP 块② 全量重抽的影子库切换
- 引入 `iss-common-log` + OTEL → KAP 全链路审计

### ISS 数据权限要点

最关键的 ISS 文档之一：[数据权限详解](../_refs/iss-kb/iss-ai-knowledge/iss-common/数据权限详解.md)。

5 级数据权限（基于 `@DataScope` AOP + 动态 SQL 拼接）：

| 级别 | 含义 | 适用 |
|---|---|---|
| 1 | 全部数据 | 公司级管理者 |
| 2 | 自定义部门集合 | 跨部门协作角色 |
| 3 | 仅本部门 | 部门内管理者 |
| 4 | 本部门 + 子部门（FIND_IN_SET ancestors）| 部门经理/总监 |
| 5 | 仅本人 | 普通员工 |

**KAP 决策书 §8.1 直接采用**，并在此之上叠加"密级"维度（公开/内部/秘密/机密）。

### 已忽略的 ISS 内部噪音

以下文件被 Obsidian 索引但不属于 KAP 关注范围：

- `iss-system/.opencode/...` — opencode 工具本地缓存（非 ISS 业务文档）
- `__MACOSX/*` — macOS 解压垃圾（已通过 .gitignore 排除）

---

## 链接索引（Obsidian 图谱反向关联用）

本节列出从本索引出发能跳转到的所有上游文档，方便 Obsidian 反向关系建图：

**Wiki-map V15 docs/**：
[v8-design](../_refs/wiki-map/bookworm-agent/docs/v8-design.md) ·
[v8-detailed-design](../_refs/wiki-map/bookworm-agent/docs/v8-detailed-design.md) ·
[architecture](../_refs/wiki-map/bookworm-agent/docs/architecture.md) ·
[v15-summary](../_refs/wiki-map/bookworm-agent/docs/v15-summary.md) ·
[v15-system-map](../_refs/wiki-map/bookworm-agent/docs/v15-system-map.md) ·
[optimization-log](../_refs/wiki-map/bookworm-agent/docs/optimization-log.md) ·
[energy-test-results](../_refs/wiki-map/bookworm-agent/docs/energy-test-results.md) ·
[team-simulation](../_refs/wiki-map/bookworm-agent/docs/team-simulation.md)

**ISS 知识库 docs/**：
[iss-auth/项目详细设计](../_refs/iss-kb/iss-ai-knowledge/iss-auth/ISS-Auth%20%E8%AE%A4%E8%AF%81%E6%9C%8D%E5%8A%A1%20%E2%80%94%20%E9%A1%B9%E7%9B%AE%E8%AF%A6%E7%BB%86%E8%AE%BE%E8%AE%A1%E6%96%87%E6%A1%A3%20.md) ·
[iss-auth/二方包详细介绍](../_refs/iss-kb/iss-ai-knowledge/iss-auth/二方包详细介绍.md) ·
[iss-system/项目详细设计](../_refs/iss-kb/iss-ai-knowledge/iss-system/ISS-System项目详细设计文档.md) ·
[iss-system/README](../_refs/iss-kb/iss-ai-knowledge/iss-system/README.md) ·
[iss-system/AGENTS](../_refs/iss-kb/iss-ai-knowledge/iss-system/AGENTS.md) ·
[iss-system/二方包详细介绍](../_refs/iss-kb/iss-ai-knowledge/iss-system/二方包详细介绍.md) ·
[iss-common/README](../_refs/iss-kb/iss-ai-knowledge/iss-common/README.md) ·
[iss-common/二方包介绍](../_refs/iss-kb/iss-ai-knowledge/iss-common/二方包介绍.md) ·
[iss-common/二方包详细介绍](../_refs/iss-kb/iss-ai-knowledge/iss-common/二方包详细介绍.md) ·
[iss-common/数据权限详解](../_refs/iss-kb/iss-ai-knowledge/iss-common/数据权限详解.md) ·
[iss-knowledge-parser/ARCHITECTURE](../_refs/iss-kb/iss-ai-knowledge/iss-knowledge-parser/docs/ARCHITECTURE.md) ·
[iss-knowledge-parser/DEVOPS](../_refs/iss-kb/iss-ai-knowledge/iss-knowledge-parser/docs/DEVOPS.md) ·
[iss-knowledge-parser/README](../_refs/iss-kb/iss-ai-knowledge/iss-knowledge-parser/docs/README.md) ·
[iss-ai-knowladge-web/README](../_refs/iss-kb/iss-ai-knowledge/iss-ai-knowladge-web/README.md)

---

## 文档变更记录

| 版本 | 日期 | 变更说明 |
|---|---|---|
| v1.0 | 2026-04-29 | 首版。修复 Wiki-map test_data/test_docs GBK 乱码 + 建立 Wiki-map / ISS 双索引 + ISS 二方包依赖关系图 |
