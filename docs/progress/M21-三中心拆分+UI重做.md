---
title: M21 三中心拆分 + UI 重做 + backend 配置收尾 进度快照
milestone: M21
version: v1
date: 2026-05-16
commits: 11
tests: 既有 1048/1050 unit + 58 frontend tests + 12 live_llm 不变（M21 无新增 unit，UI 改造 + 部署文档为主）
hours: ~10
opus-estimate: 50-60h
savings: ~80%
status: completed
tags: [kap, m21, three-centers, ui-redesign, deployment]
---

> 进程链：[M0 KAP-Lite](M0-KAP-Lite.md) → ... → [M20 W4 诊断 PG + L2 迁移工具](M20-W4诊断PG%2BL2迁移工具.md) → **【M21 三中心拆分 + UI 重做】** → [M22 多模态解析增强 + 知识中心补强（候选）](M22-多模态解析增强（候选）.md)⬜

# M21 三中心拆分 + UI 重做 + backend 配置收尾（11 commits / ~10h vs Opus 估 50-60h，节省 ~80%）

## 主线

M21 不是单一技术里程碑，是 **部署期对齐 + 三中心边界重划**：决策书 §3.1 三层视图 + M19 #5 部署收口 阶段后，把单体后端按业务边界拆为三个**松耦合可独立部署**的中心，前端做配套 UI 重做（三 tab 框架 + 统一设计语言 + 亮色主题 + 概览页）。

**为什么 M21 才动**：M0-M20 阶段单体 backend（`api.main:app`）跑得够用，业务边界没收敛清楚；M20 收尾后六工位 + 4×6 矩阵 + 影子库重抽 + 三路召回 全部稳定，**业务边界自然显形**：
- 咨询中心 architect — AI 对话式建本体（W1-W5）
- 知识中心 storage — 入库 + 治理 + 影子库（W6 + 矩阵）
- 消费中心 portal — 三路召回 + 仪表盘

---

## 全景成果

### M21 #1 · 三块松耦合拆分（5d8518f）
- 新增 `backend/api/main_architect.py` / `main_portal.py` / `main_storage.py`，每个中心独立 FastAPI app
- `api/app_factory.py` 抽象 router 注册逻辑，按中心装载不同 router 子集
- `backend/Dockerfile.architect` / `Dockerfile.portal` / `Dockerfile.storage` 三 Dockerfile
- `run_architect.py` / `run_portal.py` / `run_storage.py` 启动入口（8011 / 8012 / 8013）
- `packages/integration/clients.py` 服务间 HTTP SDK（StorageClient / ArchitectClient / PortalClient）
- 一体化打包模式（`run_dev.py:8001`）保留，PoC / 小客户用单进程加载全 14 routers

### M21 #2 · 前端三中心 tab（92fc0bf）
- `frontend/src/components/v15/CenterShell.tsx` 三中心壳子
- 路由按中心分：`/consult` / `/governance` / `/reader`
- 顶栏 tab 切换，每个中心保留独立 sub-router

### M21 #3 · 咨询中心可用 + UI 重做 + 三块边界重划（c2a77ff）
- ConsultHome 从原 `WikiTree` 中拆出
- 块②/块③ 不再在 ConsultHome 干预，边界清晰

### M21 #4 · 三中心统一设计 — claude-frontend-skills · Nordic Minimalism（b146da6）
- 调用 `claude-frontend-skills` 的 `frontend-design` skill（参考 [memory: 前端设计 skill 路径](../../memory/reference_frontend_design_skill.md)）
- `distinctive.css` 注入 Nordic Minimalism 色板 + 字体
- `EditionPill` / `V15Layout` 视觉对齐

### M21 #5 · 三中心 + 顶栏统一 shadcn 风（529bf2a）
- 用 `stitch-shadcn-ui` skill 把顶栏统一到 shadcn 设计语言
- Layout 抽统一组件

### M21 #6 · 亮色主题切换 + 咨询中心文件上传（08f9fe4）
- `lib/themes.ts` applyTheme 支持 dark / light 切换
- `index.html` 首帧 `color-scheme: dark` 防白屏闪烁，运行时按需切换
- `ConsultUploader.tsx` 咨询中心新增文件上传入口（前置 W2 体验）

### M21 #7 · Excel/CSV/doc 解析 + KAP backend 重新装为 editable（133b0c4）
- knowledge.py `_parse_upload_file` 加 .xlsx / .xls / .csv / .doc 解析（openpyxl / xlrd / python-docx 兜底）
- pyproject.toml 加 optional deps `[parsers]`
- backend 重新 `pip install -e .` 修复 editable 失效

### M21 #8 · 三中心部署资源清单（Word + zip）（e903418）
- `docs/deployment/三中心部署资源清单.md` v1.0
  - 方案 A 三中心分别部署（48 vCPU / 92 GB / 1 TB SSD）
  - 方案 B 一体打包部署（21 vCPU / 41 GB / 1 TB SSD）
  - 14 routers 按中心分配清单 + 6 PG 持久化开关 + nginx 网关路由分发
  - 5 共用部署前置清单 + 上线签字栏
- `scripts/md_to_docx.py` python-docx 直接渲染（无 pandoc 依赖）
- 打包：`E:\Obsidian\知识PPL\raw\KAP-三中心部署资源清单-20260506.zip`（61 KB）

### M21 #9 · 概览页 + 咨询中心行业前置（登录默认进总览）（dbb996e）
- 登录后默认路由 `/overview`，不再直接落 `/consult`
- ConsultHome 进入时强制选行业（manufacturing / energy），避免无行业上下文跑 W1
- `ModeContext` 全局保留行业选择

### M21 #10 · ConsultHome 切换行业崩溃（React hooks 顺序）（7f73733）
- 修复 ConsultHome 在 industry change 时 hooks 顺序变化导致的 React invariant 错误
- 把条件渲染的 hook 抽到组件顶层

### M21 #11 · backend 配置加载 + httpx 超时 + .pptx 解析 + raw_store PK 迁移 收尾（f9d835d）
- `_apply_llm_settings_json`：UI 保存的 LLM 配置（gateway / key / model）重启后立即生效
- httpx 超时 60→120s + `trust_env=False`：避免被 Windows 代理引到本地 V2Ray 挂等
- `raw_store.py` 老 schema PK 自动迁移（doc_id → (doc_id, project_id)）
- knowledge.py 加 .pptx 解析（python-pptx）+ 二进制魔数守卫
- run_dev.py dev 默认开 `KAP_ALLOW_MEMORY_FALLBACK=true`
- **secret 同步收口**：`backend/configs/llm_settings.json` 含真实 API Key 违反 KAP 全局 MUST NOT 1，`git rm --cached` 隔离（git 历史未泄露），新建 `.example` 模板，`.gitignore` 加忽略

---

## Commits 时间线

| Commit    | 内容                                              | 文件                |
|:---|:---|:---:|
| `5d8518f` | #1 三块松耦合拆分（三中心独立 FastAPI app）              | +backend 三入口 / 三 Dockerfile / clients.py |
| `92fc0bf` | #2 前端三中心 tab                                  | CenterShell + 三 Home |
| `c2a77ff` | #3 咨询中心可用 + UI 重做 + 三块边界重划                | ConsultHome / 边界 |
| `b146da6` | #4 三中心统一设计（claude-frontend-skills）            | distinctive.css |
| `529bf2a` | #5 三中心 + 顶栏统一 shadcn 风（stitch-skills）        | EditionPill / V15Layout |
| `08f9fe4` | #6 亮色主题切换 + 咨询中心文件上传                      | themes.ts / ConsultUploader |
| `133b0c4` | #7 Excel/CSV/doc 解析 + KAP backend editable 修复    | knowledge.py / pyproject.toml |
| `e903418` | #8 三中心部署资源清单（Word + zip）                    | docs/deployment/ |
| `dbb996e` | #9 概览页 + 咨询中心行业前置                          | OverviewHome / ModeContext |
| `7f73733` | #10 ConsultHome 切换行业崩溃（React hooks 顺序）        | ConsultHome hooks |
| `f9d835d` | #11 backend 配置 / 超时 / .pptx / PK 迁移 收尾         | 6 file + .gitignore + secret 隔离 |

---

## 测试基线

`1048/1050 unit ✓` 后端 + `58 frontend tests passed` + 12 live_llm（默认 deselect）。

M21 主要是 UI 重做 + 部署文档 + 配置收口，**未增 unit tests**；M22 #1-#7 将补齐多模态相关测试。

## M21 已交付

### 后端
- ✓ 三中心独立 FastAPI app（architect:8011 / storage:8012 / portal:8013）
- ✓ 一体化打包模式（kap-api:8001）保留
- ✓ 服务间 HTTP SDK（packages/integration/clients.py）
- ✓ 三 Dockerfile 独立 + 一体化 Dockerfile 兼容
- ✓ knowledge.py 解析器扩展：Excel / CSV / .doc / .pptx + 二进制守卫
- ✓ 配置加载链 UI ↔ JSON ↔ env 三层同步
- ✓ httpx 超时与 Windows 代理隔离
- ✓ raw_store 老 schema PK 自动迁移
- ✓ secret 隔离与模板化

### 前端
- ✓ 三中心 tab 框架（CenterShell + 路由分流）
- ✓ Nordic Minimalism + shadcn 统一设计语言
- ✓ 亮色 / 暗色主题切换（首帧不闪）
- ✓ 概览页 OverviewHome（登录默认）
- ✓ 咨询中心行业前置 + 文件上传

### 部署
- ✓ 三中心部署资源清单 v1.0（方案 A 三中心 / 方案 B 一体 + 资源汇总 + 上线签字栏）
- ✓ Word + Markdown 双格式打包（`KAP-三中心部署资源清单-20260506.zip`）

## M21 未做（M22+ 候选）

- ⬜ 前端 dist 重新构建（dist 时间戳停在 May 1，落后 M21 所有 commit）
- ⬜ M22 多模态解析增强（A 主线：MinerU / 表格 / 公式 / context-aware / ISS bypass）
- ⬜ M22 知识中心补强（B 补强：relation_extractor / entity_resolver / ingest_metrics / 增量重抽）
- ⬜ M22 后置：跨模态实体进 KG / VLM 图像处理器 / 召回三路融合权重动态学习
- ⬜ 部署期 候选：首批客户 PoC 上线 / 真实 ISS-Job 联调 / 独立物理 Neo4j 实例

---

## 设计依据回顾

- **三中心边界**：决策书 §3.1 三层视图自然延伸；不是技术驱动，是 M20 收尾后**业务功能聚类自然显形**
- **UI 重做**：依从 [feedback: 图谱 obsidian 风格 + 动态交互](../../memory/feedback_graph_obsidian_style.md) + Nordic Minimalism 美学；调用 `frontend-design` + `stitch-shadcn-ui` skill 复用现有设计资产
- **配置加载链**：解决私有化部署运维"UI 改了 Key 重启失效"痛点；JSON 优先级高于 env 是因为运维主要通过 UI 操作（决策书 §10.6）
- **httpx 超时**：踩过 librarian 在 60s timeout 撞死的真坑（M20 之前 dev 偶发，M21 测试时复现）

> 详见 [docs/deployment/三中心部署资源清单.md](../deployment/三中心部署资源清单.md) v1.0
