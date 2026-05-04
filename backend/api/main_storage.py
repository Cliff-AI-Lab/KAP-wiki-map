"""块② 知识管理 + 存储中心 · 独立入口（M21 #1）。

装载治理 / 本体 / Wiki / 图谱 / 项目 / 敏感映射 / 审计等存储侧能力，
是 KAP 三块中最重的服务（含 6 工位 + 4×6 矩阵 + 双层本体演化 + 影子库重抽）。

启动：
    python run_storage.py             # dev :8012
    uvicorn api.main_storage:app --port 8012

可单独使用：作为企业知识库底座（不需要块①咨询和块③消费门户也能用）。
连起来：通过 architect 的 SchemaCommitClient 接收建好的体系；通过 portal 暴露查询。
"""

from api.app_factory import create_app

app = create_app(
    blocks=["storage"],
    title="KAP · 知识中心",
    serve_spa=True,    # 知识中心是治理主面板，挂 V15 SPA
)
