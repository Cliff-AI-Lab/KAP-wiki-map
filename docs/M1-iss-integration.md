# M1 · ISS 集成部署指南

> 版本：v1.0（M1 批 1+2-4 完工）· 日期：2026-04-29
> 适用对象：私有化部署运维、ISS 系统管理员、KAP 部署工程师

KAP（Python FastAPI）通过协议层接入 ISS（Java Spring Cloud），**零侵入 ISS 代码**。
本文档说明部署 KAP 时如何对接客户已有的 ISS 实例。

---

## 1. 三种认证模式选其一

KAP 通过 `KAP_AUTH_MODE` 环境变量决定如何识别用户身份：

| 模式               | 适用场景                                  | 配置要求                                |
|:---|:---|:---|
| `api_key` (默认)   | 开发 / 单机 demo / 不接入 ISS 的客户       | `API_KEYS=key:user_id:role`             |
| `jwt`              | KAP 独立部署，自己验签 ISS Token           | `ISS_JWT_SECRET` + `ISS_REDIS_URL`      |
| `gateway_header`   | KAP 部署在 ISS-Gateway 后面（推荐）        | 网关注入 `X-User-*` header              |

`KAP_ENV=sandbox / prod` 时，强制非 `api_key`（自动回退到 `gateway_header`）。

---

## 2. JWT 模式部署清单

### 2.1 共享 ISS-Auth JWT 密钥

ISS-Auth 在 Nacos 配置 `application-{profile}.yml` 中定义 JWT secret（HS512）。
KAP 复用同一密钥：

```yaml
# Nacos 共享配置（ISS 侧已存在）
token:
  signKey: <hex-or-base64-secret>
```

KAP 启动时通过环境变量注入：

```bash
export ISS_JWT_SECRET="<同上 signKey>"
```

**绝不**写入 KAP 源码或 Dockerfile（决策书 §8.3 / 全局规约 MUST NOT-2）。

### 2.2 共享 ISS Redis

ISS-Auth 把 LoginUser 存在 Redis `login_tokens:{user_key}`。
KAP 通过独立连接池读取（与 KAP 自己的 Redis 解耦，私有化场景可能不同实例）：

```bash
export ISS_REDIS_URL="redis://iss-redis:6379/0"
export ISS_TOKEN_KEY_PREFIX="login_tokens:"  # 与 ISS CacheConstants.LOGIN_TOKEN_KEY 一致
```

### 2.3 验证

```bash
# 1. ISS-Auth 登录拿 token
TOKEN=$(curl -s -X POST http://iss-auth:9204/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | jq -r '.data.access_token')

# 2. 带 token 调 KAP
curl http://kap-api:8000/api/v1/qa/ask \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"question":"什么是设备点检？"}'
```

KAP 日志应看到 `auth.iss_session` 与 `auth.iss_jwt` 模块输出，UserContext.source = `jwt`。

---

## 3. Gateway Header 模式部署清单

ISS-Gateway 已经验签好 JWT 后，把用户身份注入下游服务的 header（沿用 ISS HeaderInterceptor 约定）：

| Header              | 类型       | 说明                                       |
|:---|:---|:---|
| `X-User-Id`         | int (必填) | 用户 ID                                     |
| `X-User-Name`       | str        | 用户名 / 昵称                               |
| `X-User-Roles`      | csv        | 角色码列表，如 `DG,READER`                  |
| `X-User-Perms`      | csv        | 权限码列表，如 `system:user:list`           |
| `X-Dept-Id`         | int        | 部门 ID（与 ISS sys_user.dept_id 对齐）     |
| `X-Data-Scope`      | int        | 1-5 数据权限级别（默认 5=SELF）             |
| `X-Access-Level`    | str        | 密级 PUBLIC/INTERNAL/CONFIDENTIAL/SECRET    |

**网关侧改动**（一次性配置）：
- ISS-Gateway 路由到 KAP 的过滤器中，把 `SecurityContextHolder` 里的字段写到 header
- 参考 ISS `iss-gateway` 项目的 `AuthFilter` 实现

---

## 4. KAP 5 角色注册（在 ISS 后台配，不动数据库）

KAP 引入 5 角色（决策书 §1.5）：

| 角色码  | 名称        | 推荐 dataScope    | 推荐密级访问           |
|:---|:---|:---|:---|
| `DG`     | 数据治理员 | 3 = 本部门         | INTERNAL              |
| `SME`    | 业务专家   | 3 = 本部门         | CONFIDENTIAL          |
| `SEC`    | 安全审计员 | 1 = 全部           | TOP_SECRET            |
| `AIOps`  | AI 运营员  | 3 = 本部门         | INTERNAL              |
| `READER` | 终端用户   | 5 = 仅本人         | INTERNAL              |

**操作步骤**（在 ISS 管理后台执行，不需要写 SQL）：
1. 登录 ISS 后台 → 系统管理 → 角色管理 → 新增
2. 角色名称 = 上表"名称"，权限字符 = 角色码（如 `DG`）
3. 数据范围 = 上表"推荐 dataScope"
4. 菜单权限：勾选 KAP 相关菜单（M2 块① 上线后扩展）

KAP 侧 `packages/common/roles.py` 已经识别这 5 个角色码 + V15 的 `admin`/`editor` 别名。

---

## 5. DataScope 5 级语义（KAP Python 等价实现）

ISS Java 端 `DataScopeAspect` 用 MyBatis SQL 拼接，KAP 用 `packages/auth/data_scope.py` 函数式实现：

| ISS 级别 | KAP 实现位置                                    |
|:---:|:---|
| 1 ALL              | `build_milvus_expr` 返回空串（不过滤）          |
| 2 CUSTOM           | `dept_id IN user.custom_dept_ids`               |
| 3 DEPT             | `dept_id == user.dept_id`                       |
| 4 DEPT_AND_CHILD   | 调用 ISS `/system/dept/list?parentId=` 拉子树   |
| 5 SELF             | `created_by == user.user_id`                    |

**当前限制（M1 KAP-Lite）**：
- DataScope 在 retriever 后过滤层生效，**未注入 Milvus expr**（避免改 schema）
- 文档元数据缺 `dept_id` / `created_by` 时透明放行（兼容 M0 demo 数据）
- W4 工位写入侧补全这两个字段是后续工作（M1 矩阵审核台）

---

## 6. 故障排查

| 现象                                        | 排查                                      |
|:---|:---|
| `ISS_JWT_SECRET 未配置` 启动失败            | 检查环境变量是否在 K8s/Docker 中正确传入     |
| 401 "JWT 验签失败"                          | 确认 KAP/ISS 两侧 secret 一致；时钟差 ≤ 60s |
| 401 "ISS 会话失效"                          | Token 已过期或被登出；重新登录              |
| 403 调 RequireRole(SME) endpoint            | 用户在 ISS 没有 SME 角色码                  |
| DataScope DEPT_AND_CHILD 子部门没看到       | 检查 `ISS_SYSTEM_BASE_URL` + 部门表 ancestors 字段 |

---

## 7. 监控指标（M2+ 接入 Skywalking 后展开）

- `kap.auth.jwt.decode.failure` — JWT 验签失败次数
- `kap.auth.iss_redis.miss` — Redis LoginUser 不存在次数
- `kap.auth.dept_descendants.fallback` — ISS-System 不可达，DataScope 降级为 [self]
- `kap.auth.data_scope.filter.hit` — 后过滤过滤掉的文档数

---

> 文档版本：v1.0
> 配套实施：commit `4a4206a` (批 1) + `<TBD>` (批 2-4)
> 决策依据：技术决策书 §8.1 §9.1 / PRD §6.1 §10.4
