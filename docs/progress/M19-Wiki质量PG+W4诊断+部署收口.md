---
title: M19 Wiki 质量 PG + W4 诊断 + diff UI + 部署收口 进度快照
milestone: M19
version: v1
date: 2026-05-02
commits: 5
tests: +15 backend / +7 frontend / +4 live_llm
hours: ~5
opus-estimate: 16-22h
savings: ~75%
status: completed
tags: [kap, m19]
---

> 进程链：[M0 KAP-Lite](M0-KAP-Lite.md) → ... → [M18 Wiki 质量闭环 + 前端管理面板](M18-Wiki质量闭环%2B前端管理面板.md) → **【M19 Wiki 质量 PG + W4 诊断 + diff UI + 部署收口】** → 部署期 / M20⬜

# M19 Wiki 质量 PG + W4 诊断 + diff UI + 部署收口（5 commits / ~5h vs Opus 估 16-22h，节省 ~75%）

## 全景成果

### M19 #1 · Wiki 质量评分 PG 持久化 + 趋势 + 前端时间序列
后端：
- `wiki_quality.py` 加 `_history` 列表 + `_pg_sink` + `set_wiki_quality_pg_sink` + `_fire_and_forget`
- 新模块 `pg_wiki_quality.py`（仿 `pg_query_log`，write-through）
  - DDL + 双索引（project_id+scored_at / page_id+scored_at）
  - 启动水化最近 N 条到 `_history` + `_scores`
  - INSERT-only（每次评分一行历史）
- `compute_wiki_quality_trend`：按时间桶聚合 + delta + trend_alert（跌幅 > 10pp）
- API `GET /wiki-quality/trend`
- `main.py` 由 `KAP_WIKI_QUALITY_PG=1` 启用；shutdown 加挂

前端：
- `observabilityApi.ts` 加 `fetchWikiQualityTrend` + `WikiQualityTrend` 类型
- `WikiQualityDashboard` 加历史趋势线图（recharts `LineChart` + delta + alert 高亮）
- i18n 加 3 个 `wq.trend*` keys + zh/en

测试：+6 后端 / +1 前端

### M19 #2 · W4 抽取链式自动评分（规则化诊断）
新模块 `packages/observability/extraction_quality.py`：
- 4 维**规则化评分**（不调 LLM；每文档抽取后立即跑，开销可忽略）
  - `entity_density` 实体密度 5-15/k 字符为最优
  - `relation_validity` 关系/实体比 ≥ 0.3 为充分
  - `confidence_avg` 实体平均置信度
  - `sensitive_handled` 敏感词检出 → 1.0
- `ExtractionMetric` Pydantic + `record / list / aggregate`
- LLM 失败（error 非空）→ overall=0 + alert
- 5000 metric 内存上限（FIFO）

W4 入口接入：
- `entity_extractor` 入口尾部 + LLM 失败早返回处都调 `record_extraction_metric`
- try/except 兜底：诊断失败不阻塞抽取

API：
- `GET /observability/extraction-quality`
- `GET /observability/extraction-quality/aggregate`

测试：+9（4 评分 + 3 list/aggregate + 1 空 + 1 W4 入口集成）

### M19 #3 · PromptVersion 版本对比 UI（行级 diff）
- `PromptVersionManager` 加第三个 tab "版本对比"
- `DiffView` 组件：左右两个 select 选版本 + 行级 diff 显示
- `computeLineDiff`（LCS 算法 O(n*m)）：返回 common/added/removed 三态
- 新增行绿色 / 删除行粉色 / 共有行默认色
- diff 摘要：`+N / -M` 计数
- 完全一致时显示提示
- i18n 加 9 个 `pv.diff*` keys + zh/en

测试：+7（1 空状态 + 1 真 diff 渲染 + 4 `computeLineDiff` 算法 + 1 已有测试通过）

### M19 #4 · 真 LLM 测试覆盖扩展（块① 架构师）
新增 `tests/integration/test_live_llm_architect.py`：
- `recognize_industry`：能源样本下应识别 `industry_code` 非空（弱断言）
- `recognize_industry`：空样本短路返回空（验证 short-circuit）
- `propose_taxonomy`：manufacturing 模板 + 样本不会全 drop
- `propose_taxonomy`：未注册行业返回空（兜底）

弱断言策略：长度 / 类型 / 非空 / `stage_used` 在合法集；不强制具体值。
默认 deselect（`addopts -m 'not live_llm'`）；显式 `pytest -m live_llm` 跑。
12 live_llm 测试（原 8 + 4 新）。

### M19 #5 · 部署收口
**生产 docker-compose**（`infra/docker-compose.prod.yml`）：
- 4 副本 kap-api + 资源限制 + healthcheck
- PG / Neo4j / Milvus / Redis 仅内网，不暴露端口
- nginx :443 上游 + TLS 终端
- 通过 `.env.prod` 注入所有密钥

**nginx 反向代理**（`infra/nginx.conf`）：
- 80 → 443 强制重定向
- /api/ proxy 到 kap-api 集群（200M 上传上限 + 300s 超时）
- 静态前端走同 upstream（kap-api 镜像内置 `frontend/dist`）

**分区迁移脚本**（`backend/scripts-backend/migrate_partitioned.py`）：
- `--dry-run` 仅打印 DDL（已验证）
- `--apply` 执行完整迁移（停写期）
- `--ensure-current` 周度 cron 用，建当月 + 下月分区

**部署 checklist**（`docs/deployment/checklist.md`）：
- 10 大类 ~50 项验证：环境变量 / DB 迁移 / LLM 网关 / ISS 集成 / Neo4j / 监控 / 灾备 / 安全
- 上线签字栏

**Neo4j 物理化指南**（`docs/deployment/neo4j-physical.md`）：
- 选型决策矩阵（PoC / 生产 / 大规模）
- 物理实例配置（heap / pagecache / APOC）
- 切换步骤（从 docker-compose 过度到独立实例）
- 备份 / 恢复 cron
- 影子库（M4 lite）配合策略
- 性能调优清单

---

## Commits 时间线

| Commit    | 内容                                              | 测试           |
|:---|:---|:---:|
| `c705cd4` | #1 Wiki 质量 PG 持久化 + 趋势 + 前端时间序列         | +6 后 +1 前    |
| `4ee32e2` | #2 W4 抽取链式自动评分（规则化诊断）                  | +9 后          |
| `c122c75` | #3 PromptVersion 版本对比 UI（行级 diff）            | +7 前          |
| `7029e33` | #4 真 LLM 测试覆盖 architect 模块（块①）             | +4 live_llm    |
| `(5)`    | #5 部署收口（compose.prod / nginx / 迁移脚本 / 文档） | docs           |

---

## 测试基线

`1031/1033 unit ✓` 后端 + `58 frontend tests passed` + 12 live_llm（默认 deselect）。

## M19 已交付

- ✓ Wiki 质量评分 PG 持久化 + write-through sink + 启动水化
- ✓ Wiki 质量历史趋势（按时间桶 + delta + trend_alert）+ 前端 LineChart
- ✓ W4 抽取链式诊断（规则化 4 维，不调 LLM；每文档跑）
- ✓ PromptVersion 版本对比 UI（LCS 行级 diff，三态高亮）
- ✓ 真 LLM 测试覆盖块①（industry_recognizer / taxonomy_builder）
- ✓ 生产 docker-compose + nginx + TLS
- ✓ 时序分区迁移脚本（dry-run / apply / ensure-current）
- ✓ 部署 checklist（50+ 项）+ Neo4j 物理化指南

---

## 部署期待启动

1. 真实环境部署（按 `docs/deployment/checklist.md` 走完 10 章）
2. 首批客户 PoC 上线
3. ISS-Job 真环境联调（接通 JWT + 真 Quartz 跑 cron）
4. 物理 Neo4j 实例切换（按 `docs/deployment/neo4j-physical.md`）

## M20 候选方向（未启动）

- W4 抽取诊断 PG 持久化（M19 #2 当前内存）
- 影子库物理多 DB 隔离（Neo4j Enterprise）
- 多模态文档解析（图片 / 表格 / PDF 复杂排版）
- KAP 横向多租户（共享 PG / 各租户独立 Neo4j DB）
- 客户共建本体迁移工具（L2 跨项目 / 跨环境的 export-import）
