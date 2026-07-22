#!/usr/bin/env bash
set -Eeuo pipefail

STACK_DIR="${STACK_DIR:-/opt/aimeton/auditor-stack}"
SOURCE_DIR="${SOURCE_DIR:-${GITHUB_WORKSPACE:-$PWD}}"
DEPLOY_SHA="${DEPLOY_SHA:-${GITHUB_SHA:-}}"
STAGE_URL="${STAGE_URL:-https://stage-auditor.aimeton.ru}"
SERVICE="${SERVICE:-auditor}"
CONTAINER="${CONTAINER:-aimeton-auditor}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-180}"
BACKUP_KEEP="${BACKUP_KEEP:-5}"
LOCK_FILE="${LOCK_FILE:-/tmp/aimeton-auditor-stage-deploy.lock}"

log() {
  printf '%s %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

fail() {
  log "ERROR: $*"
  exit 1
}

[[ -n "$DEPLOY_SHA" ]] || fail "DEPLOY_SHA is required"
[[ "$DEPLOY_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "DEPLOY_SHA must be a full 40-character commit SHA"
[[ -d "$STACK_DIR" ]] || fail "Stack directory not found: $STACK_DIR"
[[ -f "$STACK_DIR/docker-compose.yml" ]] || fail "docker-compose.yml not found in $STACK_DIR"
[[ -d "$SOURCE_DIR" ]] || fail "Source directory not found: $SOURCE_DIR"
[[ -f "$SOURCE_DIR/app/main.py" ]] || fail "app/main.py missing from source"
[[ -f "$SOURCE_DIR/app/mcp_server.py" ]] || fail "app/mcp_server.py missing from source"
[[ -f "$SOURCE_DIR/requirements.txt" ]] || fail "requirements.txt missing from source"

exec 9>"$LOCK_FILE"
flock -n 9 || fail "Another stage deployment is already running"

DEPLOY_ROOT="$STACK_DIR/.deployments"
STAGING_DIR="$DEPLOY_ROOT/app-source.$DEPLOY_SHA.$$.staging"
BACKUP_DIR="$DEPLOY_ROOT/app-source.backup.$(date -u +'%Y%m%dT%H%M%SZ').${DEPLOY_SHA:0:12}"
FAILED_DIR="$DEPLOY_ROOT/app-source.failed.$(date -u +'%Y%m%dT%H%M%SZ').${DEPLOY_SHA:0:12}"
CURRENT_DIR="$STACK_DIR/app-source"
SHA_FILE="$STACK_DIR/app-source-sha.txt"
PREVIOUS_SHA="unknown"
SWITCHED=0

mkdir -p "$DEPLOY_ROOT"

if [[ -f "$SHA_FILE" ]]; then
  PREVIOUS_SHA="$(tr -d '[:space:]' < "$SHA_FILE")"
fi

wait_healthy() {
  local deadline=$((SECONDS + HEALTH_TIMEOUT))
  local status

  while (( SECONDS < deadline )); do
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$CONTAINER" 2>/dev/null || true)"
    log "Container status: ${status:-not-found}"
    if [[ "$status" == "healthy" ]]; then
      return 0
    fi
    if [[ "$status" == "unhealthy" || "$status" == "exited" || "$status" == "dead" ]]; then
      return 1
    fi
    sleep 5
  done

  return 1
}

smoke_test() {
  local headers body status location

  log "Smoke: GET /api/health"
  body="$(curl --fail --silent --show-error --max-time 30 "$STAGE_URL/api/health")"
  python3 - "$body" <<'PY'
import json
import sys
payload = json.loads(sys.argv[1])
assert payload.get("status") == "ok", payload
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
PY

  log "Smoke: /mcp relative redirect"
  headers="$(mktemp)"
  status="$(curl --silent --show-error --max-time 30 --max-redirs 0 -D "$headers" -o /dev/null -w '%{http_code}' "$STAGE_URL/mcp" || true)"
  [[ "$status" == "307" ]] || { cat "$headers"; rm -f "$headers"; return 1; }
  location="$(awk 'BEGIN{IGNORECASE=1} /^location:/ {gsub("\\r", "", $2); print $2}' "$headers" | tail -n 1)"
  cat "$headers"
  rm -f "$headers"
  [[ "$location" == "/mcp/" ]] || { log "Unexpected Location: $location"; return 1; }

  log "Smoke: MCP initialize"
  body="$(curl --fail --silent --show-error --max-time 30 \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"stage-deploy-smoke","version":"1.0"}}}' \
    "$STAGE_URL/mcp/")"
  python3 - "$body" <<'PY'
import json
import sys
payload = json.loads(sys.argv[1])
assert payload.get("jsonrpc") == "2.0", payload
assert payload.get("id") == 1, payload
result = payload.get("result") or {}
assert result.get("protocolVersion"), payload
assert (result.get("serverInfo") or {}).get("name") == "AIMETON Site Auditor", payload
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
PY
}

rollback() {
  local reason="$1"
  log "ROLLBACK: $reason"

  if (( SWITCHED == 1 )) && [[ -d "$BACKUP_DIR" ]]; then
    if [[ -d "$CURRENT_DIR" ]]; then
      mv "$CURRENT_DIR" "$FAILED_DIR"
    fi
    mv "$BACKUP_DIR" "$CURRENT_DIR"
    printf '%s\n' "$PREVIOUS_SHA" > "$SHA_FILE"

    (
      cd "$STACK_DIR"
      docker compose build "$SERVICE"
      docker compose up -d --force-recreate "$SERVICE"
    )

    if wait_healthy; then
      log "Rollback restored SHA: $PREVIOUS_SHA"
    else
      log "CRITICAL: rollback container did not become healthy"
    fi
  else
    log "Rollback skipped: bundle was not switched"
  fi

  docker logs --tail 200 "$CONTAINER" || true
  exit 1
}

trap 'rollback "unexpected failure at line $LINENO"' ERR

log "Preparing deployment SHA $DEPLOY_SHA from $SOURCE_DIR"
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"

tar \
  --exclude='.git' \
  --exclude='.github' \
  --exclude='.pytest_cache' \
  --exclude='__pycache__' \
  --exclude='.venv' \
  --exclude='*.pyc' \
  -C "$SOURCE_DIR" -cf - . | tar -C "$STAGING_DIR" -xf -

[[ -f "$STAGING_DIR/app/main.py" ]] || fail "Staged app/main.py missing"
[[ -f "$STAGING_DIR/app/mcp_server.py" ]] || fail "Staged app/mcp_server.py missing"
[[ -f "$STAGING_DIR/requirements.txt" ]] || fail "Staged requirements.txt missing"

grep -q 'stage-auditor.aimeton.ru' "$STAGING_DIR/app/mcp_server.py" || fail "Stage MCP host allowlist missing"
grep -q 'Location.*\/mcp\/' "$STAGING_DIR/app/main.py" || fail "Relative MCP redirect implementation missing"

log "Switching bundle atomically; previous SHA: $PREVIOUS_SHA"
if [[ -d "$CURRENT_DIR" ]]; then
  mv "$CURRENT_DIR" "$BACKUP_DIR"
fi
mv "$STAGING_DIR" "$CURRENT_DIR"
printf '%s\n' "$DEPLOY_SHA" > "$SHA_FILE"
SWITCHED=1

log "Building and recreating Docker service: $SERVICE"
(
  cd "$STACK_DIR"
  docker compose build "$SERVICE"
  docker compose up -d --force-recreate "$SERVICE"
)

wait_healthy || rollback "container failed health check"
smoke_test || rollback "stage smoke test failed"

trap - ERR

DEPLOYED_SHA="$(tr -d '[:space:]' < "$SHA_FILE")"
[[ "$DEPLOYED_SHA" == "$DEPLOY_SHA" ]] || rollback "deployed SHA mismatch: $DEPLOYED_SHA"

log "DEPLOYMENT PASS"
log "Deployed SHA: $DEPLOYED_SHA"
log "Previous SHA: $PREVIOUS_SHA"
log "Backup: $BACKUP_DIR"

docker ps --filter "name=$CONTAINER" --format 'container={{.Names}} image={{.Image}} status={{.Status}}'

mapfile -t OLD_BACKUPS < <(find "$DEPLOY_ROOT" -maxdepth 1 -type d -name 'app-source.backup.*' -printf '%T@ %p\n' | sort -rn | awk -v keep="$BACKUP_KEEP" 'NR>keep {$1=""; sub(/^ /, ""); print}')
for old_backup in "${OLD_BACKUPS[@]:-}"; do
  [[ -n "$old_backup" ]] || continue
  log "Removing expired backup: $old_backup"
  rm -rf "$old_backup"
done
