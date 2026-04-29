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

**下一阶段 M1 企业级 v1**：4×6 矩阵审核台 + 脱敏管线 + 制造模板 + ISS 集成深化。

后续路线：M1 → M2 块①（咨询智能体）→ M3 高级治理 → M4 GA → M5 PoC。

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

### 下次开工提示词模板（M1 入口）

进入 **M1 企业级 v1**（决策书 §13 + PRD §10 路线图），目标：

1. **4×6 矩阵审核台**（DG/SME/SEC/AIOps × W1-W6 工位）— 前端工位看板 + 后端工单状态机
2. **敏感实体识别 + 脱敏管线** — W4 工位增加 PII/PHI/秘级识别 → 写入侧分流到 `vec_redacted` / `vec_original`
3. **制造行业模板包**（v1）— 设备故障 / 工艺标准 / SOP / 质量记录 4 套 facet schema
4. **ISS 集成深化** — `iss-common-security` JWT claims 完整对接（`roles` / `data_scope_level`）+ `iss-common-datascope` 5 级数据权限 AOP
5. **access_level 完整 4 级映射规则** — 按 Owner 角色 + Facet 推断（M0 默认全部 PUBLIC=0，写入侧需补）

建议工作流：
1. 用 `kap-delegate.py --task-type plan --mode roadmap` 让 Opus 4.7 出 M1 DAG（参考 M0 节奏）
2. 优先级顺序：**ISS 集成（解锁权限）→ 矩阵审核台后端 → 脱敏管线 → 制造模板包 → 矩阵审核台前端**
3. 每子模块独立 commit + 跑 `tests/unit/` + 新增 `tests/integration/`
4. 关键约束：决策书 D12（审核台 SLA 不允许 LLM 自动通过）；ISS 复用不重写

**项目当前状态可直接接续**：
- 文档：`docs/01-技术决策书.md` v1.1 / `docs/02-产品需求PRD.md` v1.2 / `docs/M0-tech-debt.md` v1.0（M0 全部 closed）
- 设计：`design/index.html`（Plan A UI 原型，M1 矩阵审核台需在此基础上扩展）
- 工具：`scripts/kap-delegate.py`（默认 Opus 4.7 via 睿动 CRS Anthropic 端点）
- 代码：`backend/` (Python FastAPI 异步全栈) + `frontend/` (React 19) + `infra/` (compose) 全部就绪
- 测试样例：`test-samples/` 48 文档 5 行业子集 + Obsidian 图谱完整无孤岛
- 测试基线：250/252 unit 通过（V15 遗留 2 项不涉及 KAP 改造）

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
