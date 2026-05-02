---
title: Neo4j 独立物理实例部署指南 (M19 #5 + 决策书 §5.3)
version: v1
date: 2026-05-02
tags: [kap, deployment, neo4j]
---

# Neo4j 独立物理实例部署指南

> 决策书 §5.3：知识图谱建议在**独立物理 / VM** 上跑，与 kap-api 解耦。
> M0-M18 默认使用 docker-compose 内嵌 Neo4j；M19 起支持物理实例切换。
>
> M4 lite "影子库"用 alias 隔离，与本指南无关，部署期可继续保留。

## 何时选择独立物理实例？

| 场景 | 选择 |
|:---|:---|
| PoC / Demo / 开发 | docker-compose 内嵌（infra/docker-compose.dev.yml） |
| 客户数据量 < 10 GB / QPS < 50 | docker-compose 生产版（infra/docker-compose.prod.yml） |
| 客户数据量 > 10 GB 或 QPS > 50 | **独立物理 / VM**（本指南） |
| 客户已有 Neo4j 集群 | 直接对接客户实例（仅配 NEO4J_URI） |

## 部署步骤

### 1. 物理 / VM 规格

- CPU：≥ 8 vCPU（图遍历 CPU 密集）
- 内存：≥ 32 GB（heap 8G + pagecache 16G + OS 8G）
- 磁盘：≥ 500 GB SSD（NVMe 优先，图谱随机读多）
- 网络：与 kap-api 同 LAN，延迟 ≤ 5ms

### 2. 安装 Neo4j Server 5.x

```bash
# Ubuntu / Debian
wget -O - https://debian.neo4j.com/neotechnology.gpg.key | sudo apt-key add -
echo 'deb https://debian.neo4j.com stable 5' | sudo tee /etc/apt/sources.list.d/neo4j.list
sudo apt update && sudo apt install neo4j=1:5.20.0
```

### 3. 关键配置（`/etc/neo4j/neo4j.conf`）

```properties
# 内存（按机器规格调整）
server.memory.heap.initial_size=8G
server.memory.heap.max_size=8G
server.memory.pagecache.size=16G

# 网络（仅监听内网 LAN 网卡，不暴露公网）
server.default_listen_address=10.0.0.10           # 改为 KAP 内网 IP
server.bolt.listen_address=:7687
server.http.listen_address=:7474

# 鉴权
dbms.security.auth_enabled=true

# 日志
server.directories.logs=/var/log/neo4j
server.logs.query.enabled=INFO

# APOC 插件（M0+ 用 apoc.periodic）
dbms.security.procedures.unrestricted=apoc.*
dbms.security.procedures.allowlist=apoc.*
```

下载 APOC：

```bash
sudo wget -O /var/lib/neo4j/plugins/apoc.jar \
  https://github.com/neo4j/apoc/releases/download/5.20.0/apoc-5.20.0-core.jar
```

### 4. 启动 + 改密码

```bash
sudo systemctl enable --now neo4j
# 首次登录改密
sudo cypher-shell -u neo4j -p neo4j
> ALTER USER neo4j SET PASSWORD '<新密码>'
> :exit
```

### 5. 配置 KAP 切换到物理实例

修改 `.env.prod`（参考 `docs/deployment/checklist.md` §1）：

```ini
NEO4J_URI=bolt://10.0.0.10:7687    # 物理实例内网地址
NEO4J_USER=neo4j
NEO4J_PASSWORD=<上一步密码>
```

把 docker-compose.prod.yml 中的 `kap-neo4j` service **删除或注释**，让 kap-api 直连物理实例：

```yaml
services:
  kap-api:
    # ... 其他配置不变
    depends_on:
      - kap-postgres
      # - kap-neo4j   # 删除这行
      - kap-milvus
      - kap-redis
```

### 6. 验证连接

```bash
docker compose -f infra/docker-compose.prod.yml exec kap-api \
  python -c "
from packages.storage.graph_store import GraphStore
import asyncio
async def t():
    g = GraphStore(use_memory=False)
    await g.initialize()
    await g.refresh_counts()
    print(f'nodes={g.node_count} edges={g.edge_count}')
asyncio.run(t())
"
```

期望输出 `nodes=N edges=M`（即使空也算成功）。

## 备份与恢复

### 每日全量备份（cron）

```bash
# /etc/cron.daily/neo4j-backup
#!/bin/bash
DATE=$(date +%Y%m%d)
sudo systemctl stop neo4j
sudo neo4j-admin database dump --to-path=/backup/neo4j-$DATE.dump neo4j
sudo systemctl start neo4j
mc cp /backup/neo4j-$DATE.dump kap-backup/neo4j/
find /backup -name "neo4j-*.dump" -mtime +30 -delete
```

### 恢复

```bash
sudo systemctl stop neo4j
sudo neo4j-admin database load --from-path=/backup/neo4j-20260501.dump --overwrite-destination=true neo4j
sudo systemctl start neo4j
```

## 影子库（M4 lite）配合策略

M4 lite 用 `ontology_version` 节点标签做逻辑隔离。物理化后**不变**：

- 主图谱写入 `:Entity {ontology_version: "main"}`
- 影子库写入 `:Entity {ontology_version: "shadow_v2"}`
- 切换走 `swap_shadow_to_main` 改 label

如果客户偏好物理隔离，可参考决策书 §5.3 起 2 个 Neo4j database：
1. 安装 Neo4j Enterprise（社区版只支持单 DB）
2. `CREATE DATABASE shadow`
3. M4 ShadowGraphStore 改连 `bolt://...:7687/shadow`

> M4 lite 当前未支持多 DB；若客户强需求，M20+ 加这个能力。

## 性能调优清单

- [ ] `pagecache.size` ≥ 图谱大小 × 1.2（避免冷启动 IO 风暴）
- [ ] 关键 label 都建 INDEX：`CREATE INDEX entity_type_idx FOR (n:Entity) ON (n.entity_type)`
- [ ] 启用 query cache：`db.query.cache.size=10000`
- [ ] APOC `apoc.periodic.iterate` 用于大批量更新（M4 重抽）
- [ ] 监控 GC：长时间 Full GC > 200ms 需扩 heap

## 常见问题

| 问题 | 检查 |
|:---|:---|
| KAP 启动报 `bolt connection refused` | LAN / 防火墙 / Neo4j 监听地址 |
| 节点数突然为 0 | 是否误连了空 `shadow` DB |
| 写入超时 > 30s | pagecache 不够导致频繁刷盘 |
| Cypher 查询慢 | `EXPLAIN` 看是否走索引；缺索引则补 |
