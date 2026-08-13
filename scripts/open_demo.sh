#!/usr/bin/env bash
# open_demo.sh：一键打开 DockingCopilot 网页 Demo（幂等）。
# 行为：
#   1. 检测后端（默认 127.0.0.1:8000）与前端（默认 localhost:5173）是否已在运行；
#   2. 未运行的服务按与 Makefile 相同的方式后台启动（后端带 PYTHONPATH=backend，
#      前端 stdin 重定向 /dev/null 防止后台进程收到 SIGTTIN 被挂起）；
#   3. 轮询等待服务就绪后，用系统命令打开浏览器（macOS: open；Linux: xdg-open）；
#   4. 无 GUI / headless 环境下 open 失败不中断流程，仅打印链接（退出码仍为 0）。
# 已在运行的服务绝不会被重启或打断。
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
FRONTEND_URL="http://localhost:${FRONTEND_PORT}"
BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}/health"
LOG_DIR="${ROOT}/outputs/logs"
mkdir -p "${LOG_DIR}"

# conda 环境：已激活 dockskill 直接用 python，否则 conda run 包装
if [ "${CONDA_DEFAULT_ENV:-}" = "dockskill" ]; then
  PY="python"
else
  PY="conda run -n dockskill python"
fi

is_up() { curl -s -o /dev/null --max-time 2 "$1"; }

wait_up() { # wait_up <url> <seconds>
  local i=0
  while [ "$i" -lt "$2" ]; do
    if is_up "$1"; then return 0; fi
    sleep 1
    i=$((i + 1))
  done
  return 1
}

# ---------- 后端（8000）----------
if is_up "${BACKEND_URL}"; then
  echo "[open_demo] 后端已在运行：${BACKEND_URL}"
else
  echo "[open_demo] 后端未运行，后台启动 uvicorn（日志 ${LOG_DIR}/backend.log）..."
  (
    cd "${ROOT}"
    export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:${PYTHONPATH}}"
    nohup ${PY} -m uvicorn backend.app.main:app \
      --host "${BACKEND_HOST}" --port "${BACKEND_PORT}" --workers 1 \
      </dev/null >"${LOG_DIR}/backend.log" 2>&1 &
  )
  if wait_up "${BACKEND_URL}" 45; then
    echo "[open_demo] 后端就绪：${BACKEND_URL}"
  else
    echo "[open_demo] 警告：后端 45s 内未就绪，请检查 ${LOG_DIR}/backend.log"
  fi
fi

# ---------- 前端（5173）----------
if is_up "${FRONTEND_URL}"; then
  echo "[open_demo] 前端已在运行：${FRONTEND_URL}"
else
  echo "[open_demo] 前端未运行，后台启动 vite（日志 ${LOG_DIR}/frontend.log）..."
  if [ ! -d "${ROOT}/frontend/node_modules" ]; then
    echo "[open_demo] 首次运行：安装前端依赖（npm install）..."
    (cd "${ROOT}/frontend" && npm install --no-fund --no-audit) || true
  fi
  (cd "${ROOT}/frontend" && nohup npm run dev </dev/null >"${LOG_DIR}/frontend.log" 2>&1 &)
  if wait_up "${FRONTEND_URL}" 60; then
    echo "[open_demo] 前端就绪：${FRONTEND_URL}"
  else
    echo "[open_demo] 警告：前端 60s 内未就绪，请检查 ${LOG_DIR}/frontend.log"
  fi
fi

# ---------- 打开浏览器（失败容错，不中断）----------
echo "[open_demo] 网页 Demo：${FRONTEND_URL}"
OPENED=0
if command -v open >/dev/null 2>&1; then
  if open "${FRONTEND_URL}" 2>/dev/null; then OPENED=1; fi
elif command -v xdg-open >/dev/null 2>&1; then
  if xdg-open "${FRONTEND_URL}" 2>/dev/null; then OPENED=1; fi
fi
if [ "${OPENED}" -eq 1 ]; then
  echo "[open_demo] 已在浏览器中打开：${FRONTEND_URL}"
else
  echo "[open_demo] 未能自动打开浏览器（可能为无 GUI / headless 环境）。"
  echo "[open_demo] 请手动访问：[DockingCopilot 网页 Demo](${FRONTEND_URL})"
fi
exit 0
