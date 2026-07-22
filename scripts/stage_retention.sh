#!/usr/bin/env bash
set -Eeuo pipefail

STACK_DIR="${STACK_DIR:-/opt/aimeton/auditor-stack}"
MODE="${MODE:-plan}"
KEEP_BACKUPS="${KEEP_BACKUPS:-3}"
KEEP_FAILED="${KEEP_FAILED:-2}"
CONFIRM="${CONFIRM:-}"
OUTPUT="${OUTPUT:-retention-evidence/retention.json}"
WARNING_PERCENT="${WARNING_PERCENT:-70}"
CRITICAL_PERCENT="${CRITICAL_PERCENT:-85}"
LOCK_FILE="${LOCK_FILE:-/tmp/aimeton-auditor-stage-retention.lock}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[[ "$MODE" == "plan" || "$MODE" == "apply" ]] || fail "MODE must be plan or apply"
[[ "$KEEP_BACKUPS" =~ ^[0-9]+$ ]] || fail "KEEP_BACKUPS must be an integer"
[[ "$KEEP_FAILED" =~ ^[0-9]+$ ]] || fail "KEEP_FAILED must be an integer"
[[ -d "$STACK_DIR" ]] || fail "Stack directory not found: $STACK_DIR"
[[ -d "$STACK_DIR/.deployments" ]] || fail "Deployment directory not found"
[[ -f "$STACK_DIR/app-source-sha.txt" ]] || fail "Current SHA marker not found"

exec 9>"$LOCK_FILE"
flock -n 9 || fail "Another retention or deployment operation is running"

DEPLOY_ROOT="$(readlink -f "$STACK_DIR/.deployments")"
CURRENT_SHA="$(tr -d '[:space:]' < "$STACK_DIR/app-source-sha.txt")"
mkdir -p "$(dirname "$OUTPUT")"

python3 - "$DEPLOY_ROOT" "$MODE" "$KEEP_BACKUPS" "$KEEP_FAILED" "$CURRENT_SHA" "$OUTPUT" "$WARNING_PERCENT" "$CRITICAL_PERCENT" "$CONFIRM" <<'PY'
from __future__ import annotations
import hashlib, json, os, shutil, sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1]).resolve()
mode = sys.argv[2]
keep_backups = int(sys.argv[3])
keep_failed = int(sys.argv[4])
current_sha = sys.argv[5]
output = Path(sys.argv[6])
warning = int(sys.argv[7])
critical = int(sys.argv[8])
confirm = sys.argv[9]

def entries(prefix: str):
    result = []
    for p in root.glob(prefix + '*'):
        if p.is_symlink() or not p.is_dir():
            continue
        resolved = p.resolve()
        if resolved.parent != root:
            continue
        st = p.stat()
        size = sum(f.stat().st_size for f in p.rglob('*') if f.is_file() and not f.is_symlink())
        result.append({'path': str(p), 'name': p.name, 'mtime': st.st_mtime, 'size_bytes': size, 'protected_marker': (p / '.retention-protected').exists()})
    return sorted(result, key=lambda x: x['mtime'], reverse=True)

backups = entries('app-source.backup.')
failed = entries('app-source.failed.') + entries('app-source.manual-failed.')
failed.sort(key=lambda x: x['mtime'], reverse=True)

for idx, item in enumerate(backups):
    item['protected'] = idx < keep_backups or item['protected_marker']
    item['reason'] = 'newest-backup' if idx < keep_backups else ('marker' if item['protected_marker'] else 'expired')
for idx, item in enumerate(failed):
    item['protected'] = idx < keep_failed or item['protected_marker']
    item['reason'] = 'newest-failed' if idx < keep_failed else ('marker' if item['protected_marker'] else 'expired')

candidates = [x for x in backups + failed if not x['protected']]
protected = [x for x in backups + failed if x['protected']]
usage = shutil.disk_usage(root)
used_percent = round((usage.used / usage.total) * 100, 1)
level = 'critical' if used_percent >= critical else ('warning' if used_percent >= warning else 'normal')
manifest = '\n'.join(sorted(x['name'] for x in candidates))
digest = hashlib.sha256(manifest.encode()).hexdigest()[:16]
expected = f'CLEANUP {len(candidates)} {digest}'

deleted = []
if mode == 'apply':
    if confirm != expected:
        raise SystemExit(f'Confirmation must equal: {expected}')
    for item in candidates:
        target = Path(item['path']).resolve()
        if target.parent != root or target.is_symlink() or not target.name.startswith('app-source.'):
            raise SystemExit(f'Unsafe retention target: {target}')
        shutil.rmtree(target)
        deleted.append(item['name'])

payload = {
    'timestamp_utc': datetime.now(timezone.utc).isoformat(),
    'mode': mode,
    'stack_dir': str(root.parent),
    'current_sha': current_sha,
    'policy': {'keep_backups': keep_backups, 'keep_failed': keep_failed, 'warning_percent': warning, 'critical_percent': critical},
    'disk': {'total_bytes': usage.total, 'used_bytes': usage.used, 'free_bytes': usage.free, 'used_percent': used_percent, 'level': level},
    'protected': protected,
    'candidates': candidates,
    'candidate_count': len(candidates),
    'candidate_bytes': sum(x['size_bytes'] for x in candidates),
    'confirmation': expected,
    'deleted': deleted,
    'openstack_images_deleted': False,
}
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
PY
