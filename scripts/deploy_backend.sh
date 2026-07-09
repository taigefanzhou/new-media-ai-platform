#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${DEPLOY_HOST:-root@82.156.2.200}"
REMOTE_DIR="${DEPLOY_DIR:-/opt/new-media-ai-platform}"
CONTAINER="${DEPLOY_CONTAINER:-server-platform-api-1}"

rsync -az --delete --exclude='__pycache__' "$ROOT/backend/app/" "$HOST:$REMOTE_DIR/backend/app/"
rsync -az --delete "$ROOT/backend/tests/" "$HOST:$REMOTE_DIR/backend/tests/"
ssh "$HOST" "docker cp $REMOTE_DIR/backend/app $CONTAINER:/app/ && docker restart $CONTAINER >/dev/null && sleep 3 && docker ps --filter name=$CONTAINER --format '{{.Names}} {{.Status}}'"
