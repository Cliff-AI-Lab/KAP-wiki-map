"""块① 知识咨询智能体 · 独立入口（M21 #1）。

仅装载 architect router；可独立部署提供"AI 对话式建知识体系"服务。

启动：
    python run_architect.py            # dev :8011
    uvicorn api.main_architect:app --port 8011

无缝衔接（连起来用）：
- 把生成的 Schema/Wiki 草稿 POST 到 storage block：
    KAP_STORAGE_BASE=http://localhost:8012  python run_architect.py
- architect 内部用 ``packages.integration.clients.StorageClient`` 调对方
"""

from api.app_factory import create_app

app = create_app(
    blocks=["architect"],
    title="KAP · 咨询中心",
    serve_spa=False,    # 咨询中心是独立对话 UI，不走 V15 SPA
)
