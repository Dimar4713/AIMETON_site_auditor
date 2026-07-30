#!/usr/bin/env bash
set -Eeuo pipefail

STACK_DIR="${STACK_DIR:-/opt/aimeton/auditor-stack}"
STAGE_URL="${STAGE_URL:-https://stage-auditor.aimeton.ru}"
SERVICE="${SERVICE:-auditor}"
CONTAINER="${CONTAINER:-aimeton-auditor}"
RUNTIME_SECRETS_FILE="$STACK_DIR/.runtime-secrets.env"
COMPOSE_OVERRIDE_FILE="$STACK_DIR/docker-compose.runtime-secrets.yml"

: "${YANDEX_SEARCH_API_KEY:?YANDEX_SEARCH_API_KEY is required}"
: "${YANDEX_CLOUD_FOLDER_ID:?YANDEX_CLOUD_FOLDER_ID is required}"
YANDEX_SEARCH_TYPE="${YANDEX_SEARCH_TYPE:-SEARCH_TYPE_RU}"
YANDEX_SEARCH_FAMILY_MODE="${YANDEX_SEARCH_FAMILY_MODE:-FAMILY_MODE_MODERATE}"
YANDEX_SEARCH_RESULTS_PER_PAGE="${YANDEX_SEARCH_RESULTS_PER_PAGE:-10}"
YANDEX_SEARCH_SMOKE_QUERY="${YANDEX_SEARCH_SMOKE_QUERY:-AIMETON искусственный интеллект для бизнеса}"

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

cd "$STACK_DIR"
docker compose -f docker-compose.yml -f "$COMPOSE_OVERRIDE_FILE" up -d --force-recreate "$SERVICE"
for _ in $(seq 1 36); do
  status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$CONTAINER" 2>/dev/null || true)"
  [[ "$status" == healthy ]] && break
  [[ "$status" =~ ^(unhealthy|exited|dead)$ ]] && exit 1
  sleep 5
done

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

lookup="$(curl --fail --silent --show-error -H 'Content-Type: application/json' --data "{\"query\":\"$YANDEX_SEARCH_SMOKE_QUERY\"}" "$STAGE_URL/api/missions/search/yandex/web")"
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
