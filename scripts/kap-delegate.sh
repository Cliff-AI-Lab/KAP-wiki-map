#!/usr/bin/env bash
# kap-delegate.sh —— bash 包装器，转发参数到 kap-delegate.py
# 用法：./kap-delegate.sh [选项] "任务描述"
# 完整文档：scripts/README.md

set -e
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if ! command -v python >/dev/null 2>&1; then
  echo "[x] 未找到 python，请先安装 Python 3.9+" >&2
  exit 1
fi

if [ -z "${IRUIDONG_API_KEY}" ]; then
  echo "[!] 警告：IRUIDONG_API_KEY 未设置" >&2
  echo "    Windows: setx IRUIDONG_API_KEY sk-..." >&2
  echo "    Linux/Mac: export IRUIDONG_API_KEY=sk-..." >&2
fi

exec python "${SCRIPT_DIR}/kap-delegate.py" "$@"
