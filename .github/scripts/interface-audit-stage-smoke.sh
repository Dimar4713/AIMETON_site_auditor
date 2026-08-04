#!/usr/bin/env bash
set -Eeuo pipefail

: "${EXPECTED_SHA:?EXPECTED_SHA is required}"
: "${STACK_DIR:=/opt/aimeton/auditor-stack}"
: "${CONTAINER:=aimeton-auditor}"
: "${STAGE_URL:=https://stage-auditor.aimeton.ru}"
: "${OUT_DIR:=/tmp/ia-291-${GITHUB_RUN_ID:-local}}"

[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]
deployed="$(cat "$STACK_DIR/app-source-sha.txt")"
[[ "$deployed" == "$EXPECTED_SHA" ]]
status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$CONTAINER")"
[[ "$status" == healthy ]]

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

docker exec -i \
  -e STAGE_URL="$STAGE_URL" \
  -e IA_OUT=/tmp/ia291 \
  "$CONTAINER" python - <<'PY'
import asyncio
import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path

from app.capabilities.interface_audit.evidence_collector import collect_interface_evidence
from app.capabilities.interface_audit.quick_orchestrator import run_quick_audit

base = os.environ['STAGE_URL']
out = Path(os.environ['IA_OUT'])
shutil.rmtree(out, ignore_errors=True)
out.mkdir(parents=True, exist_ok=True)

async def main():
    manifests = {}
    results = {}
    for name, width, height in (
        ('desktop', 1440, 900),
        ('narrow', 390, 844),
    ):
        target = out / name
        manifest = await collect_interface_evidence(
            base,
            target,
            viewport_width=width,
            viewport_height=height,
            timeout_seconds=45,
        )
        # IA-03A proves exact-SHA collection and orchestration plumbing only.
        # Empty observations MUST NOT be presented as a quality sign-off.
        result = run_quick_audit(manifest, ())
        manifests[name] = asdict(manifest)
        results[name] = asdict(result)

    payload = {
        'schema_version': 'ia-03a-v1',
        'coverage': ['desktop', 'narrow'],
        'manifests': manifests,
        'quick_results': results,
        'release_verdict': 'inconclusive',
        'release_reason': 'domain reviewers are not connected in IA-03A; empty observations are not quality evidence',
        'next_step': 'connect deterministic Accessibility, Layout, Writing and Observability reviewers',
    }
    (out / 'self-audit.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding='utf-8',
    )

asyncio.run(main())
PY

docker cp "$CONTAINER:/tmp/ia291/." "$OUT_DIR/"
docker exec "$CONTAINER" rm -rf /tmp/ia291

python3 - "$OUT_DIR/self-audit.json" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
assert payload['release_verdict'] == 'inconclusive'
for viewport in ('desktop', 'narrow'):
    manifest = payload['manifests'][viewport]
    assert len(manifest['rule_pack_digest']) == 64
    assert manifest['rule_pack_version']
    refs = {item['ref'] for item in manifest['artifacts']}
    assert {'viewport.png', 'full-page.png', 'dom.html', 'metadata.json'} <= refs
    result = payload['quick_results'][viewport]
    assert result['rule_pack_digest'] == manifest['rule_pack_digest']
PY

{
  echo '## IA-03A — stage self-audit plumbing'
  echo
  echo "- workflow run: ${GITHUB_RUN_ID:-local}"
  echo "- timestamp UTC: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "- expected/deployed SHA: \`$EXPECTED_SHA\`"
  echo "- stage status: \`$status\`"
  echo '- desktop evidence manifest: ✅'
  echo '- narrow evidence manifest: ✅'
  echo '- exact rule-pack version/digest binding: ✅'
  echo '- collector → quick orchestrator plumbing: ✅'
  echo '- release verdict: **inconclusive**'
  echo '- reason: domain reviewers are intentionally not connected yet; empty observations are not treated as quality evidence'
  echo '- next: connect deterministic Accessibility, Layout, Writing and Observability reviewers'
} > "$OUT_DIR/evidence.md"
cat "$OUT_DIR/evidence.md" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
