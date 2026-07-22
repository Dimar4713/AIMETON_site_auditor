#!/usr/bin/env bash
set -Eeuo pipefail

OUTPUT="${1:-server-audit.md}"
STACK_DIR="${STACK_DIR:-/opt/aimeton/auditor-stack}"
STAGE_URL="${STAGE_URL:-https://stage-auditor.aimeton.ru}"

safe_cmd() {
  local title="$1"
  shift
  {
    echo "### ${title}"
    echo '```text'
    "$@" 2>&1 || true
    echo '```'
    echo
  } >> "$OUTPUT"
}

: > "$OUTPUT"
{
  echo "# Sanitized server architecture audit"
  echo
  echo "- timestamp_utc: $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  echo "- runner: self-hosted / Linux / X64 / stage / auditor"
  echo "- mode: read-only"
  echo
  echo "> Secrets, process environments, IP addresses, credentials and user data are intentionally excluded."
  echo
} >> "$OUTPUT"

safe_cmd "Operating system" bash -lc 'source /etc/os-release 2>/dev/null || true; printf "os=%s %s\n" "${NAME:-unknown}" "${VERSION_ID:-unknown}"; uname -srmo'
safe_cmd "CPU" bash -lc 'printf "logical_cpus=%s\n" "$(nproc 2>/dev/null || echo unknown)"; lscpu 2>/dev/null | grep -E "^(Architecture|CPU\(s\)|Model name|Thread|Core|Socket|Virtualization):" || true'
safe_cmd "Memory" bash -lc 'free -h'
safe_cmd "Filesystems" bash -lc 'df -hT -x tmpfs -x devtmpfs | sed -E "s#(/home/[^/ ]+|/root)(/[^ ]*)?#<home>#g"'
safe_cmd "Docker" bash -lc 'docker version --format "engine={{.Server.Version}}" 2>/dev/null || echo "engine=unavailable"; docker compose version 2>/dev/null || true; docker ps --format "container={{.Names}} image={{.Image}} status={{.Status}}" 2>/dev/null || true'
safe_cmd "AIMETON stack layout" bash -lc 'd="/opt/aimeton/auditor-stack"; if [[ -d "$d" ]]; then printf "stack_present=yes\n"; find "$d" -maxdepth 2 -mindepth 1 -printf "%y %P\n" 2>/dev/null | grep -Ev "(^|/)(\.env|secrets?|credentials?|private|data)(/|$)" | head -200; else printf "stack_present=no\n"; fi'
safe_cmd "Self-hosted runner services" bash -lc 'systemctl list-units --type=service --all --no-legend 2>/dev/null | awk "/actions\.runner|github.*runner/ {print \$1, \$3, \$4}" || true'
safe_cmd "Key platform services" bash -lc 'for s in docker containerd nginx caddy; do printf "%s=%s\n" "$s" "$(systemctl is-active "$s" 2>/dev/null || true)"; done'
safe_cmd "Application health" bash -lc 'printf "health_http="; curl -sS -o /tmp/aimeton-health-body -w "%{http_code}\n" --max-time 15 https://stage-auditor.aimeton.ru/api/health || true; python3 - <<"PY"
import json
from pathlib import Path
p=Path("/tmp/aimeton-health-body")
if p.exists():
    try:
        d=json.loads(p.read_text(encoding="utf-8"))
        print("health_version=" + str(d.get("version", "unknown")))
        print("health_status=" + str(d.get("status", d.get("ok", "unknown"))))
    except Exception:
        print("health_body=non-json")
PY
printf "mcp_redirect_http="; curl -sS -o /dev/null -w "%{http_code}\n" --max-time 15 --max-redirs 0 https://stage-auditor.aimeton.ru/mcp || true'

{
  echo "## Preliminary architecture interpretation"
  echo
  echo "- Control plane: GitHub Issues/Projects/Actions."
  echo "- Execution plane: self-hosted runner inside the stage Ubuntu VM."
  echo "- Application plane: Docker Compose stack under /opt/aimeton/auditor-stack."
  echo "- Infrastructure plane: immers.cloud OpenStack APIs (Keystone/Nova/Neutron/Cinder/Glance)."
  echo "- External interface plane: HTTPS UI/REST/MCP at stage-auditor.aimeton.ru."
  echo
  echo "This report is evidence only; it performs no package, service, firewall, Docker, volume or application mutation."
} >> "$OUTPUT"
