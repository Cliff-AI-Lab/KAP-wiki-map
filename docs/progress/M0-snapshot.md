---
title: M0 KAP-Lite 进度快照
milestone: M0
version: v3
date: 2026-04-29
commits: 23
tests: +250
hours: ~12.5
opus-estimate: 112h
savings: 89%
status: completed
tags: [kap, m0]
---

> **起点** · 设计蓝本：[决策书](../01-技术决策书.md) / [PRD](../02-产品需求PRD.md) · 下一步：[→ M1 企业级 v1](M1-snapshot.md)

# M0 KAP-Lite 进度快照 v3

**M0 全部 9 大坑 + 4 个顺手坑全部完工（23 commits / ~12.5 人时实际 vs Opus 估算 112h，节省 89%）**

> 基于 [Wiki-map V15](../../_refs/wiki-map/bookworm-agent/) + ISS 接入 + 睿动；
> 9 大坑全部技改；块②③ 主流程跑通；测试 250/252 ✓；可演示给客户。

---

## 全景成果

### 坑 1（LLM 全链路异步化）
- `httpx.Client` → `AsyncClient`，pipeline `ThreadPoolExecutor` → `asyncio.gather` + `Semaphore`
- 双轨保留（sync `run_*` + async `arun_*`）
- tenacity 业务异常不重试 + `reraise=True`
- 影响代码：[`backend/packages/distillation/`](../../backend/packages/distillation/)

### 坑 2（Milvus ConnectionManager + 双向量）
- `MilvusConnectionManager` 健康检查 + 熔断
- schema 增加 `vector_type` / `embedding_model_version` / `access_level` int8 字段
- 原始向量与脱敏向量物理分离（M1 #1 脱敏管线写入侧用）
- 影响代码：[`backend/packages/storage/vector_store.py`](../../backend/packages/storage/vector_store.py) / [`milvus_connection.py`](../../backend/packages/storage/milvus_connection.py)

### 坑 3（Judge 阈值外置）
- 阈值 → `judge_thresholds.yaml`
- 决策函数化 `decide_action()` 纯函数
- `R3 review` 通道独立
- 影响代码：[`packages/distillation/agents/judge.py`](../../backend/packages/distillation/agents/judge.py) / [`scoring/judge_thresholds.py`](../../backend/packages/distillation/scoring/judge_thresholds.py)

### 坑 4a+4b（行业模板 + 多租户域）
- 制造/能源行业模板 loader + 多租户 domain 推断
- 含坑 B：`domain_path` 覆写
- 影响代码：[`packages/templates/`](../../backend/packages/templates/) / [`distillation/templates_loader.py`](../../backend/packages/distillation/templates_loader.py)

### 坑 5（Neo4j GraphStore）
- 移除内存模式静默 fallback
- 加 `ontology_version` 字段（M3 双层本体使用）
- 启动失败 fail-fast 而非误用 InMemory
- 影响代码：[`packages/storage/graph_store.py`](../../backend/packages/storage/graph_store.py)
- 决策依据：[决策书 §5.6 持久化](../01-技术决策书.md)

### 坑 6（EmbeddingProvider 抽象）
- `EmbeddingProvider` ABC + `Mock` / `Ruidong` / `BGELocal` 三实现
- `current_model_version()` 写入物料元数据
- 影响代码：[`packages/storage/embedding_provider.py`](../../backend/packages/storage/embedding_provider.py) / [`embedder.py`](../../backend/packages/storage/embedder.py)

### 坑 7+8（RBAC + 召回密级路由）
- 5 KAP 角色枚举（DG/SME/SEC/AIOps/READER）+ V15 admin/editor 别名兼容
- `UserContext.max_access_level: int` 自动同步
- `RequireRole/RequireAccessLevel` Dependency
- retriever 三处 `vector_store.search()` 注入 `max_access_level` filter
- 影响代码：[`packages/common/roles.py`](../../backend/packages/common/roles.py) / [`auth.py`](../../backend/packages/common/auth.py) / [`retrieval/retriever.py`](../../backend/packages/retrieval/retriever.py)
- 决策依据：[决策书 §8.1 RBAC + 数据权限 + 密级三维](../01-技术决策书.md)

### 顺手坑 A/B/D/F
- **A** Settings 强制策略（`model_post_init` enforce sandbox/prod）
- **B** domain_path 覆写（QA 引擎已计算时 retriever 直接用）
- **D** verify_ssl 开关（dev 可关、sandbox/prod 强制开）
- **F** mock fallback 门控（sandbox/prod 完全屏蔽 mock embedding/llm）
- 影响代码：[`packages/common/config.py`](../../backend/packages/common/config.py)

---

## Commits 时间线（全部 23 个）

| Commit | 内容 | 测试 |
|---|---|:---:|
| `1dd9ebd` | M0 Day 0 骨架 + V15 主干导入 | — |
| `b56dab5` | 加 .claude/ 到 .gitignore | — |
| `ff41e39` | T1 · KAP 品牌化 + T5 Neo4j compose | — |
| `25f9124` | T2 · M0 技术债务地图（Opus 4.7 产出）| — |
| `7125455` | T4 · 三环境配置（.env.dev/sandbox/prod + master）| — |
| `7d08a42` | 坑 3 · Judge 阈值外置 + 决策函数化 + R3 review 通道 | +22 ✓ |
| `e8f7dad` | 坑 4a+4b · 行业模板加载器 + 多租户域推断（含坑 B）| +29 ✓ |
| `1560bbe` | CLAUDE.md 进度快照 v1 | — |
| `ad8e2b9` | 坑 1 批 0 · 三环境 settings + verify_ssl/allow_mock 门控 | +18 ✓ |
| `37b8b3e` | 坑 1 批 1 · llm_client 双轨（acall_llm/_json）+ 坑 D/F 落地 | +14 ✓ |
| `e9d2fc1` | 坑 1 批 2 · 4 个 agent arun_* 异步入口 | +9 ✓ |
| `c7a6b13` | 坑 1 批 3 · pipeline asyncio.gather + Semaphore | +6 ✓ |
| `87949c5` | 坑 1 批 4 · API endpoint 切 `await arun_pipeline` | — |
| `973aebc` | CLAUDE.md 进度快照 v2 | — |
| `d1b5691` | 坑 6 · EmbeddingProvider 抽象 + bge 接入 + 异步双轨 | +20 ✓ |
| `6c169ad` | docs(refs) · 修复 _refs 乱码 + 建立 Wiki-map/ISS 关联索引 | — |
| `1ad3d0f` | feat(test-samples) · 48 文档按行业打包为 KAP 测试样例集 | — |
| `8f9e387` | 坑 2 · Milvus ConnectionManager + 双向量 schema（含坑 8 access_level 预留）| +13 ✓ |
| `7e385ef` | docs(test-samples) · 用 markdown link 全面理顺 Obsidian 图谱关系 | — |
| `df5c9c1` | 坑 5 · Neo4j GraphStore 修静默 fallback + 加 ontology_version | +14 ✓ |
| `f751be7` | feat(test-samples) · 为 39 份非 .md 样本生成 .md 索引页 | — |
| `5bc2047` | feat(test-samples) · 给 9 份 V15 原始 .md 注入 navigation header | — |
| `4ff7af8` | 坑 7+8 · KAP 5 角色枚举 + RBAC Dependency + 召回阶段密级路由 | +25 ✓ |

---

## 测试基线

`250/252 unit ✓`（仅 V15 既有 connector mock 数据漂移 2 项与 KAP 改造无关）

---

## M1 启动条件（M0 已交付）

- ✓ 三环境隔离 + 强制策略
- ✓ LLM/Embedding 全链路异步 + 双轨可降级
- ✓ Milvus 双向量 schema + 召回密级过滤
- ✓ Neo4j GraphStore fail-fast + 本体版本化
- ✓ KAP 5 角色 + RBAC Dependency
- ✓ 行业模板 + 多租户域推断
- ✓ 测试样例集（48 文档，5 行业子集，Obsidian 图谱完整）

---

## 关联资源

- **决策依据**：[决策书](../01-技术决策书.md) D5/D7/D8/D11/D17 + §5.6 / §8.1
- **实施计划**：[M0-tech-debt](../M0-tech-debt.md)（Opus 4.7 产出 9 坑地图） / [M0-tech-debt-async-plan](../M0-tech-debt-async-plan.md)（坑 1 异步 5 批迁移）
- **下一阶段**：[→ M1 企业级 v1](M1-snapshot.md)
- **测试样例**：[test-samples/](../../test-samples/)（48 文档 5 行业子集）
