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

```
[M0 KAP-Lite]──→[M1 企业级v1]──→[M2 AI-native]──→[M3 高级治理]──→[M4 重抽影子库]──→ M5⬜
```

进程链（按时间正序，每份是独立快照）：
[M0-KAP-Lite](docs/progress/M0-KAP-Lite.md) → [M1-企业级v1](docs/progress/M1-企业级v1.md) → [M2-AI-native](docs/progress/M2-AI-native.md) → [M3-高级治理](docs/progress/M3-高级治理.md) → [M4-重抽影子库](docs/progress/M4-重抽影子库.md) → M5（待启动）

**KAP 累计**：~80 commits / 测试 714/716 ✓ / 实际 ~51h vs Opus 估 ~390h，节省 ~87%。

**三块产品形态全部就位**：
- 块①（M2 + M3 完整对话式建体系）
- 块②（M0+M1+M3 6 工位 + 4×6 矩阵 + 脱敏 + W4 LLM 抽取 + M4 重抽）
- 块③（M0+M2 三路召回 + obsidian 图谱）
- M3+M4 双层本体演化 + 全量重抽影子库（[决策书 §5.3 D8/D9](docs/01-技术决策书.md) KAP IP 引擎闭环）

**下一阶段 M5 待启动**：监测条件 2/3/4 完整 LLM / as_of 历史回溯 / 7 天自动观察 / 独立物理 Neo4j 实例。

### Obsidian 图谱配色建议

打开 obsidian → Graph view → ⚙️ Filters → Color groups，按路径 query 设：

| 节点                  | 路径模式（query）                                 | 建议颜色 |
|:---|:---|:---:|
| KAP 新作              | `path:docs/ OR path:backend/ OR path:frontend/`   | 🔵 蓝色 |
| KAP 进程链            | `path:docs/progress/`                              | 🟢 绿色（线性递增） |
| 设计蓝本（中心）      | `path:docs/01-技术决策书 OR path:docs/02-产品需求` | 🟡 黄色 |
| ISS 参考项目          | `path:_refs/iss-kb/`                              | 🔴 红色 |
| Wiki-map V15 参考     | `path:_refs/wiki-map/`                            | 🟠 橙色 |

> 详细 commit 时间线、ISS / Wiki-map 引用关系、代码模块关联等见各 [`docs/progress/M{N}-...md`](docs/progress/) 快照。
> 不要在 CLAUDE.md 重复维护快照内容（避免与进度文档双源不一致）。

<!-- M0 v3 / M1 v1 / M2 v2 / M3 v1 / M4 v1 详细快照已迁移到 docs/progress/M{N}-...md
     避免本文件大爆炸式中心化（feedback memory · obsidian 进程版本化）

历史快照内容（不再维护，请去 docs/progress/）：
- 坑 1（LLM 全链路异步化）：`httpx.Client` → `AsyncClient`，pipeline `ThreadPoolExecutor` → `asyncio.gather` + `Semaphore`
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

### M2 进度快照 v2（2026-04-29 · 4/4 项全部交付，含块①）

**M2 全部完工（7 commits / ~5h 实际 vs Opus 估算 ~30h，节省 83%）**

| Commit  | 内容                                           | 测试   |
|:---|:---|:---:|
| `6175808` | **#1 LLM-Critic 6 维质疑** · prompt + sync/async 双轨 + 容错 + W4 hook 集成 | +16 ✓ |
| `b9cca04` | **#2 W1 脱敏 ingest hook** · redact_and_persist_doc + /sensitive/decode 高密解码 + 审计日志 | +8 ✓  |
| `ca544be` | **#3 GraphView obsidian 风格升级** · 柔光外发光 + 染色维度切换（社区/类型/中心性） | —     |
| `98e03b0` | **#4 块① 批 1** · ArchitectAgent 状态机骨架（4 阶段 identify/propose/refine/export） | +14 ✓ |
| `8385745` | **#4 块① 批 2** · industry_recognizer 两阶段（关键词初筛 + LLM 二轮判定） | +11 ✓ |
| `2788acf` | **#4 块① 批 3** · taxonomy_builder + exporter（主树提议 + 自然语言 CRUD + IndustryTemplate 导出） | +18 ✓ |
| `6bdac2d` | **#4 块① 批 4** · API endpoints（5 端点 + RequireRole(DG) 权限） | +9 ✓  |

**M2 全景成果**：

- **LLM-Critic（决策书 §5.5 D13 lite）**：单 LLM 调用 6 维质疑（一致性/完整性/证据强度/重复性/时效性/跨域），CriticResult 含 findings + overall_severity + has_blocking_issue()；轻量化路线 — 不接 pipeline 主路径，**只在 W4 写入侧 hook（低置信度兜底场景）调用**，符合"AI native + 人工兜底"；critic blocking 触发工单 priority +20
- **W1 脱敏接入（§5.4 D10）**：ingest 主路径在 RawStore 保存原文之后调 `redact_and_persist_doc`，doc.content 就地替换为脱敏文 + mapping 写加密 KV；pipeline 后续基于脱敏文做嵌入 + 入库（向量库不存原文）；新增 `/api/v1/sensitive/decode/{mapping_id}` 高密解码端点（`RequireAccessLevel(CONFIDENTIAL)` + 每次访问写审计日志）
- **GraphView obsidian 升级（feedback memory · 用户反馈兑现）**：增量改造不重写 — canvas `shadowBlur` 柔光外发光（选中 22 / 聚焦 10）+ 染色维度三模式 toggle（社区 Louvain / 实体类型 8 类 / 中心性 3 档梯度）+ 详情面板 + 图例联动；保留所有既有交互（拖拽 / 1-hop / 搜索 / 推理虚线）
- **块① 知识咨询智能体（决策书 §4 / PRD §3 lite，KAP AI native 旗舰）**：
  - 对话状态机 4 阶段：identify → propose → refine → export
  - industry_recognizer 两阶段（Stage 1 conf ≥ 0.7 跳过 LLM，省成本；Stage 2 LLM 在 top 3 候选中选）+ 防 LLM 幻觉（返回 code 必须在候选）
  - taxonomy_builder 主树提议（只动 L2 不重写 L3/L4，全 drop 兜底保全）+ 自然语言 CRUD（中文 regex：删除/重命名/新增）
  - exporter 导出 IndustryTemplate（自动避免覆盖基础模板加 -custom-{uuid}）+ YAML/JSON 序列化
  - 5 API 端点（sessions / message / draft / export）+ RequireRole(DG)（决策书 §4.1 锁 DG 主导建体系）
  - 不上 LangGraph 等重框架；内存 session store；M3 接 PG 持久化

**测试基线**：503/505 unit ✓（V15 dingtalk/wecom mock drift 仍 2 个）

**用户反馈三条全部兑现**（feedback memory）：
- ISS 零侵入 → ISS 集成 + Architect 完全无 Java 改动
- AI native 轻量化 → critic/redactor/architect 全函数式实现，能函数就别建类
- obsidian 图谱风格 → GraphView 柔光发光 + 染色维度（M2 #3）

**M3 启动条件**（M2 已交付）：
- ✓ 6 维 LLM-Critic 调用通道
- ✓ 脱敏 W1 hook 接入主路径
- ✓ 块① 全流程（识别 → 提议 → 调整 → 导出）
- ✓ 4×6 矩阵审核台 + W4 写入侧
- ✓ 测试基线 503/505 ✓

### M3 进度快照 v1（2026-04-29 · 全部 5 项交付）

**M3 全部完工（12 commits / ~10h vs Opus 估 50-60h，节省 ~83%）**

| Commit  | 内容                                      | 测试   |
|:---|:---|:---:|
| `170ed06` | **#1 双层本体 批 1** · 类型 + L1 内置（制造 9+8 / 能源 10+6） | +17 ✓ |
| `0dacd88` | **#1 批 2** · OntologyStore + 版本管理 + diff | +17 ✓ |
| `a8ba4d5` | **#1 批 3** · LLM 演化提议器（监测条件 1） | +10 ✓ |
| `a516d86` | **#1 批 4** · API 7 端点 + 4×6 矩阵审核台联动 | +13 ✓ |
| `9ade622` | **#2 双 Agent 互审** · pipeline 主路径接入 + critic blocking 强制 review | +8 ✓ |
| `b884dcb` | **#3a Facet 提议器** · LLM 归纳 doc_type → FacetSchema | +16 ✓ |
| `0ec6173` | **#3b 命名规范生成器** · 决策书 §4.4 模板 + 校验 + 调整 | +20 ✓ |
| `53c7b4d` | **#3d 冲突预演** · LLM 归类 + 重复 + 孤立检测 | +13 ✓ |
| `1728642` | **#3c 主树高级 CRUD** · merge/split/undo 撤销栈 | +13 ✓ |
| `1d7b11c` | **#4 W4 LLM 实体抽取** · 本体约束 + 敏感标记 + 关系定义域 | +14 ✓ |
| `918b86f` | **#5 PG 持久化** · ArchitectSession + OntologyProposal Store 抽象 | +11 ✓ |

**M3 全景成果**：

- **双层本体（决策书 §5.3 D8/D9 lite）**：L1 平台预置（制造 9 实体 + 8 关系；能源 IEC CIM 10+6） + L2 客户私有可演化；OntologyStore 版本管理（patch/minor bump + diff + 多项目隔离）；LLM 演化提议器（监测条件 1：未匹配实体超阈值 → 提议新类型）；7 API 端点 + 联动 4×6 矩阵审核台 W4-SME 必审
- **双 Agent 互审 pipeline 主路径接入**：``pipeline_critic_enabled`` flag 默认关闭（M2 lite 兼容），开启时 asyncio.gather 并发跑 critic；blocking issue（severity ≥ 0.6）强制 ``needs_review=True``，覆盖 judge 高置信度
- **块① 完整化（PRD F1.3-F1.6 lite）**：
  - **#3a Facet 提议器**：LLM 基于样本归纳 doc_type → FacetSchema 6-10 字段 + 敏感标记，复用 M1 制造 4 套经验
  - **#3b 命名规范生成器**：决策书 §4.4 默认 8 字段（KB-CS-SOP-...）+ 实时预览 + 校验函数 + reorder/required 调整
  - **#3c 主树高级 CRUD**：merge_nodes（子节点合并去重）+ split_node + 撤销栈（LIFO 20 限）
  - **#3d 冲突预演**：LLM 用上传材料预演归类 → 冲突（双归 ≥ 0.5）/ 重复（标题标准化）/ 孤立 三类清单
- **W4 LLM 实体抽取（决策书 §5.2）**：本体严格约束 type_id 必须在 L1+L2 注册集合（防 LLM 幻觉）；关系 source/target 类型符合定义域；复用 packages/sensitive NER 标记敏感实体；ExtractedEntity/Relation/Result Pydantic 三层
- **PG 持久化**：ArchitectSessionStore + OntologyProposalStore Protocol + InMemory（默认）+ Pg（CREATE TABLE IF NOT EXISTS 幂等 + JSONB 字段 + 索引 + ON CONFLICT upsert）；ArchitectAgent / ontology router 接入 PG 留 M4

**测试基线**：655/657 unit ✓（V15 dingtalk/wecom mock drift 仍 2 个）

**M4 启动条件**（M3 已交付）：
- ✓ L1+L2 双层本体注册 + 版本管理 + diff
- ✓ 演化提议器 → 矩阵审核台 W4-SME
- ✓ Critic 6 维质疑 pipeline 主路径接入（可选开启）
- ✓ 块① 4 项完整功能（Facet/命名/主树高级/冲突预演）
- ✓ W4 LLM 实体抽取（本体约束 + 敏感标记）
- ✓ session/proposal store 持久化抽象（PG 实现就绪，ArchitectAgent/router 待切换）
- ✓ 测试基线 655/657 ✓

### 下次开工提示词模板（M4 入口）

进入 **M4 全量重抽影子库**（决策书 §5.3 D8 工程闭环）：

M3 #1 lite 仅做了双层本体设计 + LLM 提议；M4 是**演化机制的工程化收口**：

1. **影子图谱机制**（决策书 §5.3 核心工程难点）— 独立 Neo4j 实例 / 数据库；本体变更触发后台全量重抽，日常入库不阻塞主图谱
2. **增量哈希**（成本控制命门）— chunk content hash 未变 → 跳过实体抽取，仅按新本体重映射；schema-affected 部分才重跑
3. **as_of 历史回溯**（决策书 §5.3）— Cypher 查询带 ontology_version timestamp filter
4. **灰度切换 + 7 天回滚**（决策书 §5.3）— 影子图谱对比报告 + 指标观察期；指标恶化（召回率/SME 驳回率/命中率）一键回退
5. **PG 持久化全面接入** — ArchitectAgent / ontology router 切到 PG store（M3 #5 store 抽象已就位）
6. **演化监测条件 2/3/4**（决策书 §5.3 剩余 3 种）— 自定义关系反复 / 语义漂移 / 行业标准升版

建议工作流：
1. **必先 plan**（M4 是工程量最重的一块，~15-20h，需 DAG 拆 5+ 批）
2. 优先级顺序：**影子图谱机制 → 增量哈希 → as_of 回溯 → 灰度切换 + 回滚 → 监测条件 2/3/4 → PG 全面接入**
3. 关键约束：决策书 D8（影子库不出域，独立 Neo4j 实例）；feedback memory 三条原则
4. 每子模块独立 commit + 跑 `tests/unit/` + 集成测试（影子库需 docker-compose 测试）
-->

<!--
**项目当前状态可直接接续**：
- 文档：`docs/01-技术决策书.md` v1.1 / `docs/02-产品需求PRD.md` v1.2 / `docs/M0-tech-debt.md` v1.0（M0 closed）/ `docs/M1-iss-integration.md` v1.0（M1 部署指南）
- 设计：`design/index.html`（Plan A UI 原型）+ `frontend/src/pages/v15/GovernanceMatrix.tsx`（M1 矩阵 UI 工程蓝图美学）+ `frontend/src/pages/v15/GraphView.tsx`（M2 obsidian 风格力导向图谱）
- 工具：`scripts/kap-delegate.py`（默认 Opus 4.7 via 睿动 CRS Anthropic 端点）
- 代码：`backend/` Python 异步全栈 + `frontend/` React 19 + `infra/` compose 全部就绪
- M1 新增包：`packages/auth/`（ISS 集成）+ `packages/sensitive/`（脱敏离线工具）+ `packages/governance/matrix.py` `sla.py` `distillation_hook.py` + `packages/templates/facets_manufacturing.py`
- M2 新增模块：
  - `packages/distillation/agents/critic.py`（6 维质疑）
  - `packages/sensitive/ingest_hook.py`（W1 脱敏 hook）+ `api/routers/sensitive.py`（解码端点）
  - `packages/architect/`（块① 咨询智能体：agent / industry_recognizer / taxonomy_builder / exporter / prompts）
  - `api/routers/architect.py`（5 端点）
- M3 新增模块：
  - `packages/ontology/`（双层本体：base / store / evolution_proposer / proposal_store / builtin/manufacturing_l1.py & energy_l1.py）
  - `api/routers/ontology.py`（7 端点）
  - `packages/architect/facet_advisor.py` `naming_convention.py` `conflict_detector.py` `session_store.py`（块① 4 项完整 + PG）
  - `packages/architect/taxonomy_builder.py` 加 merge_nodes / split_node / undo
  - `packages/extraction/entity_extractor.py`（W4 LLM 实体抽取，本体约束）
  - pipeline 加 critic 主路径接入（settings.pipeline_critic_enabled flag）
- 测试样例：`test-samples/` 48 文档 5 行业子集 + Obsidian 图谱完整无孤岛
- 测试基线：655/657 unit 通过（V15 遗留 2 项不涉及 KAP 改造）
-->

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
