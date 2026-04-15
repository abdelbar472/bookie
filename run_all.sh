#!/bin/bash

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PIDS=()

# Assigned HTTP ports
AUTH_HTTP_PORT=8001
USER_HTTP_PORT=8002
FOLLOW_HTTP_PORT=8003
SOCIAL_HTTP_PORT=8004
RAG_HTTP_PORT=8005
RECOMMENDATION_HTTP_PORT=8006
BOOK_HTTP_PORT=8007

# Assigned gRPC ports
AUTH_GRPC_PORT=50051
USER_GRPC_PORT=50052
FOLLOW_GRPC_PORT=50053
SOCIAL_GRPC_PORT=50054
RAG_GRPC_PORT=50055
RECOMMENDATION_GRPC_PORT=50056
BOOK_GRPC_PORT=50057

if [[ -x "$PROJECT_ROOT/.venv/Scripts/python.exe" ]]; then
  PYTHON_BIN="$PROJECT_ROOT/.venv/Scripts/python.exe"
else
  PYTHON_BIN="python"
fi

cleanup() {
  echo -e "\n${YELLOW}Stopping all services...${NC}"
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
}

trap cleanup SIGINT SIGTERM EXIT

start_service() {
  local name="$1"
  local module="$2"
  local port="$3"
  local dir_check="$4"

  if [[ ! -d "$PROJECT_ROOT/$dir_check" ]]; then
    echo -e "${RED}Skipping ${name}: missing directory '$dir_check'${NC}"
    return
  fi

  echo -e "${GREEN}Starting ${name} on port ${port}...${NC}"
  (
    cd "$PROJECT_ROOT"
    PYTHONPATH="$PROJECT_ROOT" "$PYTHON_BIN" -m uvicorn "$module":app --host 0.0.0.0 --port "$port" --reload
  ) &
  PIDS+=("$!")
  sleep 1
}

echo "========================================"
echo "Bookie Microservices Launcher"
echo "========================================"

# Startup order: identity first, then dependents.
start_service "auth" "auth.main" "$AUTH_HTTP_PORT" "auth"
sleep 2
start_service "user" "user.main" "$USER_HTTP_PORT" "user"
start_service "follow" "follow.main" "$FOLLOW_HTTP_PORT" "follow"
start_service "book" "book.main" "$BOOK_HTTP_PORT" "book"
start_service "rag" "rag.main" "$RAG_HTTP_PORT" "rag"
start_service "recommendation" "recommendation.main" "$RECOMMENDATION_HTTP_PORT" "recommendation"
start_service "social" "social.main" "$SOCIAL_HTTP_PORT" "social"

echo "========================================"
echo "Services started"
echo ""
echo "API Docs:"
echo "  Auth:           http://localhost:${AUTH_HTTP_PORT}/docs"
echo "  User:           http://localhost:${USER_HTTP_PORT}/docs"
echo "  Follow:         http://localhost:${FOLLOW_HTTP_PORT}/docs"
echo "  Social:         http://localhost:${SOCIAL_HTTP_PORT}/docs"
echo "  RAG Service:    http://localhost:${RAG_HTTP_PORT}/docs"
echo "  Recommendation: http://localhost:${RECOMMENDATION_HTTP_PORT}/docs"
echo "  Book:           http://localhost:${BOOK_HTTP_PORT}/docs"
echo ""
echo "Assigned gRPC Ports:"
echo "  Auth:           ${AUTH_GRPC_PORT}"
echo "  Follow:         ${FOLLOW_GRPC_PORT}"
echo "  User:           ${USER_GRPC_PORT}"
echo "  Social:         ${SOCIAL_GRPC_PORT}"
echo "  RAG Service:    ${RAG_GRPC_PORT}"
echo "  Recommendation: ${RECOMMENDATION_GRPC_PORT}"
echo "  Book:           ${BOOK_GRPC_PORT}"
echo ""
echo "Press Ctrl+C to stop all services"
echo "========================================"

wait
