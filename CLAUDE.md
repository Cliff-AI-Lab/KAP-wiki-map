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

**M0 KAP-Lite**（前 4 周）：基于 Wiki-map V15 + ISS 接入 + 睿动；单角色；块②③ 主流程跑通；可演示给客户。

后续：M1 企业级 v1（4×6 矩阵 + 脱敏 + 制造模板）→ M2 块① → M3 高级治理 → M4 GA → M5 PoC。

### M0 进度快照（2026-04-28 二次会话末）

**已完成（15 commits / ~8.5 人时实际，对比 Opus 估算 56h，节省 85%）**：

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

**今日成果（5 commits in 1 session，~2h 实际 vs Opus 估 16h）**：
- 坑 1（LLM 全链路异步化）+ 顺手坑 D（verify_ssl 开关）+ 顺手坑 F（mock fallback 门控）全部修复
- httpx.Client → AsyncClient，pipeline ThreadPoolExecutor → asyncio.gather
- 双轨保留（sync run_* 仍可用，M0 兼容期不破坏其他调用方）
- tenacity 优化：业务异常不重试 + reraise=True
- 新增 `arun_pipeline` 是块②③ 入库主入口，API 三处（ingest_demo / ingest_files / analyze_files）已切换

**剩余 M0 清单（按 Opus DAG 推荐顺序）**：

```
[ ] 坑 6 · EmbeddingProvider + bge 接入         10h ← 推荐下次首项（独立度高，块③ 召回必备）
[ ] 坑 2 · Milvus ConnectionManager + 双向量    12h（与坑 6 配套）
[ ] 坑 5 · Neo4j GraphStore + InMemory 降级    20h（M0 最重）
[ ] 坑 7 · RBAC 中间件骨架                       8h
[ ] 坑 8 · Milvus access_level 字段              6h
```

剩余约 56h Opus 估时；按当前实际节奏（~12% Opus 估算）实际可能 ~7-10h。

### 下次开工提示词模板

继续 KAP M0 实施。本次目标：**坑 6 · EmbeddingProvider 抽象 + bge-large-zh 本地接入**（参见 docs/M0-tech-debt.md §2 坑 6）。

建议工作流（参照坑 1 5 批模式，已验证有效）：
1. 先用 `kap-delegate.py --task-type plan --mode diagnosis` 让 Opus 4.7 出 embedding 模块改造地图
2. 分批落地：
   - 批 a · `EmbeddingProvider` 抽象类 + `MockEmbedding` / `BGELocalEmbedding` / `RuidongEmbedding` 三实现
   - 批 b · `vector_store.py` 集成 + 写入时挂 `embedding_model_version` 元数据（坑 6 + 坑 2 联动）
   - 批 c · API + pipeline 切换调用方
3. 每批独立 commit + 跑 `tests/unit/` 套件验证零回归
4. 关键约束：`KAP_ALLOW_MOCK_EMBEDDING` 环境变量门控（仿照 `allow_mock_llm`）；sandbox/prod 强制 False

**项目当前状态可直接接续**：
- 文档：`docs/01-技术决策书.md` v1.1 / `docs/02-产品需求PRD.md` v1.2 / `docs/M0-tech-debt.md` v1.0 / `docs/M0-tech-debt-async-plan.md` v1.0
- 设计：`design/index.html`（Plan A UI 原型）
- 工具：`scripts/kap-delegate.py`（默认 Opus 4.7 via 睿动 CRS Anthropic 端点）
- 代码：`backend/` (Python FastAPI) + `frontend/` (React) + `infra/` (compose) 全部就绪
- 测试基线：181/183 通过（仅 V15 既有 connector mock 数据漂移 2 项与 KAP 改造无关）

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
