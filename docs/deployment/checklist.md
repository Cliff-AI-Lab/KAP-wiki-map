---
title: KAP 部署 Checklist (M19 #5)
version: v1
date: 2026-05-02
tags: [kap, deployment, ops]
---

# KAP 部署 Checklist

> 私有化部署收口（M19 #5）。开发已结束，本清单覆盖**真实环境上线**前的验证项。
> 与 `docker-compose.prod.yml` + `migrate_partitioned.py` + `iss-job-config.md` 配套使用。

## 0. 前置条件

- [ ] 客户机房物理 / 虚拟机就绪：≥ 16 vCPU / 32 GB RAM / 500 GB SSD
- [ ] 操作系统：CentOS 7+ / Ubuntu 22.04 / RHEL 8+
- [ ] Docker 24+ 与 Docker Compose v2 安装并通过 `docker info` 验证
- [ ] 域名解析 + TLS 证书签发到位（默认 nginx 监听 :443 走 server.crt）
- [ ] 防火墙仅放行 :80 / :443 / SSH（PG/Neo4j/Milvus 等不暴露公网）

## 1. 环境变量与密钥

将下述键值写入 `.env.prod`（**不入仓**，权限 600）：

| Key | 用途 |
|:---|:---|
| `POSTGRES_PASSWORD` | PG 密码（≥ 32 字符随机） |
| `NEO4J_PASSWORD` | Neo4j 密码（≥ 32 字符随机） |
| `REDIS_PASSWORD` | Redis 密码 |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | MinIO 认证 |
| `IRUIDONG_API_KEY` | 睿动 LLM 网关 Key（生产 Key，不能用 sandbox） |
| `IRUIDONG_BASE_URL` | 默认 `https://iruidong.com/v1`；私有化部署填客户内网地址 |
| `JWT_SECRET` | API JWT 签名密钥（≥ 64 字符） |
| `KAP_ENV` | 固定为 `prod` |

- [ ] `.env.prod` 已写入并 `chmod 600`
- [ ] 模型名 / API Key / SSO AES Key 等**未硬编码**到任何源代码或镜像层
  - 跑 `git grep -E "sk-|cr_|AES_KEY|hardcoded"` 确认零命中
- [ ] 已确认睿动 Key 调用 `/v1/models` 能列出至少 1 个 chat 模型

## 2. 启动 Compose

```bash
cd /opt/kap
docker compose -f infra/docker-compose.prod.yml --env-file .env.prod up -d
```

- [ ] `docker compose ps` 所有服务 `running` 且 `healthy`
- [ ] `curl -k https://<host>/health` 返回 `{"status":"ok"}`
- [ ] PG / Neo4j / Milvus 初始化均 `degraded → ok` 后稳定（≥ 60s 观察）

## 3. 数据库初始化

启动时主程序的 `lifespan` 会自动建表，但分区迁移需手动触发：

### 3.1 决策日志 / 查询日志时序分区（M14 + M19 #5）

**首次部署**（表是空表，可直接 swap）：

```bash
# 先停 KAP 写入（让 PG 表无新数据），建议短期维护窗口
docker compose -f infra/docker-compose.prod.yml stop kap-api

# 跑迁移（DDL 序列：rename → create partition table → 创子分区 → INSERT INTO new SELECT FROM legacy）
docker compose -f infra/docker-compose.prod.yml exec kap-postgres psql -U kap -d kap \
  -c "$(python -m scripts-backend.migrate_partitioned --dry-run 2>&1 | grep -E '^[A-Z]')"

# 或直接走脚本（需要在 kap-api 容器内）
docker compose -f infra/docker-compose.prod.yml run --rm kap-api \
  python -m scripts-backend.migrate_partitioned --apply

# 启动
docker compose -f infra/docker-compose.prod.yml start kap-api
```

- [ ] `decision_events` / `query_events` 分区表已存在
  - `\d+ decision_events` 显示 PARTITIONED TABLE + 子分区列表
- [ ] 周度 cron 已配置 `--ensure-current` 自动建未来分区

### 3.2 Wiki 质量评分 PG（M19 #1）

由 `KAP_WIKI_QUALITY_PG=1` 在 lifespan 中触发；表名 `wiki_quality_scores`。

- [ ] 首次 `score_wiki_page` 调用后查 `wiki_quality_scores` 至少有 1 行
- [ ] `/api/v1/observability/wiki-quality/trend` 返回非空

## 4. 真实 LLM 网关连通

- [ ] backend 容器内执行 `curl -H "Authorization: Bearer $IRUIDONG_API_KEY" $IRUIDONG_BASE_URL/models` 返回 200
- [ ] 调用 `POST /api/v1/architect/recognize_industry` 上传几条样本，返回 `industry_code`（不是空）
- [ ] 跑 12 个 live_llm 测试（生产环境跳过；预生产或 sandbox 跑）：
  ```bash
  pytest -m live_llm tests/integration/
  ```

## 5. ISS 集成（如适用）

详见 `docs/integration/iss-job-config.md`。

- [ ] ISS 平台配置 KAP 服务地址 + JWT 公钥
- [ ] ISS-Job Quartz 已注册下列 cron 推荐任务（GET `/iss-job/cron-recommendations`）：
  - `kap_recall_eval_daily` — 召回评估（日度）
  - `kap_observation_sweep` — 观察期 sweep（小时度）
  - `auto_tune_prompt_*` — 自学习 auto-tune（周度，仅 decisions_total ≥ 50 时推荐）
- [ ] ISS-Job 调度器拉到的 cron 表达式 + endpoint 在 KAP 端能正常响应（200 + JSON）

## 6. Neo4j 物理实例（决策书 §5.3）

详见 `docs/deployment/neo4j-physical.md`。

- [ ] Neo4j Server 模式部署在独立物理 / VM（与 kap-api 同 LAN，延迟 < 5ms）
- [ ] 内存配置：heap 4G / pagecache ≥ 总图谱大小 × 1.2
- [ ] 备份：每日 `neo4j-admin database dump` 到 MinIO bucket `kap-backup`
- [ ] 影子库 alias 隔离已验证（M4 #1：写入主版本不污染影子）

## 7. 前端访问

- [ ] `https://<host>/` 加载首页正常
- [ ] `https://<host>/v15/manage/observability` 仪表盘所有 6 卡片渲染（M11+ ✓）
- [ ] `https://<host>/v15/manage/observability/wiki-quality` 6 维雷达 + 趋势线（M18+M19）
- [ ] `https://<host>/v15/manage/observability/prompts` 版本管理 + diff 三 tab（M18+M19）
- [ ] LanguageSwitcher 中 / EN 切换可用（M16+M17）

## 8. 监控告警

- [ ] OpenTelemetry collector 接 KAP（决策书 §13）
- [ ] Skywalking 看到 `bookworm-agent` service trace
- [ ] Grafana：以下面板已部署（基于 PG `wiki_quality_scores` / `query_events` 等）
  - Wiki 质量趋势（avg_overall + alerting count）
  - useful_rate 趋势（M15）
  - 召回率 / F1 趋势（M9）
  - SME 决策吞吐（M6）

## 9. 灾备 + 回滚

- [ ] PG 每日备份到独立存储（不与 PG 主机同盘）
- [ ] Neo4j `dump` 每日 + 影子库 promote 前快照（M5 #2）
- [ ] 镜像回滚：保留前 3 个 `kap/backend:vX` tag；可一键 `docker compose pull && up -d`

## 10. 安全

- [ ] 生产 Key/secrets 走 `.env.prod`，不出现在镜像层（`docker history kap/backend` 验证）
- [ ] `git grep` 验证零硬编码 Key / 模型名 / 内网 IP（睿动开发约束 MUST NOT）
- [ ] CORS allow-list 收敛到客户域名（不开 `*`）
- [ ] /health 与 /docs 仅内网可访问（外网由 nginx 屏蔽）

---

## 上线签字

| 阶段 | 负责人 | 验证人 | 签字 |
|:---|:---|:---|:---|
| 环境准备 |  |  |  |
| 数据库迁移 |  |  |  |
| LLM 网关连通 |  |  |  |
| ISS 集成 |  |  |  |
| 监控告警 |  |  |  |
| 灾备 + 回滚 |  |  |  |
| 安全审计 |  |  |  |
| **整体上线** | | | |
