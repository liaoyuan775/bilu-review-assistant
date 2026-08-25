#!/usr/bin/env bash
# 笔录审查助手一键部署（Docker Compose）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# 自愈：若从 Windows 拷过来带 \r，先去掉再继续
if grep -q $'\r' "$0" 2>/dev/null; then
  tmp="$(mktemp)"
  tr -d '\r' <"$0" >"$tmp"
  chmod +x "$tmp"
  exec bash "$tmp" "$@"
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERR] 未找到 docker，请先安装 Docker / Docker Compose"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "[ERR] 需要 Docker Compose v2（docker compose）"
  exit 1
fi

# 包结构校验（避免人在错误目录执行）
if [[ ! -f ../../backend/Dockerfile ]] || [[ ! -f ../../backend/requirements.txt ]]; then
  echo "[ERR] 当前目录不对。请在解压后的 deploy/app 下执行："
  echo "      cd <解压目录>/deploy/app && ./deploy.sh"
  echo "      当前: $ROOT"
  exit 1
fi

if [[ ! -f ../../backend/app/main.py ]]; then
  echo "[ERR] 缺少 ../../backend/app/main.py，请重新打包上传"
  exit 1
fi

if [[ ! -f ../../backend/app/data/rules.py ]]; then
  echo "[ERR] 缺少 ../../backend/app/data/rules.py（app.data 必须进包），请重新打包上传"
  exit 1
fi

if [[ ! -f ../../backend/app/data/domain_contracts.py ]]; then
  echo "[ERR] 缺少 ../../backend/app/data/domain_contracts.py，请重新打包上传"
  exit 1
fi

if [[ ! -f ../../backend/template_rules.json ]]; then
  echo "[ERR] 缺少 ../../backend/template_rules.json，请重新打包上传"
  exit 1
fi

if [[ ! -f ../../backend/domain-contracts/header_procedure.json ]]; then
  echo "[ERR] 缺少 ../../backend/domain-contracts，请重新打包上传"
  exit 1
fi

if [[ ! -f ../../backend/prompt-templates/domain-extraction.txt ]]; then
  echo "[ERR] 缺少 ../../backend/prompt-templates/domain-extraction.txt，请重新打包上传"
  exit 1
fi

if [[ ! -f ../../backend/prompt-templates/domains/online-money.txt ]]; then
  echo "[ERR] 缺少域提示词 ../../backend/prompt-templates/domains，请重新打包上传"
  exit 1
fi

if [[ ! -f ../../backend/test-fixtures/01-baseline.docx ]]; then
  echo "[ERR] 缺少演示样例 ../../backend/test-fixtures/01-baseline.docx，请重新打包上传"
  exit 1
fi
if [[ ! -f ../../backend/test-fixtures/06-all-statuses-demo.docx ]]; then
  echo "[ERR] 缺少演示样例 ../../backend/test-fixtures/06-all-statuses-demo.docx，请重新打包上传"
  exit 1
fi

if [[ ! -f ../../frontend/package.json ]] || [[ ! -f ../../frontend/package-lock.json ]]; then
  echo "[ERR] 缺少 frontend/package.json 或 package-lock.json，请重新打包上传"
  exit 1
fi

if ! grep -q 'uvicorn' ../../backend/requirements.txt; then
  echo "[ERR] requirements.txt 未含 uvicorn，请重新打包上传"
  exit 1
fi
if ! grep -q 'mirrors.aliyun.com' ../../backend/Dockerfile; then
  echo "[ERR] backend Dockerfile 未使用国内镜像，请重新打包上传"
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "[OK] 已生成 .env（来自 .env.example，含模型密钥和 SQLite 路径）"
fi

# 去掉 .env 可能的 CRLF，避免变量名异常
if grep -q $'\r' .env 2>/dev/null; then
  tr -d '\r' <.env >.env.tmp && mv .env.tmp .env
  echo "[OK] 已清除 .env 中的 Windows 换行"
fi

if ! grep -qE '^QWEN_API_KEY=.+' .env || grep -qE 'replace-with-your-api-key|your-api-key-here' .env; then
  echo "[ERR] .env 缺少有效 QWEN_API_KEY"
  exit 2
fi
if ! grep -qE '^QWEN_BASE_URL=.+' .env; then
  echo "[ERR] .env 缺少 QWEN_BASE_URL"
  exit 2
fi
if ! grep -qE '^QWEN_MODEL=.+' .env; then
  echo "[ERR] .env 缺少 QWEN_MODEL"
  exit 2
fi
if ! grep -qE '^QWEN_DOMAIN_CONCURRENCY=.+' .env; then
  echo "[ERR] .env 缺少 QWEN_DOMAIN_CONCURRENCY"
  exit 2
fi
if ! grep -qE '^REVIEW_DATABASE_PATH=.+' .env; then
  echo "[ERR] .env 缺少 REVIEW_DATABASE_PATH，请重新打包上传"
  exit 2
fi
if ! grep -qE '^DATABASE_URL=sqlite' .env; then
  echo "[ERR] .env 缺少 DATABASE_URL（sqlite），请重新打包上传"
  exit 2
fi
if ! grep -qE '^FRONTEND_PORT=.+' .env; then
  echo "[ERR] .env 缺少 FRONTEND_PORT"
  exit 2
fi
if ! grep -qE '^BACKEND_PORT=.+' .env; then
  echo "[ERR] .env 缺少 BACKEND_PORT"
  exit 2
fi

# 默认走 Docker 层缓存，不会每次重下 pip / npm
# 只有显式 FORCE_REBUILD=1 才 --no-cache（调试用，平时别开）
export DOCKER_BUILDKIT=1
BUILD_ARGS=(up -d --build)
if [[ "${FORCE_REBUILD:-0}" == "1" ]]; then
  echo "[..] FORCE_REBUILD=1：无缓存全量重建（会重新下载依赖）"
  docker compose build --no-cache
  BUILD_ARGS=(up -d)
else
  echo "[..] 构建并启动（复用缓存；并发读 env: QWEN_DOMAIN_CONCURRENCY）"
fi

if ! docker compose "${BUILD_ARGS[@]}"; then
  echo
  echo "[ERR] 启动失败，后端最近日志："
  docker compose logs --tail=120 backend || true
  echo
  echo "完整日志: docker compose logs -f backend"
  exit 1
fi

BACKEND_STATE="$(docker inspect -f '{{.State.Status}}' bilu2-backend 2>/dev/null || echo missing)"
if [[ "$BACKEND_STATE" != "running" ]]; then
  echo "[ERR] backend 状态 $BACKEND_STATE，日志如下："
  docker logs --tail=120 bilu2-backend || true
  exit 1
fi

echo "[..] 等待后端 /api/v1/health 就绪…"
BACK_PORT="$(grep -E '^BACKEND_PORT=' .env | cut -d= -f2- || true)"
BACK_PORT="${BACK_PORT:-6678}"

_check_health() {
  if command -v curl >/dev/null 2>&1; then
    curl -fsS "http://127.0.0.1:${BACK_PORT}/api/v1/health" >/dev/null 2>&1
    return $?
  fi
  docker exec bilu2-backend python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/api/v1/health', timeout=12)" \
    >/dev/null 2>&1
}

ok=0
for i in $(seq 1 60); do
  if _check_health; then
    ok=1
    break
  fi
  st="$(docker inspect -f '{{.State.Status}}' bilu2-backend 2>/dev/null || echo missing)"
  if [[ "$st" != "running" ]]; then
    echo "[ERR] 等待健康检查时 backend 已退出（status=$st）"
    docker logs --tail=160 bilu2-backend || true
    exit 1
  fi
  sleep 2
done

if [[ "$ok" != "1" ]]; then
  echo "[ERR] 120s 后 /api/v1/health 仍不可用，日志如下："
  docker logs --tail=160 bilu2-backend || true
  docker compose ps || true
  exit 1
fi

if ! docker exec bilu2-backend test -f /app/template_rules.json; then
  echo "[ERR] 容器内缺少 /app/template_rules.json"
  exit 1
fi
if ! docker exec bilu2-backend test -f /app/prompt-templates/domain-extraction.txt; then
  echo "[ERR] 容器内缺少提示词 /app/prompt-templates/domain-extraction.txt"
  docker exec bilu2-backend ls -l /app/prompt-templates/ || true
  exit 1
fi
if ! docker exec bilu2-backend test -f /app/test-fixtures/01-baseline.docx; then
  echo "[ERR] 容器内缺少演示样例 /app/test-fixtures/01-baseline.docx"
  docker exec bilu2-backend ls -l /app/test-fixtures/ || true
  exit 1
fi

echo
echo "[OK] 已启动（health 通过）"
docker compose ps
echo
FRONT_PORT="$(grep -E '^FRONTEND_PORT=' .env | cut -d= -f2- || true)"
FRONT_PORT="${FRONT_PORT:-5175}"
echo "前端:  http://<服务器IP>:${FRONT_PORT}"
echo "健康检查:  http://<服务器IP>:${BACK_PORT}/api/v1/health"
echo "本机自检: curl -s http://127.0.0.1:${BACK_PORT}/api/v1/health"
echo "日志:  docker compose logs -f"
echo "停止:  docker compose down"
