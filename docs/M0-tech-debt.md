# KAP M0 技术债务地图

> **文档版本**：v1.0
> **撰写日期**：2026-04-28
> **作者**：claude-opus-4-7（via kap-delegate plan diagnosis）+ KAP 项目组复核
> **文档定位**：M0 阶段实施前的技术债务清单与改造路线图，作为决策书 §13 的代码级落地补充
> **数据依据**：基于 backend/ 实际代码（llm_client.py / judge.py / refiner.py / 决策书 §13）的只读分析
> **属性**：内部工程文档（非客户文档）

## 0. 与其他文档的关系

```
01-技术决策书 §13（高层 8 项坑） ──┐
                                  ├──► 本文档（代码级映射 + DAG + 估时）─► M0 实施
02-产品需求 PRD §10.4（复用细则）──┘
```

- 决策书 §13 描述了**高层踩坑**（8 项），本文档把它们落到具体文件 + 行号 + 改造方案
- Opus 4.7 在分析过程中**发现 6 项决策书未列的额外坑**（A-F），其中 B/F 升级为 M0 必修
- 改造工时估算 **92 人时**（≈ 2-2.5 周单人 / 1 周双人），对应 PRD §10.3 方案 B 的 M0 KAP-Lite 4 周窗口

---

## 1. 总览表

| # | 坑 | 在代码中的位置 | 严重度 | 阶段归属 | 改造规模 |
|---|---|---|---|---|---|
| 1 | 同步 httpx 阻塞事件循环 | `llm_client.py` L17-26（`_get_openai`）、L420-470（`call_llm` 同步）、Judge/Refiner 全链路同步调用 | **致命** | **M0 必修** | **大** |
| 2 | Milvus 不稳定 / 连接断开重连 | `vector_store.py`（未提供，但被 W5 入库依赖） | 高 | M0 必修 | 中 |
| 3 | Judge 阈值过严，KEEP 率 42% | `judge.py` L94-111（决策规则硬编码）+ `kpi_retain.py`（DISCARD/ARCHIVE_THRESHOLD 常量） | 高 | **M0 必修** | 小 |
| 4 | domain_id 分配不精，全归 regulation | `llm_client.py` L235-278（`_mock_infer_domain_id`）、`refiner.py` L26-46（`_get_domain_list`）、L49-83（`_clean_domain_id`） | 高 | **M0 必修** | 中 |
| 5 | 图谱重启丢失（内存模式） | `graph_store.py`（未提供，决策书 §10.4 已锁 Neo4j 5+） | **致命** | **M0 必修** | 大 |
| 6 | Mock embedding 无语义区分 | `llm_client.py` L29-37（`_get_openai` 用于 LLM，但 embedding 通道未见真实接入）；`vector_store.py` 未提供 | 高 | M0 必修 | 中 |
| 7 | 单角色 Editor 无法企业 RBAC | `api/middleware/auth.py`（未提供）；决策书 §5.2 要求 DG/SME/SEC/AIOps/Reader 五角色 + 工位矩阵 | 高 | M1（M0 预留接口） | 大 |
| 8 | 仅 access_level 二元过滤 | 同上 + 召回链路（`retrieval/`）；决策书 §8.1 要求 4 级密级 + 召回阶段过滤 | 高 | M1（M0 预留字段） | 中 |
| **A** | **Mock 与真 LLM 路径行为割裂** | `llm_client.py` L74-104, L137-141 等 mock 内嵌业务规则 | 高 | M0 必修 | 中 |
| **B** | **`_get_domain_list()` 全局单例缓存（多租户事故源）** | `refiner.py` L23-46 模块级 `_domain_list_cache` | **高** | **M0 必修** | 小 |
| **C** | Mock 硬编码部门名 | `llm_client.py` L401-417 `_ENERGY_RELATION_TEMPLATES` | 中 | M1 | 小 |
| **D** | `verify=False` 硬编码（生产中间人攻击风险）| `llm_client.py` L21 | 高 | M0 必修 | 小 |
| **E** | Refiner `_clean_domain_id` 防御性清洗过重 | `refiner.py` L49-83 | 中 | M1 | 中 |
| **F** | **tenacity @retry 与 mock fallback 静默冲突** | `llm_client.py` L426-470 catch-all | **高** | **M0 必修** | 小 |

> **说明**：编号 1-8 来自决策书 §13；A-F 是本次代码分析新发现，未在决策书中。

---

## 2. 逐项详解（决策书 §13 八项坑）

### 坑 1 · 同步 httpx 阻塞事件循环

- **当前代码状态**：
  - `llm_client.py` L17-26：`_get_openai()` 显式构造 **`httpx.Client(verify=False)`**（同步客户端），注入 OpenAI SDK
  - `llm_client.py` L429-470：`call_llm()` 是**同步函数**，加了 `@retry`（tenacity 同步装饰器）。内部 `client.chat.completions.create(...)` 为同步阻塞调用，`timeout=60`
  - `llm_client.py` L484-495：`call_llm_json()` 同步
  - `judge.py` L74、`refiner.py` L153 直接同步调用 `call_llm_json()`
  - 决策书 §10.3 已明确要求 "httpx (AsyncClient!) — 避免 V15 同步阻塞坑"

- **问题机制**：在 FastAPI/uvicorn 单事件循环中，任意同步 60s LLM 阻塞会冻结整个进程的所有 API（含心跳、健康检查、其他请求）。批量入库期 W2-W5 全部同步串行 → 服务对外不可用

- **改造方向**：
  1. 在 `llm_client` 引入 `httpx.AsyncClient`，提供 `acall_llm` / `acall_llm_json` 异步接口
  2. Judge / Refiner / Librarian / Auditor 全部改为 `async def`，沿调用栈向上传染到 W1-W5 任务编排层
  3. 重试装饰器换成 tenacity 的 `AsyncRetrying` 或 `retry` 的 async 模式
  4. `verify=False` 应通过配置开关控制（睿动需要时启用，生产校验证书）—— 见额外坑 D

- **影响面**：
  - Pipeline 调度层（W1-W6 的 orchestrator）必须全异步化
  - 测试桩（`_mock_llm_call`）需要提供 async 版本或保持同步但通过 `asyncio.to_thread` 桥接
  - 任何 `def run_xxx` 的 Agent 接口需重命名为 `arun_xxx`，旧同步保留为兼容期 wrapper

- **依赖关系**：无前置依赖，是 M0 第一块多米诺骨牌。坑 2/坑 5/坑 6 的异步化建立在此之上

---

### 坑 2 · Milvus 不稳定 / 连接断开重连

- **当前代码状态**：`vector_store.py` 未在本次上下文提供，但根据：
  - 决策书 §13 明确指出 "连接池 + 健康检查 + 自动重连（参考 ISS-Knowledge-Parser 的 ConnectionManager）"
  - `pymilvus 2.4` 已锁选型
  - W5 双写（向量+图谱）是核心数据流

- **问题机制**：Milvus 默认 gRPC 连接长时间空闲会断；Wiki-map V15 实测出现"重连超时 → 检索失败 → 整批回滚"

- **改造方向**：
  1. 引入 ConnectionManager 单例，封装 `connect/health_check/reconnect`，暴露 async context manager
  2. 健康检查走 `utility.get_server_version()`，失败触发重连，重连失败计数熔断
  3. 每次 `search/insert` 前轻量探活；批量写入用幂等 upsert（基于 `chunk_id` + `vector_type`）
  4. 决策书 §5.4 要求**双向量**（vec_redacted + vec_original）→ collection schema 必须支持 `vector_type` 字段和按密级路由

- **影响面**：W5 入库、块③ 召回、所有依赖 `vector_store.search()` 的检索路径

- **依赖关系**：依赖坑 1 完成异步化（pymilvus 2.4 已支持 async）；与坑 6（真嵌入）解耦，可并行推进

- **需人工验证**：本次未看到 `vector_store.py`，需确认当前是否已经存在 ConnectionManager 雏形，还是裸用 `connections.connect()`

---

### 坑 3 · Judge 阈值过严，KEEP 率 42%

- **当前代码状态**：
  - `judge.py` L92-111：决策规则**完全硬编码**：
    ```
    if kpi < DISCARD_THRESHOLD and llm_decision == DISCARD: → DISCARD
    elif kpi < ARCHIVE_THRESHOLD or llm_decision == ARCHIVE: → ARCHIVE
    elif llm_decision == DISCARD and confidence > 0.8: → DISCARD
    else: → llm_decision
    ```
  - L84-89：`effective_redundancy = max(redundancy, llm_redundancy)` 取并集 → 进一步推高冗余惩罚
  - 阈值常量 `DISCARD_THRESHOLD` / `ARCHIVE_THRESHOLD` 来自 `scoring/kpi_retain.py`（未提供），但从命名看为模块级常量，**无项目/行业维度配置入口**
  - 决策书 §13 明确："阈值可配置，按行业模板预设不同阈值"（§7.4 行业模板包含 `refiner-prompt.tmpl` 但未含 `judge-thresholds.yaml`）

- **问题机制**：
  - 单一全局阈值无法适配不同行业（制造规章严密 vs 能源 SOP 高频迭代）
  - `confidence > 0.8` 这个魔数在 mock LLM 中极易达到（见 `_mock_judge` 多处 `confidence = 0.92/0.95`）→ 大量误丢弃
  - Mock 模式的"过时通知 → DISCARD" 等硬规则（L137-141）会在真 LLM 模式下失效，造成行为不一致

- **改造方向**：
  1. 阈值外置到行业模板包：`templates/<industry>/judge-thresholds.yaml`，含 `discard_threshold` / `archive_threshold` / `confidence_floor` / `redundancy_weight`
  2. Settings 注入项目级覆盖：`project_id → industry_template → thresholds`
  3. 决策规则函数化（`decide(reasoning, kpi, confidence, thresholds) → Decision`），独立可测试
  4. 增加"放行 + 标记"档位：当 KPI 居中且 LLM 不确定时，进入 W4 SME 复核队列而非自动归档

- **影响面**：所有 Judge 调用方、行业模板初始化流程、单测 fixture

- **依赖关系**：独立；可在坑 1 之前完成（属于纯逻辑重构）

---

### 坑 4 · domain_id 分配不精，全归 regulation

- **当前代码状态**：
  - `llm_client.py` L235-278：`_mock_infer_domain_id()` 用一长串 `if any(kw in text for kw in [...])` 关键词匹配
  - L274-278 兜底：`return "regulation"`（**这就是 V15 踩坑的根因之一在 KAP 复刻**）
  - `refiner.py` L26-46：`_get_domain_list()` 缓存全局 `_domain_list_cache: str | None`，**单例缓存且无项目/租户隔离**（详见额外坑 B）
  - `refiner.py` L49-83：`_clean_domain_id()` 做了大量字符串清洗（提取 `[xxx]`、去 `L1/`、取冒号前），说明当前 LLM 输出格式不稳定，依赖事后清洗（详见额外坑 E）
  - `llm_client.py` L401-417：`_ENERGY_RELATION_TEMPLATES` 已为能源行业预置 7 个分支模板（安全/生产/环保/设备/应急/物流/采购），但 **domain_id 推断却没有同等深度的能源关键词树** —— 推断器与关系生成器的行业覆盖不一致
  - 决策书 §13 要求："必须给行业模板加 Refiner Prompt 指引，模板中含具体 domain 关键词字典"

- **问题机制**：
  - 关键词匹配硬编码在 Python 模块中 → 客户私有化时无法不改代码切换行业
  - `_get_domain_list()` 的全局单例缓存意味着多租户/多项目场景下，第一个加载的 Skills 会污染所有后续请求
  - mock 与真 LLM 路径下 domain_id 推断逻辑割裂（mock 走关键词，真 LLM 走 prompt + 后处理）→ 测试覆盖到的不是生产路径

- **改造方向**：
  1. domain 关键词字典外置到 `templates/<industry>/domain-keywords.yaml`，与 taxonomy.yaml 同源
  2. `_get_domain_list()` 改为按 `(org_id, project_id)` 维度缓存，TTL 过期；提供显式 invalidate 接口
  3. Refiner Prompt 模板按行业分发，prompt 中直接列出该行业完整 domain 树 + 每个 domain 的判别要点
  4. 兜底策略从硬编码 `"regulation"` 改为"未识别 → routing_pending 队列"，进入 DG 主审工位（决策书 §5.2 W2 行）

- **影响面**：Refiner / SkillsRouter Stage 2 / 行业模板加载器 / 多租户上下文

- **依赖关系**：与坑 3 共享"行业模板包"基础设施 → 建议合并设计

---

### 坑 5 · 图谱重启丢失（内存模式）

- **当前代码状态**：`graph_store.py` 未在本次上下文提供。但根据：
  - 决策书 §9.2 复用清单："GraphStore V8 双向索引 + 归一化 + 去重 …… 90%（持久化改 Neo4j）"
  - §10.4 已锁 Neo4j 5
  - `refiner.py` L86-103 `_validate_and_fix_relations()` 已实现关系端点校验，说明图谱写入前置已就绪
  - V15 原型基于 networkx 内存图（决策书 §13 明确踩坑）

- **问题机制**：networkx 进程内 dict + 重启即灭。任何 W5 入库的实体/关系在服务 OOM/重启后归零 → 块③ 图谱推理路径直接失效

- **改造方向**：
  1. 抽象 `GraphStore` 接口（`add_entity / add_relation / find_neighbors / search_path / merge_entity`），现有 networkx 实现降级为 `InMemoryGraphStore`（单测用）
  2. 新增 `Neo4jGraphStore` 实现，支持双图谱实例（主图 + 影子图，决策书 §5.3 全量重抽前置）
  3. 实体节点必须挂 `ontology_version` 属性，支持 `as_of` 历史回溯（§5.3）
  4. 双向索引（`_nodes` / `_edge_index` / `_synonym_map`）改为 Cypher 查询封装，保持调用语义一致

- **影响面**：W5 入库、块③ 图谱推理、本体演化（M2 阶段才上）、所有测试 fixture（必须提供两套）

- **依赖关系**：依赖坑 1 异步化（neo4j-python-driver 5+ 提供 AsyncDriver）；与坑 6 独立

- **需人工验证**：当前 `graph_store.py` 是否已有接口抽象层，还是直接暴露 networkx 对象给上层

---

### 坑 6 · Mock embedding 无语义区分

- **当前代码状态**：
  - 本次上下文中 `vector_store.py` / `embedding_*.py` 未提供
  - `llm_client.py` 仅处理 LLM chat completion，**未见 embedding 通道的 mock fallback 处理逻辑** —— 这意味着 embedding 可能也走了同样的"无 API Key → mock"分支但缺乏审视
  - 决策书 §10.3："嵌入模型必须本地化（bge-large-zh / bce-embedding）"
  - §13 踩坑："私有化必须接入真嵌入"

- **问题机制**：V15 的 mock embedding 通常返回随机向量或哈希向量 → 召回质量退化为字符串相似度 → 块③ 三路召回中的向量路径完全失效

- **改造方向**：
  1. 引入 `EmbeddingProvider` 抽象，至少三种实现：`MockEmbedding`（仅测试）/ `BGELocalEmbedding`（本地推理）/ `RuidongEmbedding`（睿动网关）
  2. `MockEmbedding` 必须有显式启用门槛（`KAP_ALLOW_MOCK_EMBEDDING=true`），生产环境拒绝启动
  3. 配合坑 2，写入 Milvus 时同时写 `embedding_model_version` 字段，便于模型升级后增量重嵌入
  4. 双向量（vec_redacted / vec_original）必须用同一模型版本，否则跨向量比较失效

- **影响面**：W5 入库、块③ 召回、所有用到 `embed()` 的链路

- **依赖关系**：依赖坑 2（Milvus collection schema 调整）；可与坑 1 并行

---

### 坑 7 · 单角色 Editor 无法企业 RBAC

- **当前代码状态**：
  - `api/middleware/auth.py` 未在本次上下文提供
  - 决策书 §5.2 要求 DG / SME / SEC / AIOps / Reader 五角色 × W1-W6 六工位矩阵
  - §9.1 复用 ISS-Auth + ISS-Common-Datascope（5 级数据权限）
  - V15 原型只有"Editor / Reader"二态

- **问题机制**：当前若 auth 中间件只识别 Editor 单角色，任何工位审核 API 都无法做角色路由（W4 必须 SME 主审、W2 DG 主审等都失效）

- **改造方向**：
  1. M0 阶段：扩展 JWT claims 至少含 `roles: List[str]`、`data_scope_level: int`、`access_level: int`（密级）
  2. 中间件提供 `RequireRole(*roles)` / `RequirePermission(perm)` FastAPI Dependency
  3. ReviewTask 模型（决策书 §5.2）的 `routing.role` 字段必须与角色枚举对齐
  4. M1 阶段再做 ISS-Auth 完整对接（JWT + Redis 会话 + IP 黑名单）

- **影响面**：所有审核台 API、所有写操作端点、前端登录态

- **依赖关系**：独立于其他 7 坑；但坑 8（密级）逻辑上同框架推进

- **建议**：M0 仅需"角色枚举 + 中间件骨架 + 字段预留"，**不需要完整 ISS 对接**。完整 RBAC 是 M1 工作

---

### 坑 8 · 仅 access_level 二元过滤

- **当前代码状态**：
  - 召回链路代码（`retrieval/`）和 `auth.py` 均未在本次上下文提供
  - 决策书 §8.1 明确：4 级密级（公开/内部/秘密/机密）+ **召回阶段过滤**（Milvus where 子句直接带 `access_level <= user_level`）
  - 当前若是二元（公开/内部）→ 无法承载敏感工艺参数、客户名等高密知识

- **问题机制**：二元过滤展示阶段过滤 = 高密向量被低密用户的查询命中 → 既低效又有泄露风险（决策书原话）

- **改造方向**：
  1. Milvus collection schema 增加 `access_level: int8`（0/1/2/3 对应公开/内部/秘密/机密）
  2. 双向量字段 `vec_redacted` / `vec_original` 与 access_level 联动：低密用户只能命中 vec_redacted
  3. 召回入口强制注入 `expr=f"access_level <= {user.max_access_level}"`，禁止旁路
  4. 展示层做二次校验（防御性深度），但不依赖它做主过滤
  5. M0 阶段：schema 字段 + 注入点预留即可，完整 4 级映射规则交 M2

- **影响面**：Milvus schema 迁移、所有 search 调用、双层存储联动

- **依赖关系**：依赖坑 7 的角色/密级 claims；依赖坑 2 的 Milvus 重构

---

## 3. 额外坑（Opus 4.7 代码分析新发现）

### 额外坑 A · Mock 与真 LLM 路径行为割裂

- `llm_client.py` L74-104：根据 system_prompt 关键词路由到 7 个 mock 函数。这些 mock 实现的"业务规则"（如 `_mock_judge` 中"过时通知 → DISCARD"L137-141）在真 LLM 模式下不存在
- **风险**：单测全绿，生产首日翻车
- **改造**：mock 应仅返回 schema 合规的随机/占位数据，不应内嵌业务判定逻辑

### 额外坑 B · `_get_domain_list()` 全局单例缓存（多租户事故源）

- `refiner.py` L23-46：`_domain_list_cache: str | None = None  # 模块级`
- **风险**：多项目/多租户场景，第一个加载的 Skills 永久污染后续请求
- **决策书要求**：§1.4 "单实例 + 多业务单元逻辑隔离"，当前实现违反此约束
- **严重度**：**M0 必修**（潜在的客户隔离事故）

### 额外坑 C · Mock 中硬编码部门名

- `llm_client.py` L401-417：`_ENERGY_RELATION_TEMPLATES` 直接把"安全生产部 / 总经理 / 班组长 / 消防队"等名词写在 Python 代码里
- 决策书 §7.4 行业模板要求这些都应在 `ontology-l1.yaml` 中
- **风险**：客户私有化时改组织架构需要改源码
- **归属**：M1（与行业模板包基建一起做）

### 额外坑 D · `verify=False` 硬编码（生产中间人攻击风险）

- `llm_client.py` L21：`http_client = httpx.Client(verify=False)`
- 注释说"睿动平台等部分 API 需要跳过 SSL 验证"，但**所有环境**都跳过
- **风险**：生产环境中间人攻击；安全审计不通过
- **改造**：通过 settings 开关，默认 `verify=True`；睿动需特殊处理时仅在 dev/sandbox 环境关闭
- **归属**：**M0 必修**（与坑 1 异步化合并 PR）

### 额外坑 E · Refiner `_clean_domain_id` 防御性清洗过重

- `refiner.py` L49-83：能识别 `'L1 [quality]'`、`L1/product`、带引号、带逗号 …… 5 种异常格式 → 反向证明当前 LLM 输出**很不稳定**
- **本质问题**：Prompt 工程不充分，靠后处理打补丁
- **改造**：M0 阶段加 prompt 中的 few-shot 示例 + JSON schema 约束输出
- **归属**：M1（与坑 4 prompt 工程一起做）

### 额外坑 F · tenacity @retry 与 mock fallback 静默冲突

- `llm_client.py` L426-470：装饰器要求重试 3 次后抛错，但 catch-all 的 `except Exception` 又静默 fallback 到 mock 并返回数据
- **风险**：生产环境 LLM 故障，调用方完全感知不到，数据被 mock 污染入库
- **严重度**：**M0 必修**；mock fallback 必须只在测试环境启用（受环境变量门控）

---

## 4. M0 阶段建议改造顺序（DAG）

```
                                        [坑 3 Judge 阈值外置]    （独立，3-5 人时）
                                                    ↓
[坑 4 domain 关键词外置]  → 共享行业模板包基建 ←  [行业模板包加载器骨架]
                                                    ↓
[坑 1 LLM 异步化 + 坑 D verify 开关 + 坑 F mock 门控] ─┐
        │                                              ├──→ [坑 2 Milvus ConnectionManager]
        │                                              │              ↓
        │                                              │       [坑 6 真 Embedding 接入]
        │                                              │              ↓
        │                                              ├──→ [坑 5 Neo4j GraphStore 替换]
        │                                              │
        ↓                                              ↓
[坑 7 RBAC 中间件骨架 + 角色枚举]
        ↓
[坑 8 Milvus schema 加 access_level + 召回注入]

[坑 B 多租户缓存] —— 与坑 4 同 PR 一起改
[坑 A mock 业务逻辑剥离] —— 与坑 1 同 PR 一起改
```

### 工时估算（人时，P50）

| # | 任务 | 估时 | 说明 |
|---|---|---|---|
| 3 | Judge 阈值外置 + 决策函数化 | 6 | 纯逻辑，最先动手回血 |
| 4a | 行业模板包加载器（domain-keywords.yaml + judge-thresholds.yaml 共用） | 8 | 与坑 3 协同 |
| 4b | Refiner domain 推断重构 + 多租户缓存（修坑 B） | 6 | |
| 1 | LLM 全链路异步化（含 Mock 桥接、修坑 A/D/F） | 16 | 涉及全栈，是 PR 大头 |
| 2 | Milvus ConnectionManager + 健康检查 + 双向量 schema | 12 | |
| 6 | EmbeddingProvider 抽象 + bge 本地接入 | 10 | |
| 5 | Neo4j GraphStore 实现 + InMemory 降级 + 测试双 fixture | 20 | M0 最重 |
| 7 | RBAC 中间件骨架（5 角色枚举 + JWT claims 预留） | 8 | M0 仅要骨架 |
| 8 | Milvus access_level 字段 + 召回注入点 | 6 | M0 仅要字段不做完整 4 级路由 |

**M0 总计**：约 **92 人时**（≈ 2-2.5 周单人 / 1 周双人）

---

## 5. 建议人工验证的点

本次分析受限于上下文，以下文件需要打开核对，可能影响 DAG 估时：

1. **`vector_store.py` 当前实现**：是否已有 ConnectionManager？是否已支持双向量字段？
2. **`graph_store.py` 当前实现**：是 networkx 直接暴露，还是已有接口抽象？影子图谱接口是否预留？
3. **`scoring/kpi_retain.py` 中阈值常量**：是模块级常量还是已有配置层？
4. **`api/middleware/auth.py`**：当前角色识别是单态、二态还是已有多角色雏形？
5. **`configs/llm_settings.json`**：是否已含行业模板路径？是否已含密级映射？
6. **embedding 通道的实际代码位置**：是单独文件还是混在 vector_store 中？是否同样有 mock fallback 静默失败问题？
7. **W5 双写事务**：当前是否做了 Milvus + Neo4j 的最终一致性保证？是否有补偿机制？
8. **Mock LLM 路径在 CI 中的占比**：是否所有集成测试都跑在 mock 模式下导致真路径无回归？

---

## 6. 跨坑结构性观察

### 6.1 行业模板包基础设施缺位（最关键）

决策书 §7.4 设计的 `templates/<industry>/*.yaml` 是**坑 3、坑 4、额外坑 C** 的共同解药，但当前代码中所有行业知识都散落在 Python 硬编码（`_ENERGY_RELATION_TEMPLATES`、`_mock_infer_domain_id`、`_ROUTE_RULES`）。

**M0 应优先建立模板加载器骨架**，否则后续每修一个坑都要碰一次行业知识。

### 6.2 同步/异步混用是定时炸弹

坑 1 不解决，坑 2/坑 5/坑 6 的异步化都做不彻底。建议 M0 第一周专注异步化重构，第二周才动其他坑。

### 6.3 测试体系断层

mock 层内嵌大量业务逻辑导致单测无法覆盖真实路径。M0 应同时引入"真 LLM 烟雾测试"环境（哪怕 1 个用例），用睿动 + Claude Sonnet 跑端到端验证。

---

## 附录 · 文档变更记录

| 版本 | 日期 | 变更说明 |
|---|---|---|
| v1.0 | 2026-04-28 | 首版。Opus 4.7 via kap-delegate 分析产出，KAP 项目组复核 |
