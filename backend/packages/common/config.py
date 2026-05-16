"""全局配置管理，通过环境变量或 .env 文件加载。

LLM 部分还会叠加 backend/configs/llm_settings.json — 由设置 UI 写入，
让前端保存的模型/Key/网关地址在重启后立即生效。
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# UI 保存的 LLM 配置文件（与 api/routers/settings.py 同源）
_LLM_SETTINGS_JSON = Path(__file__).resolve().parents[2] / "configs" / "llm_settings.json"

# 睿动 (iruidong) 是 OpenAI 兼容网关，LLM 客户端按 openai 分支调用
_LLM_PROVIDER_ALIAS = {"ruidong": "openai"}

# M0 三环境枚举（决策书 §10.3 + 用户全局 ruidong-agent-dev 规约）
KAP_ENV_DEV = "dev"
KAP_ENV_SANDBOX = "sandbox"
KAP_ENV_PROD = "prod"
KAP_ENVIRONMENTS = (KAP_ENV_DEV, KAP_ENV_SANDBOX, KAP_ENV_PROD)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 环境标识（必填，影响 mock fallback / SSL / 审计严格度）---
    kap_env: str = Field(
        default=KAP_ENV_DEV,
        description="部署环境：dev / sandbox / prod。sandbox/prod 触发严格安全策略",
    )

    # --- LLM (睿动 iRuidong 网关, OpenAI 兼容) ---
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    # 沙箱部署: 如设置了 SANDBOX_API_BASE，运行时覆盖 openai_base_url (睿动规范 MUST-2)
    sandbox_api_base: str = ""
    anthropic_api_key: str = ""
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"

    # --- LLM Async / 安全 / 行为门控（M0-tech-debt 坑 1 + D + F）---
    llm_verify_ssl: bool = Field(
        default=True,
        description="HTTPS 证书校验（坑 D）。dev 可设 False；sandbox/prod 由 model_post_init 强制 True",
    )
    llm_http_timeout: float = Field(
        default=120.0,
        description=(
            "LLM HTTP 请求超时（秒）。睿动 / 大模型推理常 30-60s, 4 并发还会排队, "
            "60s 偏紧, 默认 120s; 原值 60 已撞过 timeout 导致 librarian 全失败"
        ),
    )
    llm_max_concurrency: int = Field(
        default=4,
        description="LLM 异步并发上限（asyncio.Semaphore），async 化后取代 pipeline_max_workers",
    )
    allow_mock_llm: bool = Field(
        default=False,
        description=(
            "是否允许 mock LLM fallback（坑 F）。"
            "False 时 mock provider/无 Key/异常都直接抛 LLMCallError，"
            "禁止静默回落 mock 污染数据。dev 可设 True；sandbox/prod 强制 False"
        ),
    )

    def model_post_init(self, __context: object) -> None:
        """三环境强制安全策略 + 睿动规范 MUST-2 沙箱 URL 覆盖。

        M0-tech-debt 坑 D / 坑 F 接入：sandbox / prod 必须严格 SSL 校验、
        必须禁用 mock fallback，无视用户输入。dev 保留宽松配置便于本地调试。
        """
        # 0. 叠加 UI 保存的 llm_settings.json (前端"系统设置"页改的 Key/Provider/Model 在此生效)
        self._apply_llm_settings_json()

        # 1. 睿动规范 MUST-2: 沙箱环境用 SANDBOX_API_BASE 覆盖外网 URL
        if self.sandbox_api_base:
            object.__setattr__(self, "openai_base_url", self.sandbox_api_base)

        # 2. 三环境枚举校验
        env = self.kap_env.strip().lower()
        if env not in KAP_ENVIRONMENTS:
            raise ValueError(
                f"非法 kap_env={self.kap_env}（合法值：{KAP_ENVIRONMENTS}）"
            )
        if env != self.kap_env:
            object.__setattr__(self, "kap_env", env)

        # 3. sandbox / prod 强制 verify_ssl=True（坑 D）
        if env in (KAP_ENV_SANDBOX, KAP_ENV_PROD) and not self.llm_verify_ssl:
            object.__setattr__(self, "llm_verify_ssl", True)

        # 4. sandbox / prod 强制 allow_mock_llm=False（坑 F）
        if env in (KAP_ENV_SANDBOX, KAP_ENV_PROD) and self.allow_mock_llm:
            object.__setattr__(self, "allow_mock_llm", False)

        # 5a. sandbox / prod 强制 allow_memory_fallback=False（坑 2）
        if env in (KAP_ENV_SANDBOX, KAP_ENV_PROD) and self.allow_memory_fallback:
            object.__setattr__(self, "allow_memory_fallback", False)

        # 5. sandbox / prod 强制 allow_mock_embedding=False（坑 6）
        #    mock embedding 是哈希伪向量，prod 启用会让块③ 召回完全失效
        if env in (KAP_ENV_SANDBOX, KAP_ENV_PROD) and self.allow_mock_embedding:
            object.__setattr__(self, "allow_mock_embedding", False)
        # sandbox/prod 也强制 embedding_provider 不能是 mock
        if env in (KAP_ENV_SANDBOX, KAP_ENV_PROD) and self.embedding_provider == "mock":
            raise ValueError(
                f"sandbox/prod 环境禁止使用 mock embedding provider（kap_env={env}）。"
                f"请设置 EMBEDDING_PROVIDER=bge / ruidong / openai 之一。"
            )

        # 6. M1 ISS 集成：sandbox/prod 强制非 api_key 模式（决策书 §9.1 / PRD F4.1）
        # api_key 模式是 PoC 静态字典，sandbox/prod 必须走 ISS JWT 或网关 header 模式
        auth_mode = self.kap_auth_mode.strip().lower()
        if auth_mode not in ("api_key", "jwt", "gateway_header"):
            raise ValueError(
                f"非法 kap_auth_mode={self.kap_auth_mode}"
                f"（合法值：api_key / jwt / gateway_header）"
            )
        if auth_mode != self.kap_auth_mode:
            object.__setattr__(self, "kap_auth_mode", auth_mode)

        if env in (KAP_ENV_SANDBOX, KAP_ENV_PROD) and auth_mode == "api_key":
            # 与 verify_ssl / allow_mock_llm 同款策略：静默纠正为最安全默认值
            # gateway_header 不需要 secret/redis 即可工作，最小阻力路径
            object.__setattr__(self, "kap_auth_mode", "gateway_header")
            auth_mode = "gateway_header"

        # 7. jwt 模式（任意环境）必须有 secret 和 redis_url（避免静默旁路）
        if auth_mode == "jwt":
            if not self.iss_jwt_secret:
                raise ValueError(
                    "kap_auth_mode=jwt 但 ISS_JWT_SECRET 未配置；"
                    "JWT 验签必须有共享密钥（与 ISS-Auth 对齐）。"
                )
            if not self.iss_redis_url:
                raise ValueError(
                    "kap_auth_mode=jwt 但 ISS_REDIS_URL 未配置；"
                    "JWT 模式下需要从 ISS Redis 读取 LoginUser。"
                )

    # --- 飞书 ---
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_mock_mode: bool = True

    # --- PostgreSQL ---
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "bookworm"
    postgres_user: str = "bookworm"
    postgres_password: str = "bookworm123"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # --- Neo4j（坑 5 改造）---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "bookworm123"
    neo4j_ontology_version: str = Field(
        default="v1",
        description=(
            "当前本体版本（M0 默认 v1，M3 本体演化启用）。"
            "实体节点和关系写入时挂此属性，未来支持 as_of 历史回溯查询"
        ),
    )
    neo4j_max_reconnect_attempts: int = Field(
        default=3,
        description="Neo4j 重连失败上限",
    )

    # --- Milvus（坑 2 改造）---
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_alias: str = Field(
        default="default",
        description="pymilvus connection alias，多 collection 隔离用",
    )
    milvus_health_check_interval: float = Field(
        default=30.0,
        description="健康检查间隔（秒），低于此间隔不重复探活",
    )
    milvus_max_reconnect_attempts: int = Field(
        default=3,
        description="重连失败上限；超过则熔断抛 StorageError，不再降级内存",
    )
    milvus_reconnect_backoff_base: float = Field(
        default=1.5,
        description="重连指数退避基数（秒）",
    )
    allow_memory_fallback: bool = Field(
        default=False,
        description=(
            "Milvus 不可用时是否降级内存模式（坑 2）。"
            "False 时连接失败直接抛 StorageError，避免数据进内存重启丢。"
            "dev 可设 True；sandbox/prod 强制 False"
        ),
    )

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- MinIO ---
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "bookworm-archive"

    # --- Embedding（坑 6 改造）---
    embedding_provider: str = Field(
        default="mock",
        description=(
            "Embedding 提供方：mock / openai / ruidong / bge。"
            "sandbox/prod 由 model_post_init 强制非 mock"
        ),
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description=(
            "embedding 模型名。bge 默认 BAAI/bge-large-zh-v1.5；"
            "ruidong 默认 qwen3-embedding；openai 走 settings.embedding_model"
        ),
    )
    embedding_dim: int = Field(
        default=1536,
        description="向量维度。bge-large-zh=1024，qwen3-embedding=1024，OpenAI=1536",
    )
    embedding_batch_size: int = Field(
        default=64,
        description="批量 embed 时的单批最大文本数（睿动 / OpenAI 上限通常 100）",
    )
    allow_mock_embedding: bool = Field(
        default=False,
        description=(
            "是否允许 mock embedding（坑 6）。"
            "False 时 mock provider/无 Key/异常都直接抛 EmbeddingError，"
            "禁止伪向量污染 Milvus。dev 可设 True；sandbox/prod 强制 False"
        ),
    )

    # --- 切片策略 ---
    chunk_strategy: str = Field(default="fixed", description="切片策略: fixed, parent_child, semantic")
    chunk_size: int = Field(default=500, description="固定切片大小(字符)")
    chunk_overlap: int = Field(default=100, description="固定切片重叠(字符)")
    parent_chunk_size: int = Field(default=2000, description="父切片大小")
    child_chunk_size: int = Field(default=300, description="子切片大小")
    semantic_threshold: float = Field(default=0.5, description="语义切片阈值")
    semantic_min_chunk_size: int = Field(default=100, description="语义切片最小字符数")
    semantic_max_chunk_size: int = Field(default=1500, description="语义切片最大字符数")

    # --- 评分权重 ---
    score_alpha: float = Field(default=0.35, description="向量检索权重")
    score_beta: float = Field(default=0.25, description="图谱关联权重")
    score_gamma: float = Field(default=0.15, description="目录匹配权重")
    score_delta: float = Field(default=0.25, description="关键词检索权重(BM25)")

    # --- Reranker ---
    reranker_provider: str = Field(default="mock", description="重排器: mock, api")
    reranker_endpoint: str = Field(default="", description="Reranker API端点")
    reranker_model: str = Field(default="Qwen3-Reranker-4B", description="Reranker模型名")
    reranker_api_key: str = Field(default="", description="Reranker API Key")
    reranker_candidate_multiplier: int = Field(default=3, description="候选扩展倍数")

    # --- 决策阈值 ---
    kpi_discard_threshold: float = Field(default=0.20, description="KPI 低于此值倾向 DISCARD")
    kpi_archive_threshold: float = Field(default=0.45, description="KPI 低于此值倾向 ARCHIVE")
    review_confidence_threshold: float = Field(default=0.60, description="Judge 置信度低于此值进入人工审核")

    # M1 4×6 矩阵审核台 SLA（决策书 §5.5 D12）
    kap_w4_sla_minutes: int = Field(
        default=60,
        description="W4 实体抽取低置信度工单的 SLA 截止分钟数；超时由 sla.sweep_overdue_tasks 升级",
    )

    # M3 #2 双 Agent 互审完整版（决策书 §5.5 D13 完整版）
    pipeline_critic_enabled: bool = Field(
        default=False,
        description=(
            "是否在蒸馏 pipeline 主路径上每文档跑 LLM-Critic 6 维质疑。"
            "False（默认）= M2 lite 行为，仅 W4 hook 在低置信度时触发 critic；"
            "True = M3 完整版，主路径每文档都跑 critic，blocking issue 强制 needs_review。"
            "开启会增加 LLM 调用成本（每文档 +1 LLM 调用）。"
        ),
    )
    critic_blocking_threshold: float = Field(
        default=0.6,
        description="Critic 任一维度 severity ≥ 此值视为 blocking，强制 needs_review = True",
    )

    # M1 敏感实体识别 + 脱敏管线（决策书 §5.4 D10/D11）
    sensitive_aes_key: str = Field(
        default="",
        description=(
            "敏感映射 AES-256-GCM 密钥（32 字节 hex 或 base64）。空则映射存内存（dev 兼容）；"
            "sandbox/prod 强制非空（决策书 §5.4 D11 加密 KV）。永远不入代码"
        ),
    )
    sensitive_mapping_redis_url: str = Field(
        default="",
        description="敏感映射独立 Redis URL，与 KAP 自身 redis 解耦（私有化客户内网）",
    )
    sensitive_role_dict_path: str = Field(
        default="",
        description="角色字典 YAML 路径（默认空走内置字典；客户定制时指定）",
    )

    # --- Agent 参数 ---
    librarian_preview_chars: int = Field(default=2000, description="Librarian 发送给 LLM 的内容预览长度")
    judge_content_chars: int = Field(default=3000, description="Judge 发送给 LLM 的内容摘录长度")

    # --- 流水线并行化 ---
    pipeline_max_workers: int = Field(default=4, description="蒸馏管线每步的最大并行线程数")

    # --- 结果缓存 ---
    cache_search_ttl: int = Field(default=300, description="搜索结果缓存 TTL（秒）")
    cache_qa_ttl: int = Field(default=600, description="问答结果缓存 TTL（秒）")

    # --- 钉钉 ---
    dingtalk_app_key: str = ""
    dingtalk_app_secret: str = ""
    dingtalk_mock_mode: bool = True

    # --- 企业微信 ---
    wecom_corp_id: str = ""
    wecom_corp_secret: str = ""
    wecom_mock_mode: bool = True

    # --- 认证 ---
    auth_required: bool = Field(default=False, description="是否强制认证(PoC默认关闭)")
    api_keys: str = Field(default="", description="逗号分隔的 API Key 列表，格式: key:user_id:role")

    # --- M1 ISS 集成（决策书 §9.1 + PRD §10.4）---
    kap_auth_mode: str = Field(
        default="api_key",
        description=(
            "认证模式：api_key（M0 PoC，本地静态字典）/ jwt（验签 ISS HS512 + 共享 Redis 拿 LoginUser）/"
            " gateway_header（信任网关注入的 X-User-* header，KAP 部署在 ISS-Gateway 后面时用）。"
            "sandbox/prod 由 model_post_init 强制非 api_key"
        ),
    )
    iss_jwt_secret: str = Field(
        default="",
        description=(
            "ISS-Auth JWT HS512 共享密钥。仅 kap_auth_mode=jwt 时必填；"
            "sandbox/prod 强制非空。绝不写入代码 / 文档（决策书 §8.3）"
        ),
    )
    iss_jwt_algorithm: str = Field(
        default="HS512",
        description="JWT 算法（与 ISS JwtUtils 对齐，固定 HS512）",
    )
    iss_jwt_user_key_claim: str = Field(
        default="user_key",
        description="JWT claims 中承载 user_key UUID 的字段名（ISS SecurityConstants.USER_KEY）",
    )
    iss_redis_url: str = Field(
        default="",
        description=(
            "ISS-Auth Redis 地址（独立连接池，与 KAP redis_url 分离，私有化部署可能不同实例）。"
            "格式 redis://[user:pass@]host:port/db。kap_auth_mode=jwt 时必填"
        ),
    )
    iss_token_key_prefix: str = Field(
        default="login_tokens:",
        description="ISS Redis 中 LoginUser 的 key 前缀（CacheConstants.LOGIN_TOKEN_KEY），完整 key=prefix+user_key",
    )
    iss_system_base_url: str = Field(
        default="",
        description="ISS-System 服务 base URL（如 http://iss-system:9201），用于 RemoteUser/Dept 调用",
    )
    iss_remote_timeout: float = Field(
        default=5.0,
        description="ISS Remote HTTP 调用超时（秒）",
    )
    iss_dept_cache_ttl: int = Field(
        default=300,
        description="部门树本地缓存 TTL（秒）",
    )

    # --- CORS ---
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        description="逗号分隔的 CORS 允许来源",
    )

    # --- 服务 ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    def _apply_llm_settings_json(self) -> None:
        """把 backend/configs/llm_settings.json 的内容叠加到 settings 上。

        前端"系统设置"页通过 /api/v1/settings 写入这个文件，但历史代码只把它当 UI
        持久化用，没有反向应用到 Settings —— 导致用户配的 Key / 网关 URL / 模型名
        在重启后失效，蒸馏管线被迫报 missing api_key 或敲到错误的网关。

        优先级: 这里 JSON 直接覆盖 env / .env / 默认值。原因: KAP 是私有化部署
        平台，运维通过设置 UI 配置 LLM 是主路径；shell 里的 OPENAI_API_KEY 多半
        是开发机其他项目（GLM / Anthropic 等）残留，让它们压制 UI 配置就会出
        现"明明改了 Key 还是 401"的诡异现象。要 prod 用 env 强制时把 JSON 删掉。
        """
        if not _LLM_SETTINGS_JSON.exists():
            return
        try:
            data = json.loads(_LLM_SETTINGS_JSON.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        # provider 别名规整：ruidong -> openai (iruidong 是 OpenAI 兼容网关)
        provider = data.get("llm_provider")
        if provider:
            provider = _LLM_PROVIDER_ALIAS.get(provider, provider)
            object.__setattr__(self, "llm_provider", provider)
        if data.get("openai_api_key"):
            object.__setattr__(self, "openai_api_key", data["openai_api_key"])
        if data.get("openai_base_url"):
            object.__setattr__(self, "openai_base_url", data["openai_base_url"])
        if data.get("llm_model"):
            object.__setattr__(self, "llm_model", data["llm_model"])
        if data.get("embedding_provider"):
            object.__setattr__(self, "embedding_provider", data["embedding_provider"])
        if data.get("embedding_model"):
            object.__setattr__(self, "embedding_model", data["embedding_model"])
        if data.get("embedding_dim"):
            try:
                object.__setattr__(self, "embedding_dim", int(data["embedding_dim"]))
            except (TypeError, ValueError):
                pass

    def validate_dependencies(self) -> dict[str, dict]:
        """检测外部依赖连通性，返回各组件状态。"""
        import socket
        results: dict[str, dict] = {}

        # PostgreSQL
        try:
            s = socket.create_connection((self.postgres_host, self.postgres_port), timeout=3)
            s.close()
            results["postgresql"] = {"status": "ok", "addr": f"{self.postgres_host}:{self.postgres_port}"}
        except Exception as e:
            results["postgresql"] = {"status": "unavailable", "error": str(e)}

        # Neo4j
        try:
            host = self.neo4j_uri.replace("bolt://", "").replace("neo4j://", "").split(":")[0]
            port = int(self.neo4j_uri.split(":")[-1].split("/")[0]) if ":" in self.neo4j_uri.split("//")[-1] else 7687
            s = socket.create_connection((host, port), timeout=3)
            s.close()
            results["neo4j"] = {"status": "ok", "addr": f"{host}:{port}"}
        except Exception as e:
            results["neo4j"] = {"status": "unavailable", "error": str(e)}

        # Milvus
        try:
            s = socket.create_connection((self.milvus_host, self.milvus_port), timeout=3)
            s.close()
            results["milvus"] = {"status": "ok", "addr": f"{self.milvus_host}:{self.milvus_port}"}
        except Exception as e:
            results["milvus"] = {"status": "unavailable", "error": str(e)}

        # Redis
        try:
            from urllib.parse import urlparse
            parsed = urlparse(self.redis_url)
            host = parsed.hostname or "localhost"
            port = parsed.port or 6379
            s = socket.create_connection((host, port), timeout=3)
            s.close()
            results["redis"] = {"status": "ok", "addr": f"{host}:{port}"}
        except Exception as e:
            results["redis"] = {"status": "unavailable", "error": str(e)}

        # MinIO
        try:
            host, port = self.minio_endpoint.split(":")
            s = socket.create_connection((host, int(port)), timeout=3)
            s.close()
            results["minio"] = {"status": "ok", "addr": self.minio_endpoint}
        except Exception as e:
            results["minio"] = {"status": "unavailable", "error": str(e)}

        return results


settings = Settings()
