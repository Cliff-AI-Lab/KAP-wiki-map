# KAP · Knowledge Agent Platform

> 全行业的、私有化部署的、AI-native 的企业知识治理全流程智能体平台。
> 首批锁定**制造**与**能源**，向金融、政企、医疗、运营商可扩展。

```
块① 知识咨询智能体    │  块② 知识库 + 知识图谱    │  块③ 渐进式消费门户
AI 对话式建体系       │  6 工位 + 4×6 审核矩阵    │  Wiki / RAG / 图谱并行
DG · 业务负责人       │  DG · SME · SEC · AIOps   │  Reader（终端用户）
```

---

## 文档导览

| 文档 | 内容 | 版本 |
|---|---|---|
| [docs/01-技术决策书.md](./docs/01-技术决策书.md) | 21 条已锁定架构决策 + 整合架构 + 复用清单 | v1.1 |
| [docs/02-产品需求PRD.md](./docs/02-产品需求PRD.md) | 三块功能需求 + MVP + 路线图（M0 KAP-Lite ~ M5 GA） | v1.2 |
| [docs/M0-tech-debt.md](./docs/M0-tech-debt.md) | M0 阶段技术债务地图（Opus 4.7 产出） | v1.0 |
| [docs/M0-tech-debt-async-plan.md](./docs/M0-tech-debt-async-plan.md) | LLM 全链路异步化迁移地图 | v1.0 |
| [docs/_refs-index.md](./docs/_refs-index.md) | 上游参考项目索引（Wiki-map V15 + ISS 知识库）| — |
| [test-samples/README.md](./test-samples/README.md) | **测试样例集**（4 行业 / 48 文档）总入口 | — |
| [design/index.html](./design/index.html) | UI 原型（Plan A · 工程蓝图美学） | v1.0 |
| [scripts/README.md](./scripts/README.md) | kap-delegate 委派工具用法（Opus 4.7 / Sonnet 4.6 / Haiku 4.5） | — |
| [CLAUDE.md](./CLAUDE.md) | Claude 会话项目内存（自动加载） | — |

## 测试样例集

按行业组织的 KAP 自有可执行测试集（Wiki-map V15 真实场景，已修复 GBK 乱码）。

| 行业 | 文件数 | 入口 README | 用途 |
|---|---|---|---|
| 能源（电力 / 油气 / 化工）| 33 | [test-samples/energy/README.md](./test-samples/energy/README.md) | M0 主测试基线（决策书 §7.2）|
| 制造（ISO9001 / 注塑 / 装备）| 5 | [test-samples/manufacturing/README.md](./test-samples/manufacturing/README.md) | M1 制造模板验证（决策书 §7.1）|
| 金融（信贷 / 反洗钱 / 理财）| 5 | [test-samples/finance/README.md](./test-samples/finance/README.md) | GA 后第二批扩展验证 |
| IT（微服务 / 敏捷 / DBA）| 5 | [test-samples/it/README.md](./test-samples/it/README.md) | `_default` 通用模板 + dogfood |

→ [测试样例总入口与场景索引](./test-samples/README.md) — 含 W1-W6 工位测试场景推荐数据集。

---

## 项目结构

```
KAP知识智能体平台/
├── backend/            Python FastAPI · 基于 Wiki-map V15 演进
│   ├── api/            REST 路由（projects/knowledge/qa/wiki/governance/...）
│   ├── packages/       核心逻辑（distillation/governance/retrieval/storage/graph/...）
│   ├── configs/        LLM/嵌入/重排配置
│   ├── scripts/        启动 / 数据灌入 / 测试
│   ├── tests/
│   └── pyproject.toml
├── frontend/           React 19 + Vite + TS + Tailwind · 基于 V15 演进
│   ├── src/            页面 / 组件 / contexts
│   ├── public/
│   └── package.json
├── infra/              基建配置（待 M0 完善）
│   └── docker-compose.dev.yml
├── docs/               架构决策、PRD、UI 规范、API、数据模型
├── design/             UI 原型（视觉锚点）
├── scripts/            kap-delegate 等工具
├── _refs/              参考项目（只读）：Wiki-map V15、ISS 知识库
├── memory/             Claude 会话间记忆
├── CLAUDE.md           Claude 项目内存
├── README.md           本文件
└── .gitignore
```

---

## 快速启动（M0 KAP-Lite）

> 详细部署见 `docs/06-部署运维.md`（待补）。

### 前置依赖

- Python 3.11+
- Node.js 18+
- Docker + Docker Compose
- 睿动 / CRS API Key

### 一键起服务

```bash
# 1. 配置环境
cp backend/.env.example backend/.env
# 编辑 backend/.env 填入 IRUIDONG_API_KEY 或 ANTHROPIC_AUTH_TOKEN

# 2. 起基建（PG / Milvus / Redis / MinIO / Neo4j）
docker-compose -f infra/docker-compose.dev.yml up -d

# 3. 起后端
cd backend && pip install -e . && python -m uvicorn api.main:app --port 8001 --reload

# 4. 起前端
cd frontend && npm install && npm run dev
```

入口：

- 消费门户：`http://localhost:3000/portal`
- 治理工作台：`http://localhost:3000/workbench`
- 知识咨询智能体：`http://localhost:3000/agent/architect`（M2 上线）

---

## 团队工具 · kap-delegate

把繁重代码工作委派给 Claude（Opus 4.7 / Sonnet 4.6 / Haiku 4.5），保留 git 安全壳与人工审核：

```bash
# 规划任务（Opus 4.7）
./scripts/kap-delegate.sh --task-type plan --mode diagnosis \
    --files "docs/01-技术决策书.md" \
    "找出技术决策书中的内部矛盾"

# 开发任务（Sonnet 4.6）
./scripts/kap-delegate.sh --files "backend/packages/governance/agents/*.py" \
    "把 auditor.py 改为 AsyncClient"

# 测试循环修复
./scripts/kap-delegate.sh --mode quick \
    --test-cmd "pytest tests/test_router.py -x" --max-rounds 5 \
    "修复路由测试"
```

详见 `scripts/README.md`。

---

## 路线图（推荐方案 B · 渐进交付）

| 里程碑 | 累计 | 交付物 |
|---|---|---|
| **M0 KAP-Lite** | 4 周 | Wiki-map V15 + ISS 接入 + 睿动；单角色；块②③ 主流程；**可演示给客户** |
| **M1 企业级 v1** | 8 周 | 4×6 矩阵审核台 + 敏感脱敏 + 制造行业模板 + ISS RBAC |
| **M2 块① 上线** | 12 周 | 知识咨询智能体（对话式建体系全流程） |
| **M3 高级治理** | 16 周 | 双层本体 + 全量重抽 + LLM-Critic 6 维 |
| **M4 GA** | 20 周 | 专家共识 + 行业模板管理 + UI 重设计 |
| **M5 PoC + 调优** | 24 周 | 1 制造 + 1 能源客户 PoC 验证 |

---

## License & 行业标准锚定

- ISO 30401:2018 知识管理体系
- DAMA-DMBOK V2（第 9 章 文档与内容管理）
- DCMM GB/T 36073（数据管理能力成熟度）
- ISA-95 / IEC 62264（制造执行体系）
- IATF 16949 / ISO 9001（质量体系）
- ISO 55000（资产管理）
- IEC 61850 / KKS（电力/能源设备标识）
- ISO 14224（设备可靠性）
