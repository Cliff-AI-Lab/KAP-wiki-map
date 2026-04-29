# KAP · Claude 项目内存

> 给未来 Claude 会话的项目级提示词。每次会话自动加载。

## 项目定位

**KAP（Knowledge Agent Platform，知识智能体平台）**——面向**全行业**（首批锁定制造与能源）的、**私有化部署**的、**AI-native** 的企业知识治理全流程智能体平台。

三块产品形态：
1. **块① 知识咨询智能体**（`/agent/architect`）——AI 对话式建知识体系
2. **块② 知识库 + 知识图谱**（`/workbench`）——六工位 + 4×6 矩阵审核台 + 双层本体 + 脱敏
3. **块③ 渐进式消费门户**（`/portal`）——Wiki / RAG / 图谱三路并行召回

## 文档体系（必读）

任何方案讨论前先看：

- `docs/01-技术决策书.md` v1.1 — **架构宪法**，已锁定决策不变更
- `docs/02-产品需求PRD.md` v1.2 — 功能规格 + MVP + 路线图
- `design/index.html` — Plan A UI 原型（工程蓝图美学）

**修改 `docs/01` 中已锁定的决策必须走变更评审**。

## 技术栈（已定）

- **前端**：React 19 + Vite + TypeScript + Tailwind
- **Java 业务**：Spring Boot 3.3.5 + Spring Cloud（继承 ISS 底座）
- **Python AI**：FastAPI + AsyncIO + httpx.AsyncClient（**禁止同步 httpx.Client**）
- **存储**：MySQL 8 / PostgreSQL 16 / Milvus 2.4 / Neo4j 5 / Redis / RabbitMQ / MinIO
- **基建**：Nacos / Sentinel / Seata / Skywalking + OpenTelemetry
- **LLM 网关**：睿动 `iruidong.com/v1`（OpenAI 兼容），不硬编码模型名

## 复用基础（M0 起点）

- **Wiki-map V15** (`_refs/wiki-map/bookworm-agent/`) — KAP 后端 + 前端起点（拉到 `backend/`、`frontend/`）
- **ISS 知识库** (`_refs/iss-kb/`) — 企业级 RBAC + 数据权限 + 多模态解析底座
- 复用率 ~55-60%；自研集中：双层本体演化 / 脱敏 / 6 维 LLM-Critic / 4×6 矩阵审核 / 块①

## 开发约束（必须遵守）

### 来自全局（user/.claude/rules/common/ruidong-agent-dev.md）

- **MUST**：所有 LLM 调用走 `iruidong.com/v1`（OpenAI 兼容）
- **MUST**：环境变量区分 dev/sandbox/prod 三套
- **MUST**：模型列表客户端过滤聊天模型，**禁止硬编码模型名**
- **MUST NOT**：硬编码 API Key（`sk-*`、`cr_*`）、SSO 密钥（AES_KEY/AES_IV）、内网 IP 到源代码
- **MUST NOT**：使用 emoji 表情（用 SVG/Lucide/Heroicons）

### KAP 项目特有

- **AsyncClient 强制**：Wiki-map V15 用 `httpx.Client`（同步）阻塞 uvicorn 事件循环。**KAP 必须用 AsyncClient**（决策书 §13）
- **图谱持久化**：用 Neo4j，不用内存模式（V15 重启丢失）
- **真嵌入**：必须用 bge-large-zh / bce-embedding，禁止 mock embedding 入生产
- **审核台 SLA 不允许 LLM 自动通过**（决策书 D12）：超时升级到上级专家，不存在"LLM 兜底"路径

## 工具与脚本

- `scripts/kap-delegate.py` — 委派代码工作给 Claude（默认 Anthropic backend + Opus 4.7）
  - `--task-type plan` → claude-opus-4-7（架构/PRD/调研）
  - `--task-type dev` → claude-sonnet-4-6（开发，默认）
  - `--task-type light` → claude-haiku-4-5-20251001（重命名/格式化）
- `scripts/README.md` — 完整用法

## 当前阶段

**M0 KAP-Lite 已完工**（2026-04-29）：基于 Wiki-map V15 + ISS 接入 + 睿动；9 大坑全部技改；块②③ 主流程跑通；测试 250/252 ✓。

**M1 企业级 v1 已完工**（2026-04-29，同日 follow-up）：ISS 集成 + 4×6 矩阵审核台 + W4 写入侧 + 敏感脱敏 + 制造 Facet + 矩阵 UI。10 commits / ~7.5h vs 原估 60-80h。

**下一阶段 M2**：obsidian 风格力导向图谱 + LLM-Critic 6 维质疑 + 块①（咨询智能体）。

后续路线：M2 → M3 高级治理 → M4 GA → M5 PoC。

### M0 进度快照 v3（2026-04-29 · M0 全部技改收口）

**M0 全部 9 大坑 + 4 个顺手坑全部完工（23 commits / ~12.5 人时实际 vs Opus 估算 112h，节省 89%）**

| Commit | 内容 | 测试 |
|---|---|---|
| `1dd9ebd` | M0 Day 0 骨架 + V15 主干导入 | — |
| `b56dab5` | 加 .claude/ 到 .gitignore | — |
| `ff41e39` | T1 · KAP 品牌化 + T5 Neo4j compose | — |
| `25f9124` | T2 · M0 技术债务地图（Opus 4.7 产出）| — |
| `7125455` | T4 · 三环境配置（.env.dev/sandbox/prod + master）| — |
| `7d08a42` | 坑 3 · Judge 阈值外置 + 决策函数化 + R3 review 通道 | +22 ✓ |
| `e8f7dad` | 坑 4a+4b · 行业模板加载器 + 多租户域推断（含坑 B）| +29 ✓ |
| `1560bbe` | CLAUDE.md 进度快照 v1 | — |
| `ad8e2b9` | **坑 1 批 0** · 三环境 settings + verify_ssl/allow_mock 门控 | +18 ✓ |
| `37b8b3e` | **坑 1 批 1** · llm_client 双轨（acall_llm/_json）+ 坑 D/F 落地 | +14 ✓ |
| `e9d2fc1` | **坑 1 批 2** · 4 个 agent arun_* 异步入口 | +9 ✓ |
| `c7a6b13` | **坑 1 批 3** · pipeline asyncio.gather + Semaphore | +6 ✓ |
| `87949c5` | **坑 1 批 4** · API endpoint 切 `await arun_pipeline` | — |
| `973aebc` | CLAUDE.md 进度快照 v2 | — |
| `d1b5691` | **坑 6** · EmbeddingProvider 抽象 + bge 接入 + 异步双轨 | +20 ✓ |
| `6c169ad` | docs(refs) · 修复 _refs 乱码 + 建立 Wiki-map/ISS 关联索引 | — |
| `1ad3d0f` | feat(test-samples) · 48 文档按行业打包为 KAP 测试样例集 | — |
| `8f9e387` | **坑 2** · Milvus ConnectionManager + 双向量 schema（含坑 8 access_level 预留）| +13 ✓ |
| `7e385ef` | docs(test-samples) · 用 markdown link 全面理顺 Obsidian 图谱关系 | — |
| `df5c9c1` | **坑 5** · Neo4j GraphStore 修静默 fallback + 加 ontology_version | +14 ✓ |
| `f751be7` | feat(test-samples) · 为 39 份非 .md 样本生成 .md 索引页 | — |
| `5bc2047` | feat(test-samples) · 给 9 份 V15 原始 .md 注入 navigation header | — |
| `4ff7af8` | **坑 7+8** · KAP 5 角色枚举 + RBAC Dependency + 召回阶段密级路由 | +25 ✓ |

**M0 全景成果**：

- **坑 1**（LLM 全链路异步化）：`httpx.Client` → `AsyncClient`，pipeline `ThreadPoolExecutor` → `asyncio.gather` + `Semaphore`，双轨保留（sync `run_*` + async `arun_*`），tenacity 业务异常不重试 + `reraise=True`
- **坑 2**（Milvus ConnectionManager + 双向量）：`MilvusConnectionManager` 健康检查 + 熔断；schema 增加 `vector_type` / `embedding_model_version` / `access_level` int8 字段，原始向量与脱敏向量物理分离
- **坑 3**（Judge 阈值外置）：阈值 → `judge_thresholds.yaml`；决策函数化 `decide_action()`；`R3 review` 通道独立
- **坑 4a+4b**（行业模板 + 多租户域）：制造/能源行业模板 loader + 多租户 domain 推断（含坑 B：domain_path 覆写）
- **坑 5**（Neo4j GraphStore）：移除内存模式静默 fallback，加 `ontology_version` 字段；启动失败 fail-fast 而非误用 InMemory
- **坑 6**（EmbeddingProvider 抽象）：`EmbeddingProvider` ABC + `Mock` / `Ruidong` / `BGELocal` 三实现；`current_model_version()` 写入物料元数据
- **坑 7+8**（RBAC + 召回密级路由）：5 KAP 角色枚举（DG/SME/SEC/AIOps/READER）+ V15 admin/editor 别名兼容；`UserContext.max_access_level: int` 自动同步；`RequireRole/RequireAccessLevel` Dependency；retriever 三处 `vector_store.search()` 注入 `max_access_level` filter
- **顺手坑 A**（Settings 强制策略）：`model_post_init` enforce sandbox/prod 的 `allow_mock_*` / `allow_memory_fallback` / `verify_ssl`
- **顺手坑 B**（domain_path 覆写）：QA 引擎已计算时 retriever 直接使用，避免重复 SkillsRouter
- **顺手坑 D**（verify_ssl 开关）：dev 可关、sandbox/prod 强制开
- **顺手坑 F**（mock fallback 门控）：sandbox/prod 完全屏蔽 mock embedding/llm

**测试基线**：250/252 通过（仅 V15 既有 connector mock 数据漂移 2 项与 KAP 改造无关）

**M1 启动条件**（M0 已交付）：
- ✓ 三环境隔离 + 强制策略
- ✓ LLM/Embedding 全链路异步 + 双轨可降级
- ✓ Milvus 双向量 schema + 召回密级过滤
- ✓ Neo4j GraphStore fail-fast + 本体版本化
- ✓ KAP 5 角色 + RBAC Dependency
- ✓ 行业模板 + 多租户域推断
- ✓ 测试样例集（48 文档，5 行业子集，Obsidian 图谱完整）

### M1 进度快照 v1（2026-04-29 · M1 全部主线交付）

**M1 全部 6 项主线 + 1 项激活补丁完工（10 commits / ~7.5 人时实际 vs Opus 估算 60-80h，节省 ~90%）**

| Commit  | 内容                                                | 测试   |
|:---|:---|:---:|
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

**M1 全景成果**：

- **ISS 集成（零侵入）**：决策书 §9.1 写"100% 复用 iss-common-*"假设 Java 业务层，但 KAP backend 是 Python — 改走**协议层接入**：HS512 JWT 验签 + 共享 ISS Redis 拿 LoginUser + HTTP 调 RemoteUser/Dept；不改 ISS 任何 Java 源码 / 数据库 schema / 二方包。AuthMiddleware 三模式 dispatch（dev=API Key / sandbox=JWT 验签 / prod=网关 header 信任）
- **DataScope 5 级**（决策书 §8.1）：Python 函数式等价（不复刻 ISS MyBatis SQL 拼接）；retriever 后过滤 RBAC 循环里激活；W4 写入侧补 dept_id/created_by 后真生效，老文档透明放行保 M0 兼容
- **4×6 矩阵审核台**（决策书 §5.2 D6）：4 角色 (DG/SME/SEC/AIOps) × 6 工位 (W1-W6) R/C/I 表代码化；GovernanceQueueItem 加 8 字段（workstation/assigned_role/claimed_*/sla_due_at/confidence）；claim/escalate/list_matrix/find_overdue 操作；D12 SLA sweep 自动升级（AIOps→SME→DG，DG 顶级触发"积压告警"）
- **W4 写入侧蒸馏 hook**：M0 坑 3 已标 needs_review，M1 在 knowledge.py 双写到 4×6 矩阵；workstation=W4 → assigned_role=SME（必审锁定）；priority 与 confidence 反相关
- **敏感脱敏管线（lite 离线工具集）**（决策书 §5.4 D10/D11）：NER 三类（人名 / 工艺参数 / 客户名）+ Redactor 三策略（角色化 / 三级降精度 / 代码化）+ AES-256-GCM 加密 KV（Redis 持久 + dev 内存 fallback）；W1/W4 hook 集成 + 双向量 vec_redacted/vec_original 路由 → M2 批
- **制造 Facet schema**（PRD §10.4 1129 行）：4 套（equipment_fault/process_standard/sop/quality_record），每套 6-10 字段 + 敏感字段标记 + primary_role；通过 IndustryTemplate.facets dict 注册，供 W3 切块 / W4 抽取阶段调
- **矩阵审核台前端 UI**：4×6 网格（CSS Grid）+ R/C/I 标记 + 角色染色（DG=蓝/SME=橙/SEC=红/AIOps=绿，柔光发光）+ 待办>0 脉冲动画 + 抽屉滑入工单列表 + 5 操作（认领/通过/驳回/改/升级）+ SLA Tag

**测试基线**：427/429 unit ✓（V15 dingtalk/wecom mock drift 仍 2 个，与 M0/M1 改造无关）

**用户反馈已落地**（feedback memory）：
- ISS 零侵入（`feedback_iss_no_modification.md`）— 全 KAP 侧改动，不动 Java 源码
- AI native 轻量化（`feedback_kap_lightweight_ai_native.md`）— 函数式实现优先、能函数就别建类、勿过度对接
- 图谱 obsidian 风格（`feedback_graph_obsidian_style.md`）— 矩阵 UI 加角色染色 + 柔光脉冲；力导向图谱留 M2

**M2 启动条件**（M1 已交付）：
- ✓ ISS 三模式认证 + DataScope 5 级激活
- ✓ 4×6 矩阵审核台后端 + 前端
- ✓ W4 写入侧 dept_id / created_by 持久化
- ✓ 敏感脱敏离线工具集（NER + Redactor + 加密 KV）
- ✓ 制造行业 Facet schema 4 套
- ✓ 测试基线 427/429 ✓

### 下次开工提示词模板（M2 入口）

进入 **M2** — obsidian 风格图谱 + LLM-Critic + 块① 咨询智能体（决策书 §10 路线图）：

1. **obsidian 风格力导向图谱**（M1 用户反馈延期）— `react-force-graph-2d`（已在依赖）改造，节点动态布局 + 染色维度切换（工位/角色/业务域/密级）+ 分支过滤侧边栏 + hover 卡片预览（参考 `feedback_graph_obsidian_style.md`）
2. **LLM-Critic 6 维质疑**（决策书 §5.5 D13）— 双 Agent 互审（抽取 LLM-A + 质疑 LLM-B），6 维（一致性/完整性/证据强度/重复性/时效性/跨域），输出结构化质疑入审核台
3. **块① 知识咨询智能体**（决策书 §1.5 块①）— `architect/agent.py` 对话式建体系，`taxonomy_builder.py` 状态机，`facet_advisor.py` Facet 提议器
4. **W1/W4 脱敏管线 hook**（决策书 §5.4 工位嵌入）— 解析后调脱敏 → 入库分双向量 vec_redacted/vec_original → 召回路由按密级
5. **能源 + 制造模板包扩充** — 完善 manufacturing-discrete / manufacturing-process / energy-power / energy-oil-gas 子模板

建议工作流：
1. 优先级顺序：**LLM-Critic（解锁审核台 AI 兜底）→ 脱敏 W1/W4 集成 → obsidian 图谱（产品视觉杀手锏）→ 块① 咨询智能体（最重，建议独立 plan agent 拆 DAG）**
2. 关键约束：决策书 D13 双 Agent 互审；feedback memory 三条原则（轻量化 / ISS 零侵入 / obsidian 风格图谱）
3. 每子模块独立 commit + 跑 `tests/unit/` + 新增 `tests/integration/`

**项目当前状态可直接接续**：
- 文档：`docs/01-技术决策书.md` v1.1 / `docs/02-产品需求PRD.md` v1.2 / `docs/M0-tech-debt.md` v1.0（M0 closed）/ `docs/M1-iss-integration.md` v1.0（M1 部署指南）
- 设计：`design/index.html`（Plan A UI 原型）+ `frontend/src/pages/v15/GovernanceMatrix.tsx`（M1 矩阵 UI 工程蓝图美学起点）
- 工具：`scripts/kap-delegate.py`（默认 Opus 4.7 via 睿动 CRS Anthropic 端点）
- 代码：`backend/` Python 异步全栈 + `frontend/` React 19 + `infra/` compose 全部就绪
- M1 新增包：`packages/auth/`（ISS 集成）+ `packages/sensitive/`（脱敏）+ `packages/governance/matrix.py` `sla.py` `distillation_hook.py` + `packages/templates/facets_manufacturing.py`
- 测试样例：`test-samples/` 48 文档 5 行业子集 + Obsidian 图谱完整无孤岛
- 测试基线：427/429 unit 通过（V15 遗留 2 项不涉及 KAP 改造）

## 目录约定

```
KAP知识智能体平台/
├── backend/            Python FastAPI（基于 V15 演进）
├── frontend/           React 19（基于 V15 演进）
├── infra/              docker-compose / K8s / Nacos 配置
├── docs/               技术决策书、PRD、UI 规范、API、数据模型
├── design/             UI 原型 HTML（视觉锚点）
├── scripts/            kap-delegate 等工具
├── _refs/              参考项目（Wiki-map V15、ISS）只读
├── memory/             Claude 会话间记忆
├── CLAUDE.md           本文件
└── README.md           项目入口
```

## 不要做

- 不要在 `docs/01` 改已锁定决策（D1-D21），需走变更
- 不要在 `_refs/` 下改文件（参考项目，只读）
- 不要在代码里硬编码模型名 / Key / 内网 IP
- 不要把 Wiki-map V15 的同步 httpx.Client 模式带到 KAP（必须 AsyncClient）
- 不要重写 ISS 已有的 RBAC / DataScope / 解析能力，复用即可
