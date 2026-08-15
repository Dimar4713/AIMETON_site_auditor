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
DADATA_PUBLIC_READY_ATTEMPTS="${DADATA_PUBLIC_READY_ATTEMPTS:-8}"
DADATA_FIND_PARTY_URL="https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"
DADATA_RUNTIME_CHANGED=0

log() {
  printf '%s %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

fail() {
  log "ERROR: $*"
  exit 1
}

retry_delay() {
  local attempt="$1"
  if (( attempt <= 4 )); then
    printf '%s' "$(( attempt * 2 ))"
  else
    printf '%s' '10'
  fi
}

[[ -d "$STACK_DIR" ]] || fail "Stack directory not found"
[[ -f "$STACK_DIR/docker-compose.yml" ]] || fail "docker-compose.yml not found"
[[ -f "$COMPOSE_OVERRIDE_FILE" ]] || fail "runtime compose override not found"
[[ -n "$DADATA_API" ]] || fail "DADATA_API is required"
[[ -n "$DADATA_SECRET" ]] || fail "DADATA_SECRET is required"
[[ "$DADATA_API" != *$'\n'* ]] || fail "DADATA_API contains a newline"
[[ "$DADATA_SECRET" != *$'\n'* ]] || fail "DADATA_SECRET contains a newline"
[[ "$DADATA_SMOKE_QUERY" =~ ^[0-9]{10,15}$ ]] || fail "DADATA_SMOKE_QUERY must be an INN or OGRN"
[[ "$DADATA_PUBLIC_READY_ATTEMPTS" =~ ^[1-9][0-9]*$ ]] || fail "DADATA_PUBLIC_READY_ATTEMPTS must be a positive integer"

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
if [[ -f "$RUNTIME_SECRETS_FILE" ]] && cmp -s "$tmp" "$RUNTIME_SECRETS_FILE"; then
  rm -f "$tmp"
  DADATA_RUNTIME_CHANGED=0
  log "DaData runtime credentials already match desired state; preserving running container"
else
  mv "$tmp" "$RUNTIME_SECRETS_FILE"
  DADATA_RUNTIME_CHANGED=1
  log "DaData runtime credentials changed and were installed without exposing values"
fi

if (( DADATA_RUNTIME_CHANGED == 1 )); then
  (
    cd "$STACK_DIR"
    docker compose \
      -f docker-compose.yml \
      -f "$COMPOSE_OVERRIDE_FILE" \
      up -d --force-recreate "$SERVICE"
  )
  log "Auditor recreated because DaData runtime material changed"
else
  log "Auditor recreate skipped because DaData runtime material is unchanged"
fi

for _ in $(seq 1 36); do
  status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$CONTAINER" 2>/dev/null || true)"
  [[ "$status" == "healthy" ]] && break
  [[ "$status" == "unhealthy" || "$status" == "exited" || "$status" == "dead" ]] && fail "container failed after DaData configuration"
  sleep 5
done

status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$CONTAINER" 2>/dev/null || true)"
[[ "$status" == "healthy" ]] || fail "container did not become healthy"
log "Container health is ready; waiting for public Stage route readiness"

health=""
for attempt in $(seq 1 "$DADATA_PUBLIC_READY_ATTEMPTS"); do
  if health="$(curl --fail --silent --show-error --max-time 30 "$STAGE_URL/api/missions/registry-mirror/dadata/health" 2>/dev/null)"; then
    break
  fi
  delay="$(retry_delay "$attempt")"
  log "DaData public health not ready (attempt $attempt/$DADATA_PUBLIC_READY_ATTEMPTS); retrying in ${delay}s"
  sleep "$delay"
done
[[ -n "$health" ]] || fail "DaData public health endpoint did not become ready"

python3 - "$health" <<'PY'
import json
import sys
payload = json.loads(sys.argv[1])
assert payload.get("provider") == "dadata", payload
assert payload.get("state") == "active", payload
assert payload.get("api_token_configured") is True, payload
assert payload.get("secret_configured") is True, payload
assert payload.get("secrets_exposed") is False, payload
print(json.dumps({"provider": "dadata", "state": "active", "secrets_exposed": False}, ensure_ascii=False, sort_keys=True))
PY

lookup=""
for attempt in $(seq 1 "$DADATA_PUBLIC_READY_ATTEMPTS"); do
  if lookup="$(curl --fail --silent --show-error --max-time 30 \
    -H 'Content-Type: application/json' \
    --data "{\"query\":\"$DADATA_SMOKE_QUERY\"}" \
    "$STAGE_URL/api/missions/registry-mirror/dadata/find-party" 2>/dev/null)"; then
    break
  fi
  delay="$(retry_delay "$attempt")"
  log "DaData live lookup not ready (attempt $attempt/$DADATA_PUBLIC_READY_ATTEMPTS); retrying in ${delay}s"
  sleep "$delay"
done

if [[ -z "$lookup" ]]; then
  diag_body="$(mktemp "$STACK_DIR/.dadata-app-diagnostic.XXXXXX")"
  app_http="$(curl --silent --show-error --max-time 30 -o "$diag_body" -w '%{http_code}' \
    -H 'Content-Type: application/json' \
    --data "{\"query\":\"$DADATA_SMOKE_QUERY\"}" \
    "$STAGE_URL/api/missions/registry-mirror/dadata/find-party" || true)"
  app_detail="$(python3 - "$diag_body" <<'PY'
import json
import sys
from pathlib import Path
try:
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except Exception:
    print("unavailable")
else:
    detail = payload.get("detail") if isinstance(payload, dict) else None
    print(detail if isinstance(detail, str) and len(detail) <= 120 else "unavailable")
PY
)"
  rm -f "$diag_body"
  direct_http="$(curl --silent --show-error --max-time 30 -o /dev/null -w '%{http_code}' \
    -H 'Accept: application/json' \
    -H 'Content-Type: application/json' \
    -H "Authorization: Token $DADATA_API" \
    --data "{\"query\":\"$DADATA_SMOKE_QUERY\"}" \
    "$DADATA_FIND_PARTY_URL" || true)"
  log "DaData lookup diagnostics: app_http=${app_http:-transport_error}; app_detail=${app_detail:-unavailable}; direct_provider_http=${direct_http:-transport_error}"
  fail "DaData live lookup endpoint did not become ready"
fi

python3 - "$lookup" <<'PY'
import json
import sys
payload = json.loads(sys.argv[1])
assert payload.get("provider") == "dadata", payload
assert payload.get("authority_verified") is False, payload
assert payload.get("state") in {"registry_mirror_verified", "unresolved", "conflicting"}, payload
records = payload.get("records") or []
if payload.get("state") != "unresolved":
    assert records, payload
    assert all(record.get("response_digest") for record in records), payload
print(json.dumps({
    "provider": payload.get("provider"),
    "state": payload.get("state"),
    "authority_verified": payload.get("authority_verified"),
    "records": len(records),
}, ensure_ascii=False, sort_keys=True))
PY

log "DaData stage live smoke passed"
