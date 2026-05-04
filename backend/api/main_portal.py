"""块③ 渐进式消费门户 · 独立入口（M21 #1）。

装载 QA（Wiki / RAG / 图谱三路召回）+ 召回测试 + 运营观察 + ISS-Job 协调。

启动：
    python run_portal.py              # dev :8013
    uvicorn api.main_portal:app --port 8013

可单独使用：连接已有知识库（如 ISS / 第三方）暴露问答 + 仪表盘。
连起来：通过 KAP_STORAGE_BASE 指向块②，自动从 storage 拉 Wiki/图谱/向量。
"""

from api.app_factory import create_app

app = create_app(
    blocks=["portal"],
    title="KAP · 消费中心",
    serve_spa=True,    # 消费中心暴露 ReaderHome / 仪表盘 SPA
)
