---
title: M4 重抽影子库 进度快照
milestone: M4
version: v1
date: 2026-04-29
commits: 5
tests: +59
hours: ~9
opus-estimate: 15-20h
savings: ~50%
status: completed
tags: [kap, m4]
---

> [← M3 高级治理](M3-snapshot.md) · 设计蓝本：[决策书 §5.3 D8 工程闭环](../01-技术决策书.md) · → M5（待启动）

# M4 重抽影子库（5 commits / ~9h vs Opus 估 15-20h，节省 ~50%）

> 演化机制工程闭环 — 影子库 + 增量哈希 + 灰度切换 + 7 天回滚

---

## 全景成果

### 影子库抽象 + ontology_version 隔离
M4 lite 用 `ontology_version` 标签逻辑隔离（决策书 §5.3 原文"独立 Neo4j 实例"是建议非硬约束）；多 (project_id, version) 桶完全隔离；同实体合并 doc_ids，关系去重；swap_shadow_to_main 切换 + 记录 previous_main；rollback_to_previous 一键回滚。
- **关联代码**：[`packages/rebuild/shadow_graph.py`](../../backend/packages/rebuild/shadow_graph.py)

### 增量哈希（决策书 §5.3 成本控制命门）
- compute_chunk_hash → SHA-256 hex 64 字符
- ChunkHashCache（M4 lite 内存模式；M5 接 PG 跨周期）
- should_reextract：无缓存 / 哈希变 / 空哈希 → 重抽；哈希一致 → 跳过 W4 LLM 抽取，仅按新本体重映射类型
- **关联代码**：[`packages/rebuild/incremental_hash.py`](../../backend/packages/rebuild/incremental_hash.py)

### 重抽编排器（决策书 §5.3 全量重抽机制）
- start_rebuild 创建 RebuildJob → arun_rebuild 异步主循环
- asyncio.gather + Semaphore(4) 并发抽取（M0 坑 1 模式）
- cache hit → 跳过 W4，仅记 hash_hit；cache miss → 调注入的 extractor → 写影子图谱
- 单 chunk 失败不阻断；整体失败 → cancel_shadow 清掉影子库桶
- progress 实时更新；完成时强制 progress=1.0
- **关联代码**：[`packages/rebuild/rebuild_orchestrator.py`](../../backend/packages/rebuild/rebuild_orchestrator.py)

### 灰度切换 + 回滚（决策书 §5.3 7 天观察期）
- compare_versions → RebuildDiffReport（节点 / 实体 / 关系数 + 类型分布对比 + 启发式 safe_to_promote）
- promote_shadow（force 跳过检查）
- rollback_promotion 一键回滚到上版本
- 启发式安全规则：节点数变化 > 30%（增或减）/ 关键类型在新版本消失 → 不安全
- **关联代码**：[`packages/rebuild/switch_orchestrator.py`](../../backend/packages/rebuild/switch_orchestrator.py)

### API endpoints（6 端点）
- `POST /api/v1/rebuild/jobs` 启动重抽
- `GET  /api/v1/rebuild/jobs` / `GET /jobs/{id}` 列出 / 单条
- `GET  /api/v1/rebuild/diff` 对比两版本
- `POST /api/v1/rebuild/promote` SME 灰度切换（force 跳过检查）
- `POST /api/v1/rebuild/rollback` 一键回滚
- 权限：所有 POST `RequireRole(SME)`（决策书 §5.3 SME 主导）
- **关联代码**：[`api/routers/rebuild.py`](../../backend/api/routers/rebuild.py)

### 监测条件 2-4 stub（M5 完整 LLM 实现预留）
- propose_relation_solidification（条件 2：自定义关系反复出现 → 提议固化）
- propose_relation_split_for_drift（条件 3：关系语义漂移 → 提议拆分）
- propose_standard_upgrade（条件 4：行业标准升版 → 提议本体扩展）
- M4 lite 行为：返回 None + log warning（不抛异常，不调 LLM）
- **关联代码**：[`packages/ontology/evolution_proposer.py`](../../backend/packages/ontology/evolution_proposer.py)

---

## Commits 时间线

| Commit  | 内容                                          | 测试  |
|:---|:---|:---:|
| `a2ff978` | 批 1 影子库抽象 + 增量哈希                     | +25 ✓ |
| `de90c97` | 批 2 重抽编排器（asyncio.gather + 进度）       | +10 ✓ |
| `f8ea6dc` | 批 3 灰度切换 + 回滚（启发式安全检查）         | +10 ✓ |
| `76f91c3` | 批 4 API 6 端点                                | +10 ✓ |
| `32463a3` | 批 5 监测条件 2-4 stub（M5 完整版预留）        | +4 ✓  |

---

## 测试基线

`714/716 unit ✓`（V15 mock drift 仍 2 个）

---

## M5 启动条件（M4 已交付）

- ✓ 影子库抽象（ontology_version 隔离）
- ✓ 增量哈希（chunk hash + cache）
- ✓ 重抽编排器（asyncio.gather + Semaphore + 进度）
- ✓ 灰度切换 + 回滚（启发式安全检查）
- ✓ 6 API 端点（RequireRole SME）
- ✓ 监测条件 2-4 stub（M5 完整 LLM 实现）

---

## M5 待启动方向

- 监测条件 2/3/4 完整 LLM 实现（自定义关系固化 / 语义漂移拆分 / 行业标准升版）
- as_of 历史回溯查询（Cypher with timestamp）
- 7 天自动观察 + 指标恶化告警
- 复杂多维度指标对比（召回率 / SME 驳回率 / 命中率）
- 独立物理 Neo4j 实例的影子库（生产部署优化）
- 跨重抽周期的 ChunkHashCache PG 持久化
