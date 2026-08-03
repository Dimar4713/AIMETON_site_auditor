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
cleanup() {
  set +e
  if [[ -n "$token_hash" ]]; then
    docker exec -i -e TEST_USERNAME="$username" -e TEST_TOKEN_HASH="$token_hash" "$CONTAINER" python - <<'PY'
import os, sqlite3
from pathlib import Path
path = Path(os.environ.get('AIMETON_AUTH_DB', '/app/data/auth.sqlite3'))
if path.exists():
    with sqlite3.connect(path) as connection:
        row = connection.execute('SELECT id FROM users WHERE username = ?', (os.environ['TEST_USERNAME'],)).fetchone()
        if row:
            connection.execute('DELETE FROM sessions WHERE user_id = ?', (row[0],))
            connection.execute('DELETE FROM users WHERE id = ?', (row[0],))
        connection.execute('DELETE FROM sessions WHERE token_hash = ?', (os.environ['TEST_TOKEN_HASH'],))
PY
  fi
}
trap cleanup EXIT

token="$(docker exec -i -e TEST_USERNAME="$username" "$CONTAINER" python - <<'PY'
import os
from datetime import timedelta
from pathlib import Path
from app.admin_users import AdminSQLiteUserRepository
from app.auth import PasswordHasher, UserRole
from app.session_resolution import TypedLocalAuthProvider
path = Path(os.environ.get('AIMETON_AUTH_DB', '/app/data/auth.sqlite3'))
repo = AdminSQLiteUserRepository(path)
user = repo.create_user(os.environ['TEST_USERNAME'], PasswordHasher().hash('ui262-temporary-password'), UserRole.USER)
print(TypedLocalAuthProvider(repo, session_ttl=timedelta(minutes=15)).create_session(user).token)
PY
)"
[[ -n "$token" ]]
echo "::add-mask::$token"
token_hash="$(printf %s "$token" | sha256sum | awk '{print $1}')"

docker exec -i \
  -e STAGE_URL="$STAGE_URL" \
  -e SESSION_TOKEN="$token" \
  -e CAPTURE_DIR=/tmp/ui262-capture \
  "$CONTAINER" python - <<'PY'
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

base = os.environ['STAGE_URL']
token = os.environ['SESSION_TOKEN']
out = Path(os.environ['CAPTURE_DIR'])
out.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for name, viewport in [('desktop', {'width': 1440, 'height': 1000}), ('mobile', {'width': 390, 'height': 844})]:
        context = browser.new_context(viewport=viewport)
        page = context.new_page()
        page.goto(f'{base}/login', wait_until='networkidle')
        page.screenshot(path=str(out / f'login-{name}.png'), full_page=True)
        context.add_cookies([{
            'name': 'aimeton_session',
            'value': token,
            'domain': 'stage-auditor.aimeton.ru',
            'path': '/',
            'secure': True,
            'httpOnly': True,
            'sameSite': 'Lax',
        }])
        page.goto(f'{base}/workspace', wait_until='networkidle')
        assert '/workspace' in page.url
        body = page.locator('body').inner_text().lower()
        for forbidden in ('chain-of-thought', 'raw_prompt', 'provider_payload', 'access_token', 'secret_key'):
            assert forbidden not in body
        page.screenshot(path=str(out / f'workspace-{name}.png'), full_page=True)
        context.close()
    browser.close()
PY

docker cp "$CONTAINER:/tmp/ui262-capture/." "$OUT_DIR/"
docker exec "$CONTAINER" rm -rf /tmp/ui262-capture
{
  echo '## UI-262A stage visual capture'
  echo
  echo "- workflow run: ${GITHUB_RUN_ID:-local}"
  echo "- timestamp UTC: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '%s\n' "- exact deployed SHA: $EXPECTED_SHA"
  echo '- login desktop/mobile captured: ✅'
  echo '- authenticated workspace desktop/mobile captured: ✅'
  echo '- temporary credentials/session recorded in evidence: no'
  echo '- forbidden internal UI tokens absent: ✅'
  echo '- scope: login and workspace baseline only; mission/evidence/report remain for the next bounded slice'
} > "$OUT_DIR/evidence.md"
cat "$OUT_DIR/evidence.md" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
