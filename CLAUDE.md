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

### M0 进度快照（2026-04-28，会话末）

**已完成（8 commits / ~6.5 人时实际，对比 Opus 估算 28h，节省 76%）**：

| Commit | 内容 |
|---|---|
| `1dd9ebd` | M0 Day 0 骨架 + V15 主干导入到 backend/ + frontend/ |
| `b56dab5` | 加 .claude/ 到 .gitignore |
| `ff41e39` | T1 · KAP 品牌化（元数据 / 镜像 / 容器命名）+ T5 Neo4j 加入 compose |
| `25f9124` | T2 · M0 技术债务地图（Opus 4.7 via kap-delegate 产出 docs/M0-tech-debt.md）|
| `7125455` | T4 · 三环境配置（.env.dev / .env.sandbox / .env.prod + master）|
| `7d08a42` | 坑 3 · Judge 阈值外置 + 决策函数化（22 测全绿，含 R3 review 通道）|
| `e8f7dad` | 坑 4a+4b · 行业模板加载器 + 多租户域推断（29 测全绿，附带修复额外坑 B）|

**下一项（按 Opus DAG）**：**坑 1 · LLM 全链路异步化**（M0 最大 PR，~16 人时）

涉及范围（按改造层级）：
1. `packages/distillation/llm_client.py` — `httpx.Client` → `httpx.AsyncClient`，`call_llm` / `call_llm_json` → `acall_llm` / `acall_llm_json`
2. `packages/distillation/agents/{librarian,conflict_auditor,judge,refiner}.py` — 全部 `async def`
3. `packages/distillation/pipeline.py` — orchestrator 异步化（`asyncio.gather` 并行）
4. `tenacity @retry` → `AsyncRetrying` 或 retry 的 async 模式
5. **顺手修复额外坑 D**：`verify=False` 加 settings 开关（dev 允许，sandbox/prod 强制 true）
6. **顺手修复额外坑 F**：tenacity catch-all + mock fallback 静默冲突 → mock 加 env gate (`KAP_ALLOW_MOCK_LLM`)
7. **顺手修复额外坑 A**：mock 业务规则剥离（mock 仅返回 schema 合规占位数据）
8. 全链路 fixture 升级：`asyncio.to_thread` 兼容旧同步测试

**剩余 M0 清单**：
```
[ ] 坑 1 · LLM 异步化（含坑 A/D/F）        16h ← 下次开工
[ ] 坑 2 · Milvus ConnectionManager + 双向量 12h
[ ] 坑 6 · EmbeddingProvider + bge 接入     10h
[ ] 坑 5 · Neo4j GraphStore + InMemory 降级 20h
[ ] 坑 7 · RBAC 中间件骨架                   8h
[ ] 坑 8 · Milvus access_level 字段          6h
```

### 下次开工提示词模板

继续 KAP M0 实施。本次目标：**坑 1 · LLM 全链路异步化**（参见 docs/M0-tech-debt.md §2）。

建议工作流：
1. 先用 `kap-delegate.py --task-type plan --mode diagnosis` 让 Opus 4.7 出**异步化迁移地图**（按文件给 diff 顺序、影响面、风险）
2. 按层级分批改造（llm_client → agents → pipeline）
3. 每层一个 commit + 跑 `tests/unit/` 套件验证零回归
4. 最后端到端烟测（uvicorn 起服 + 一份测试文档跑完整 W1-W5）

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
