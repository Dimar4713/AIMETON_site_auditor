#!/usr/bin/env bash
set -Eeuo pipefail

STACK_DIR="${STACK_DIR:-/opt/aimeton/auditor-stack}"
STAGE_URL="${STAGE_URL:-https://stage-auditor.aimeton.ru}"
SERVICE="${SERVICE:-auditor}"
CONTAINER="${CONTAINER:-aimeton-auditor}"
RUNTIME_SECRETS_FILE="$STACK_DIR/.runtime-secrets.env"
COMPOSE_OVERRIDE_FILE="$STACK_DIR/docker-compose.runtime-secrets.yml"
DADATA_API="${DADATA_API:-}"
DADATA_SECRET="${DADATA_SECRET:-}"
DADATA_SMOKE_QUERY="${DADATA_SMOKE_QUERY:-7707083893}"

log() {
  printf '%s %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

fail() {
  log "ERROR: $*"
  exit 1
}

[[ -d "$STACK_DIR" ]] || fail "Stack directory not found"
[[ -f "$STACK_DIR/docker-compose.yml" ]] || fail "docker-compose.yml not found"
[[ -f "$COMPOSE_OVERRIDE_FILE" ]] || fail "runtime compose override not found"
[[ -n "$DADATA_API" ]] || fail "DADATA_API is required"
[[ -n "$DADATA_SECRET" ]] || fail "DADATA_SECRET is required"
[[ "$DADATA_API" != *$'\n'* ]] || fail "DADATA_API contains a newline"
[[ "$DADATA_SECRET" != *$'\n'* ]] || fail "DADATA_SECRET contains a newline"
[[ "$DADATA_SMOKE_QUERY" =~ ^[0-9]{10,15}$ ]] || fail "DADATA_SMOKE_QUERY must be an INN or OGRN"

umask 077
tmp="$(mktemp "$STACK_DIR/.runtime-secrets.dadata.XXXXXX")"

python3 - "$RUNTIME_SECRETS_FILE" "$tmp" <<'PY'
from pathlib import Path
import os
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
api = os.environ["DADATA_API"]
secret = os.environ["DADATA_SECRET"]

kept = []
if source.exists():
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.startswith(("DADATA_API=", "DADATA_SECRET=")):
            kept.append(line)
kept.extend([f"DADATA_API={api}", f"DADATA_SECRET={secret}"])
target.write_text("\n".join(kept) + "\n", encoding="utf-8")
PY

chmod 600 "$tmp"
mv "$tmp" "$RUNTIME_SECRETS_FILE"
log "DaData runtime credentials installed without exposing values"

(
  cd "$STACK_DIR"
  docker compose \
    -f docker-compose.yml \
    -f "$COMPOSE_OVERRIDE_FILE" \
    up -d --force-recreate "$SERVICE"
)

for _ in $(seq 1 36); do
  status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$CONTAINER" 2>/dev/null || true)"
  [[ "$status" == "healthy" ]] && break
  [[ "$status" == "unhealthy" || "$status" == "exited" || "$status" == "dead" ]] && fail "container failed after DaData configuration"
  sleep 5
done

status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$CONTAINER" 2>/dev/null || true)"
[[ "$status" == "healthy" ]] || fail "container did not become healthy"

health="$(curl --fail --silent --show-error --max-time 30 "$STAGE_URL/api/missions/registry-mirror/dadata/health")"
python3 - "$health" <<'PY'
import json
import sys
payload = json.loads(sys.argv[1])
assert payload.get("provider") == "dadata", payload
assert payload.get("configured") is True, payload
assert "api_token_present" in payload, payload
assert "secret_present" in payload, payload
assert payload["api_token_present"] is True, payload
assert payload["secret_present"] is True, payload
print(json.dumps({"provider": "dadata", "configured": True}, ensure_ascii=False))
PY

lookup="$(curl --fail --silent --show-error --max-time 30 \
  -H 'Content-Type: application/json' \
  --data "{\"query\":\"$DADATA_SMOKE_QUERY\"}" \
  "$STAGE_URL/api/missions/registry-mirror/dadata/find-party")"
python3 - "$lookup" <<'PY'
import json
import sys
payload = json.loads(sys.argv[1])
assert payload.get("provider") == "dadata", payload
assert payload.get("authority_verified") is False, payload
assert payload.get("state") in {"registry_mirror_verified", "unresolved", "conflicting"}, payload
assert "document_digest" in payload or payload.get("state") == "unresolved", payload
print(json.dumps({
    "provider": payload.get("provider"),
    "state": payload.get("state"),
    "authority_verified": payload.get("authority_verified"),
}, ensure_ascii=False, sort_keys=True))
PY

log "DaData stage live smoke passed"
