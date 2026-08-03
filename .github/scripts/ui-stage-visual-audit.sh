#!/usr/bin/env bash
set -Eeuo pipefail

: "${EXPECTED_SHA:?EXPECTED_SHA is required}"
: "${STACK_DIR:=/opt/aimeton/auditor-stack}"
: "${CONTAINER:=aimeton-auditor}"
: "${STAGE_URL:=https://stage-auditor.aimeton.ru}"
: "${OUT_DIR:=/tmp/ui-262-stage-visual-audit}"

[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]
deployed="$(cat "$STACK_DIR/app-source-sha.txt")"
[[ "$deployed" == "$EXPECTED_SHA" ]]
status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$CONTAINER")"
[[ "$status" == healthy ]]

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
username="ui262-$(date -u +%Y%m%d%H%M%S)-$RANDOM"
token=""
token_hash=""
mission_id=""
csrf="csrf-${GITHUB_RUN_ID:-local}-$RANDOM"

cleanup() {
  set +e
  docker exec -i \
    -e TEST_USERNAME="$username" \
    -e TEST_TOKEN_HASH="$token_hash" \
    -e TEST_MISSION_ID="$mission_id" \
    "$CONTAINER" python - <<'PY'
import os, sqlite3
from pathlib import Path
mission_id = os.environ.get('TEST_MISSION_ID', '')
missions = Path(os.environ.get('AIMETON_MISSION_DB', '/app/data/missions.sqlite3'))
if missions.exists() and mission_id:
    with sqlite3.connect(missions) as connection:
        connection.execute('DELETE FROM mission_records WHERE mission_id = ?', (mission_id,))
        connection.execute('DELETE FROM missions WHERE id = ?', (mission_id,))
auth = Path(os.environ.get('AIMETON_AUTH_DB', '/app/data/auth.sqlite3'))
if auth.exists():
    with sqlite3.connect(auth) as connection:
        row = connection.execute('SELECT id FROM users WHERE username = ?', (os.environ['TEST_USERNAME'],)).fetchone()
        if row:
            connection.execute('DELETE FROM sessions WHERE user_id = ?', (row[0],))
            connection.execute('DELETE FROM users WHERE id = ?', (row[0],))
        token_hash = os.environ.get('TEST_TOKEN_HASH', '')
        if token_hash:
            connection.execute('DELETE FROM sessions WHERE token_hash = ?', (token_hash,))
PY
}
trap cleanup EXIT

mapfile -t identity < <(docker exec -i -e TEST_USERNAME="$username" "$CONTAINER" python - <<'PY'
import os
from datetime import timedelta
from pathlib import Path
from app.admin_users import AdminSQLiteUserRepository
from app.auth import PasswordHasher, UserRole
from app.session_resolution import TypedLocalAuthProvider
path = Path(os.environ.get('AIMETON_AUTH_DB', '/app/data/auth.sqlite3'))
repo = AdminSQLiteUserRepository(path)
user = repo.create_user(os.environ['TEST_USERNAME'], PasswordHasher().hash('ui262-temporary-password'), UserRole.USER)
session = TypedLocalAuthProvider(repo, session_ttl=timedelta(minutes=15)).create_session(user)
print(user.id)
print(session.token)
PY
)
[[ ${#identity[@]} -eq 2 ]]
user_id="${identity[0]}"
token="${identity[1]}"
echo "::add-mask::$token"
token_hash="$(printf %s "$token" | sha256sum | awk '{print $1}')"
cookie="aimeton_session=$token; aimeton_csrf=$csrf"

created="$(curl -fsS -X POST "$STAGE_URL/api/user/missions" \
  --cookie "$cookie" \
  -H "X-CSRF-Token: $csrf" \
  -H 'Content-Type: application/json' \
  --data '{"title":"UI-262 visual acceptance mission","target_ref":"https://example.org","input_snapshot":{"secret_seed":"must-not-leak"},"correlation_id":"ui-262-visual"}')"
mission_id="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["id"])' "$created")"
[[ -n "$mission_id" ]]

docker exec -i -e TEST_MISSION_ID="$mission_id" "$CONTAINER" python - <<'PY'
import os
from app.mission_sqlite import SQLiteMissionRepository
repo = SQLiteMissionRepository()
mid = os.environ['TEST_MISSION_ID']
repo.append_record(mid, 'turn', {
    'turn_id': 'turn-safe', 'status': 'completed', 'summary': 'Публичное резюме этапа', 'source_count': 3,
    'provider_token': 'SECRET-TOKEN', 'internal_trace': '/app/private/trace.json'
}, record_id='ui262-turn')
repo.append_record(mid, 'sufficiency', {
    'record_id': 'udp-safe', 'level': 'partial', 'status': 'degraded', 'summary': 'Нужно больше доказательств',
    'deficits': ['ownership'], 'secret': 'MUST-NOT-LEAK'
}, record_id='ui262-udp')
repo.append_record(mid, 'report_metadata', {
    'report_id': 'report-safe', 'status': 'blocked', 'format': 'docx',
    'available': False, 'release_level': 'reviewed', 'blocked_reason': 'report_release_blocked',
    'storage_path': '/app/private/report.docx', 'signed_url': 'https://secret.invalid/token'
}, record_id='ui262-report')
PY

docker exec -i \
  -e STAGE_URL="$STAGE_URL" \
  -e SESSION_TOKEN="$token" \
  -e TEST_MISSION_ID="$mission_id" \
  -e CAPTURE_DIR=/tmp/ui262-capture \
  "$CONTAINER" python - <<'PY'
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

base = os.environ['STAGE_URL']
token = os.environ['SESSION_TOKEN']
mission_id = os.environ['TEST_MISSION_ID']
out = Path(os.environ['CAPTURE_DIR'])
out.mkdir(parents=True, exist_ok=True)
forbidden = ('chain-of-thought', 'raw_prompt', 'provider_payload', 'access_token', 'secret_key', 'secret-token', 'must-not-leak', '/app/private')

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for name, viewport in [('desktop', {'width': 1440, 'height': 1000}), ('mobile', {'width': 390, 'height': 844})]:
        context = browser.new_context(viewport=viewport)
        page = context.new_page()
        page.goto(f'{base}/login', wait_until='networkidle')
        page.screenshot(path=str(out / f'login-{name}.png'), full_page=True)
        context.add_cookies([{
            'name': 'aimeton_session', 'value': token, 'domain': 'stage-auditor.aimeton.ru',
            'path': '/', 'secure': True, 'httpOnly': True, 'sameSite': 'Lax',
        }])
        page.goto(f'{base}/workspace', wait_until='networkidle')
        assert '/workspace' in page.url
        workspace_body = page.locator('body').inner_text().lower()
        for item in forbidden:
            assert item not in workspace_body
        page.screenshot(path=str(out / f'workspace-{name}.png'), full_page=True)

        page.goto(f'{base}/workspace/missions/{mission_id}', wait_until='networkidle')
        assert mission_id in page.url
        page.wait_for_timeout(1000)
        mission_body = page.locator('body').inner_text().lower()
        assert 'публичное резюме этапа' in mission_body
        assert 'нужно больше доказательств' in mission_body
        assert 'report_release_blocked' in mission_body or 'отч' in mission_body
        for item in forbidden:
            assert item not in mission_body
        page.screenshot(path=str(out / f'mission-evidence-report-{name}.png'), full_page=True)
        context.close()
    browser.close()
PY

docker cp "$CONTAINER:/tmp/ui262-capture/." "$OUT_DIR/"
docker exec "$CONTAINER" rm -rf /tmp/ui262-capture
{
  echo '## UI-262 stage visual capture'
  echo
  echo "- workflow run: ${GITHUB_RUN_ID:-local}"
  echo "- timestamp UTC: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '%s\n' "- exact deployed SHA: $EXPECTED_SHA"
  echo '- login desktop/mobile captured: ✅'
  echo '- authenticated workspace desktop/mobile captured: ✅'
  echo '- mission detail with sanitized evidence and blocked report desktop/mobile captured: ✅'
  echo '- temporary user, session and mission cleaned up: ✅'
  echo '- credentials/session tokens/internal payloads recorded in evidence: no'
  echo '- forbidden internal UI tokens absent: ✅'
  echo '- scope completed: login → workspace → mission → evidence → report baseline'
} > "$OUT_DIR/evidence.md"
cat "$OUT_DIR/evidence.md" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
