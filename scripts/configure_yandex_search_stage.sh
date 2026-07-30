#!/usr/bin/env bash
set -Eeuo pipefail

STACK_DIR="${STACK_DIR:-/opt/aimeton/auditor-stack}"
SOURCE_DIR="${SOURCE_DIR:-${GITHUB_WORKSPACE:-$PWD}}"
STAGE_URL="${STAGE_URL:-https://stage-auditor.aimeton.ru}"
SERVICE="${SERVICE:-auditor}"
CONTAINER="${CONTAINER:-aimeton-auditor}"
RUNTIME_SECRETS_FILE="$STACK_DIR/.runtime-secrets.env"
COMPOSE_OVERRIDE_FILE="$STACK_DIR/docker-compose.runtime-secrets.yml"
CURRENT_DIR="$STACK_DIR/app-source"
DEPLOY_ROOT="$STACK_DIR/.deployments"
DEPLOY_SHA="$(git -C "$SOURCE_DIR" rev-parse HEAD)"
STAGING_DIR="$DEPLOY_ROOT/app-source.yandex.$DEPLOY_SHA.$$.staging"
BACKUP_DIR="$DEPLOY_ROOT/app-source.backup.$(date -u +'%Y%m%dT%H%M%SZ').${DEPLOY_SHA:0:12}"

: "${YANDEX_SEARCH_API_KEY:?YANDEX_SEARCH_API_KEY is required}"
: "${YANDEX_CLOUD_FOLDER_ID:?YANDEX_CLOUD_FOLDER_ID is required}"
YANDEX_SEARCH_TYPE="${YANDEX_SEARCH_TYPE:-SEARCH_TYPE_RU}"
YANDEX_SEARCH_FAMILY_MODE="${YANDEX_SEARCH_FAMILY_MODE:-FAMILY_MODE_MODERATE}"
YANDEX_SEARCH_RESULTS_PER_PAGE="${YANDEX_SEARCH_RESULTS_PER_PAGE:-10}"
YANDEX_SEARCH_SMOKE_QUERY="${YANDEX_SEARCH_SMOKE_QUERY:-AIMETON искусственный интеллект для бизнеса}"

mkdir -p "$DEPLOY_ROOT"
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
printf '%s\n' "$DEPLOY_SHA" > "$STAGING_DIR/.aimeton-deploy-sha"
[[ -f "$STAGING_DIR/app/main.py" ]]
[[ -f "$STAGING_DIR/requirements.txt" ]]

umask 077
tmp="$(mktemp "$STACK_DIR/.runtime-secrets.yandex.XXXXXX")"
python3 - "$RUNTIME_SECRETS_FILE" "$tmp" <<'PY'
from pathlib import Path
import os, sys
source, target = map(Path, sys.argv[1:])
names = [
    "YANDEX_SEARCH_API_KEY", "YANDEX_CLOUD_FOLDER_ID", "YANDEX_SEARCH_TYPE",
    "YANDEX_SEARCH_FAMILY_MODE", "YANDEX_SEARCH_RESULTS_PER_PAGE",
]
kept = []
if source.exists():
    kept = [line for line in source.read_text().splitlines() if not any(line.startswith(name + "=") for name in names)]
kept.extend(f"{name}={os.environ[name]}" for name in names)
target.write_text("\n".join(kept) + "\n")
PY
chmod 600 "$tmp"
mv "$tmp" "$RUNTIME_SECRETS_FILE"

if [[ -d "$CURRENT_DIR" ]]; then
  mv "$CURRENT_DIR" "$BACKUP_DIR"
fi
mv "$STAGING_DIR" "$CURRENT_DIR"
printf '%s\n' "$DEPLOY_SHA" > "$STACK_DIR/app-source-sha.txt"

cd "$STACK_DIR"
docker compose -f docker-compose.yml -f "$COMPOSE_OVERRIDE_FILE" build "$SERVICE"
docker compose -f docker-compose.yml -f "$COMPOSE_OVERRIDE_FILE" up -d --force-recreate "$SERVICE"
for _ in $(seq 1 36); do
  status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$CONTAINER" 2>/dev/null || true)"
  [[ "$status" == healthy ]] && break
  [[ "$status" =~ ^(unhealthy|exited|dead)$ ]] && exit 1
  sleep 5
done
[[ "$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$CONTAINER")" == healthy ]]

health="$(curl --fail --silent --show-error "$STAGE_URL/api/missions/search/yandex/health")"
python3 - "$health" <<'PY'
import json, sys
p = json.loads(sys.argv[1])
assert p["provider"] == "yandex_web_search", p
assert p["state"] == "active", p
assert p["api_key_configured"] is True, p
assert p["folder_id_configured"] is True, p
assert p["secrets_exposed"] is False, p
PY

request_file="$(mktemp)"
response_file="$(mktemp)"
python3 - "$request_file" "$YANDEX_SEARCH_SMOKE_QUERY" <<'PY'
import json, sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({"query": sys.argv[2]}, ensure_ascii=False))
PY
http_code="$(curl --silent --show-error -H 'Content-Type: application/json' --data-binary "@$request_file" -o "$response_file" -w '%{http_code}' "$STAGE_URL/api/missions/search/yandex/web")"
lookup="$(cat "$response_file")"
rm -f "$request_file" "$response_file"
if [[ "$http_code" != 2* ]]; then
  echo "Yandex Search smoke failed: stage_http_status=$http_code"
  python3 - "$lookup" <<'PY'
import json, sys
raw = sys.argv[1]
try:
    payload = json.loads(raw)
except Exception:
    print("stage_response=non_json")
else:
    detail = payload.get("detail")
    if isinstance(detail, str):
        print("stage_detail=" + detail[:1000])
    else:
        print("stage_response_keys=" + ",".join(sorted(payload.keys())))
PY
  echo "container_log_tail_begin"
  docker logs --tail 160 "$CONTAINER" 2>&1 | sed -E 's/(Api-Key|Bearer|Token) [A-Za-z0-9._~+\/-]+/\1 [REDACTED]/g'
  echo "container_log_tail_end"
  exit 1
fi
python3 - "$lookup" <<'PY'
import json, sys
p = json.loads(sys.argv[1])
assert p["provider"] == "yandex_web_search", p
assert p["state"] in {"resolved", "unresolved"}, p
assert p["authority_verified"] is False, p
if p["state"] == "resolved":
    assert p["records"], p
    assert all(r.get("response_digest") for r in p["records"]), p
print(json.dumps({"provider": p["provider"], "state": p["state"], "records": len(p["records"])}, ensure_ascii=False))
PY

echo "Yandex Search stage live smoke passed"
