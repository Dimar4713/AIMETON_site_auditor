#!/usr/bin/env python3
"""Sanitized, read-only observability collector for AIMETON stage."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def run(cmd: list[str], timeout: int = 15) -> tuple[int, str]:
    try:
        cp = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
        return cp.returncode, (cp.stdout or cp.stderr).strip()
    except Exception as exc:  # evidence must survive partial failures
        return 127, type(exc).__name__


def http_probe(url: str, method: str = "GET", data: bytes | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    start = time.monotonic()
    request = urllib.request.Request(url, method=method, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read(65536)
            return {"ok": True, "status": response.status, "latency_ms": round((time.monotonic() - start) * 1000), "bytes": len(body)}
    except urllib.error.HTTPError as exc:
        # Redirects can be intentionally disabled by the caller; status remains useful.
        return {"ok": 200 <= exc.code < 400, "status": exc.code, "latency_ms": round((time.monotonic() - start) * 1000), "bytes": 0}
    except Exception as exc:
        return {"ok": False, "status": None, "latency_ms": round((time.monotonic() - start) * 1000), "error": type(exc).__name__}


def meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        values[key] = int(value.strip().split()[0]) * 1024
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--stage-url", default=os.getenv("STAGE_URL", "https://stage-auditor.aimeton.ru"))
    parser.add_argument("--disk-warning", type=int, default=int(os.getenv("OBS_DISK_WARNING", "70")))
    parser.add_argument("--disk-critical", type=int, default=int(os.getenv("OBS_DISK_CRITICAL", "85")))
    parser.add_argument("--memory-warning", type=int, default=int(os.getenv("OBS_MEMORY_WARNING", "85")))
    parser.add_argument("--swap-warning", type=int, default=int(os.getenv("OBS_SWAP_WARNING", "50")))
    parser.add_argument("--latency-warning-ms", type=int, default=int(os.getenv("OBS_LATENCY_WARNING_MS", "3000")))
    args = parser.parse_args()

    started = time.monotonic()
    alerts: list[dict[str, Any]] = []
    disk = shutil.disk_usage("/")
    disk_pct = round(disk.used / disk.total * 100, 1)
    inode_rc, inode_out = run(["df", "-Pi", "/"])
    inode_pct = None
    if inode_rc == 0 and len(inode_out.splitlines()) >= 2:
        try:
            inode_pct = float(inode_out.splitlines()[-1].split()[4].rstrip("%"))
        except Exception:
            pass

    memory = meminfo()
    mem_total = memory.get("MemTotal", 0)
    mem_available = memory.get("MemAvailable", 0)
    mem_pct = round((mem_total - mem_available) / mem_total * 100, 1) if mem_total else None
    swap_total = memory.get("SwapTotal", 0)
    swap_free = memory.get("SwapFree", 0)
    swap_pct = round((swap_total - swap_free) / swap_total * 100, 1) if swap_total else 0.0

    if disk_pct >= args.disk_critical:
        alerts.append({"severity": "critical", "signal": "disk_usage", "value": disk_pct})
    elif disk_pct >= args.disk_warning:
        alerts.append({"severity": "warning", "signal": "disk_usage", "value": disk_pct})
    if inode_pct is not None and inode_pct >= args.disk_warning:
        alerts.append({"severity": "critical" if inode_pct >= args.disk_critical else "warning", "signal": "inode_usage", "value": inode_pct})
    if mem_pct is not None and mem_pct >= args.memory_warning:
        alerts.append({"severity": "warning", "signal": "memory_usage", "value": mem_pct})
    if swap_pct >= args.swap_warning:
        alerts.append({"severity": "warning", "signal": "swap_usage", "value": swap_pct})

    rc, docker_json = run(["docker", "ps", "-a", "--format", "{{json .}}"])
    containers: list[dict[str, Any]] = []
    if rc == 0:
        for line in docker_json.splitlines():
            try:
                item = json.loads(line)
                name = item.get("Names")
                inspect_rc, inspect_out = run(["docker", "inspect", name, "--format", "{{json .State}}"])
                state = json.loads(inspect_out) if inspect_rc == 0 else {}
                health = (state.get("Health") or {}).get("Status")
                restarts_rc, restarts_out = run(["docker", "inspect", name, "--format", "{{.RestartCount}}"])
                restarts = int(restarts_out) if restarts_rc == 0 and restarts_out.isdigit() else None
                sanitized = {"name": name, "status": state.get("Status"), "health": health, "restarts": restarts}
                containers.append(sanitized)
                if state.get("Status") != "running" or health == "unhealthy":
                    alerts.append({"severity": "critical", "signal": "container", "name": name, "value": health or state.get("Status")})
                elif restarts and restarts > 0:
                    alerts.append({"severity": "warning", "signal": "container_restarts", "name": name, "value": restarts})
            except Exception:
                continue
    else:
        alerts.append({"severity": "critical", "signal": "docker", "value": "unavailable"})

    health = http_probe(args.stage_url.rstrip("/") + "/api/health")
    mcp_redirect = http_probe(args.stage_url.rstrip("/") + "/mcp")
    mcp_payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "stage-observability", "version": "1.0"}}}).encode()
    mcp_initialize = http_probe(args.stage_url.rstrip("/") + "/mcp/", method="POST", data=mcp_payload, headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    for name, probe in (("api_health", health), ("mcp_redirect", mcp_redirect), ("mcp_initialize", mcp_initialize)):
        expected = probe.get("status") in ({200} if name != "mcp_redirect" else {200, 307})
        if not probe.get("ok") or not expected:
            alerts.append({"severity": "critical", "signal": name, "value": probe.get("status")})
        elif (probe.get("latency_ms") or 0) >= args.latency_warning_ms:
            alerts.append({"severity": "warning", "signal": name + "_latency_ms", "value": probe.get("latency_ms")})

    service_rc, service_out = run(["systemctl", "list-units", "--type=service", "--state=running", "--no-legend", "actions.runner.*"])
    runner_services = sorted(line.split()[0] for line in service_out.splitlines() if "actions.runner." in line) if service_rc == 0 else []
    if len(runner_services) < 2:
        alerts.append({"severity": "warning", "signal": "runner_services", "value": len(runner_services)})

    load1, load5, load15 = os.getloadavg()
    cpu_count = os.cpu_count() or 1
    if load5 > cpu_count * 1.5:
        alerts.append({"severity": "warning", "signal": "load5", "value": round(load5, 2)})

    severity = "critical" if any(a["severity"] == "critical" for a in alerts) else "warning" if alerts else "ok"
    payload = {
        "schema": "aimeton.stage.observability.v1",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "severity": severity,
        "host": {
            "cpu_count": cpu_count,
            "load": [round(load1, 2), round(load5, 2), round(load15, 2)],
            "memory_used_pct": mem_pct,
            "swap_used_pct": swap_pct,
            "disk_used_pct": disk_pct,
            "inode_used_pct": inode_pct,
        },
        "containers": sorted(containers, key=lambda x: x.get("name") or ""),
        "probes": {"api_health": health, "mcp_redirect": mcp_redirect, "mcp_initialize": mcp_initialize},
        "runner_services": runner_services,
        "alerts": alerts,
        "collector_duration_ms": round((time.monotonic() - started) * 1000),
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"severity": severity, "alerts": len(alerts), "duration_ms": payload["collector_duration_ms"]}, sort_keys=True))
    return 2 if severity == "critical" else 0


if __name__ == "__main__":
    raise SystemExit(main())
