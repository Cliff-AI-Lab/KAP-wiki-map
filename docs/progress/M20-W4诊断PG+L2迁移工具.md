---
title: M20 W4 诊断 PG + L2 本体迁移工具 进度快照
milestone: M20
version: v1
date: 2026-05-02
commits: 3
tests: +17 backend
hours: ~2
opus-estimate: 8-10h
savings: ~80%
status: completed
tags: [kap, m20]
---

> 进程链：[M0 KAP-Lite](M0-KAP-Lite.md) → ... → [M19 Wiki 质量 PG + W4 诊断 + 部署收口](M19-Wiki质量PG%2BW4诊断%2B部署收口.md) → **【M20 W4 诊断 PG + L2 迁移工具】** → 部署期 / M21⬜

# M20 W4 诊断 PG + L2 本体迁移工具（3 commits / ~2h vs Opus 估 8-10h，节省 ~80%）

## 全景成果

### M20 #1 · W4 抽取诊断 PG 持久化 + 趋势 API
- `extraction_quality.py` 加 `_pg_sink` + `set_extraction_quality_pg_sink` + `_fire_and_forget`
- 新模块 `pg_extraction_quality.py`（仿 `pg_wiki_quality` M19 #1）
  - DDL `extraction_metrics` 表 + 双索引（project+extracted_at / doc+extracted_at）
  - 17 字段全字段持久化（4 维评分 + 原始计数 + alert）
  - 启动水化最近 N 条到 `_metrics`
  - INSERT-only write-through
- `compute_extraction_quality_trend`：按时间桶聚合 + delta + trend_alert（与 wiki_quality 一致接口）
- API `GET /extraction-quality/trend`
- `main.py` 由 `KAP_EXTRACTION_QUALITY_PG=1` 启用；shutdown 加挂
- `docker-compose.prod.yml` 启用该开关

测试：+3（trend 空 / 跌幅告警 / PG sink 被调）

### M20 #2 · L2 本体迁移工具（跨项目跨环境）
新模块 `packages/ontology/migration.py`：
- `OntologyExportBundle`（schema_version 1.0 + exported_at + 多版本数组）
- `export_l2_ontology` / `serialize_bundle` / `export_to_file`（JSON / YAML 双格式）
- `deserialize_bundle` / `import_l2_ontology` / `import_from_file`
- **三冲突策略**：
  - `rename` — 同 type_id 加 `_imported` 后缀（默认；零风险）
  - `skip` — 跳过已存在的 type
  - `overwrite` — 覆盖（生产慎用，需 SME 显式选择）
- 目标项目无既有 L2 → 直起 `ont-v1.0.0`；有既有 → bump minor
- L1 拒绝（仅 L2 走客户共建）
- `ImportReport` 含 renamed / overwritten / skipped 详情

API：
- `GET /ontology/migration/export?project_id=X[&fmt=yaml][&include_history=true]`
- `POST /ontology/migration/import {target_project_id, bundle, on_conflict}`（SME 权限）

CLI：
- `backend/scripts-backend/migrate_ontology.py`
  - `export --project p_src --out ont.yaml [--current-only]`
  - `import --file ont.yaml --target p_tgt [--conflict {rename,skip,overwrite}]`

支持工作流：导出 → SME 离线编辑 YAML → 导入；适用 PoC → 生产迁移、跨部门复用、跨环境同步。

测试：+14（export 3 + serialize 2 + file IO 2 + import 6 + file round-trip 1）

---

## Commits 时间线

| Commit    | 内容                                              | 测试           |
|:---|:---|:---:|
| `b9bb55c` | #1 W4 抽取诊断 PG 持久化 + 趋势 API                  | +3 后          |
| `815b358` | #2 L2 本体迁移工具（export/import + CLI + API）       | +14 后         |
| `(3)`    | #3 进度快照 + CLAUDE.md 看板                         | docs           |

---

## 测试基线

`1048/1050 unit ✓` 后端 + `58 frontend tests passed` + 12 live_llm（默认 deselect）。

## M20 已交付

- ✓ W4 抽取诊断 PG 持久化（write-through + 启动水化）
- ✓ W4 诊断时间趋势 API（与 wiki_quality 接口对齐）
- ✓ L2 本体跨项目 export/import（JSON / YAML 双格式）
- ✓ 三冲突策略（rename / skip / overwrite）
- ✓ SME 权限的导入 API + 离线 CLI 工作流
- ✓ 部署 compose 启用全部 6 个 observability PG 持久化开关

---

## 部署期就绪

KAP 后端代码与部署资产**已全部就位**：
- 6 个 observability 表全 PG 持久化（DecisionLog / QueryLog / RecallEval / PromptVersion / WikiQuality / ExtractionQuality）
- 时序分区迁移脚本（M19 #5）
- 客户共建工具（M20 #2）
- 生产 docker-compose + nginx + TLS（M19 #5）
- 50+ 项部署 checklist + Neo4j 物理化指南（M19 #5）

可按 `docs/deployment/checklist.md` 执行真实环境上线。

## M21 候选方向（部署期之后）

- 多模态文档解析 lite（图片 OCR + 表格抽取整合到 W2 ingest）
- 横向多租户基础（tenant_id 字段 + 数据隔离）
- 前端 W4 抽取诊断看板（接 M20 #1 trend API + M19 #2 list/aggregate）
- 前端 L2 迁移向导 UI（导出下载 / 上传导入 + 冲突预览）
- Neo4j Enterprise 多 DB 影子库
- 真 LLM 测试覆盖剩余模块（conflict_detector / facet_advisor / llm_router）
