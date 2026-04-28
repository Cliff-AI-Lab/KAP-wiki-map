"""全局配置管理，通过环境变量或 .env 文件加载。"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

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
        default=60.0,
        description="LLM HTTP 请求超时（秒），统一 openai/anthropic（原 60/10 不一致已修复）",
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

    # --- Neo4j ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "bookworm123"

    # --- Milvus ---
    milvus_host: str = "localhost"
    milvus_port: int = 19530

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- MinIO ---
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "bookworm-archive"

    # --- Embedding ---
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

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

    # --- CORS ---
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        description="逗号分隔的 CORS 允许来源",
    )

    # --- 服务 ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000

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
