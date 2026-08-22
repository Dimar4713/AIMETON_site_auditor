#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any
import urllib.error
import urllib.request

BASE_URL = "https://routerai.ru/api/v1"
MODELS = [
    "z-ai/glm-5.2",
    "deepseek/deepseek-v4-pro-0813",
    "qwen/qwen3.7-plus",
    "moonshotai/kimi-k2.6",
    "openai/gpt-5.6-sol",
]
SCENARIO_REL = Path("Docs/Research/Benchmarks/ACCB/public_dev/ACCB-DEV-001.scenario.json")
GOLD_REL = Path("Docs/Research/Benchmarks/ACCB/public_dev/ACCB-DEV-001.gold-ledger.json")
TRACE_SCHEMA_REL = Path("Docs/Research/Benchmarks/ACCB/candidate_trace.schema.json")
SCORER_REL = Path("scripts/score_accb_trace.py")
CONTEXT_ASSEMBLY_VERSION = "accb-routerai-live-low-v0.1"
MAX_OUTPUT_TOKENS = 1200
TARGET_VISIBLE_CHARS = 220_000


class IntegrationError(RuntimeError):
    pass


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise IntegrationError(f"missing required environment variable: {name}")
    return value


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise IntegrationError(f"expected JSON object: {path}")
    return value


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def http_json(url: str, *, payload: dict[str, Any] | None = None, api_key: str | None = None, timeout: int = 180) -> tuple[int, dict[str, Any], float]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json"}
    method = "GET"
    if payload is not None:
        method = "POST"
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise IntegrationError(f"non-object JSON from {url}")
            return int(response.status), body, time.monotonic() - started
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        raise IntegrationError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise IntegrationError(f"transport failure from {url}: {exc}") from exc


def usage(body: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    data = body.get("usage")
    if not isinstance(data, dict):
        return None, None, None

    def integer(name: str) -> int | None:
        value = data.get(name)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None

    return integer("prompt_tokens"), integer("completion_tokens"), integer("total_tokens")


def response_text(body: dict[str, Any]) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise IntegrationError("RouterAI response has no choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise IntegrationError("RouterAI first choice is not an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise IntegrationError("RouterAI choice has no message object")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise IntegrationError("RouterAI response content is empty")
    return content


def extract_json_object(text: str) -> dict[str, Any]:
    clean = text.strip()
    clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.I)
    clean = re.sub(r"\s*```$", "", clean)
    try:
        value = json.loads(clean)
    except json.JSONDecodeError:
        start = clean.find("{")
        end = clean.rfind("}")
        if start < 0 or end <= start:
            raise IntegrationError("model output does not contain a JSON object")
        value = json.loads(clean[start : end + 1])
    if not isinstance(value, dict):
        raise IntegrationError("model output JSON is not an object")
    return value


def endpoint_census(model_id: str) -> dict[str, Any]:
    author, slug = model_id.split("/", 1)
    _, body, _ = http_json(f"{BASE_URL}/models/{author}/{slug}/endpoints", timeout=60)
    data = body.get("data")
    if not isinstance(data, dict):
        raise IntegrationError(f"endpoint census missing data for {model_id}")
    endpoints = data.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        raise IntegrationError(f"endpoint census empty for {model_id}")
    candidates: list[dict[str, Any]] = []
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue
        apis = endpoint.get("supported_apis") or []
        context_length = endpoint.get("context_length")
        status = endpoint.get("status")
        if "chat" not in apis:
            continue
        if not isinstance(context_length, int) or context_length < 128_000:
            continue
        if isinstance(status, int) and status < 0:
            continue
        candidates.append(endpoint)
    if not candidates:
        raise IntegrationError(f"no healthy chat endpoint >=128K for {model_id}")
    chosen = candidates[0]
    pricing = chosen.get("pricing") if isinstance(chosen.get("pricing"), dict) else {}
    variable = chosen.get("variable_pricings") if isinstance(chosen.get("variable_pricings"), list) else []
    return {
        "model_id": model_id,
        "name": str(chosen.get("name") or ""),
        "provider_name": str(chosen.get("provider_name") or ""),
        "tag": str(chosen.get("tag") or ""),
        "country": chosen.get("country"),
        "context_length": chosen.get("context_length"),
        "max_prompt_tokens": chosen.get("max_prompt_tokens"),
        "max_completion_tokens": chosen.get("max_completion_tokens"),
        "quantization": chosen.get("quantization"),
        "pricing": {
            "prompt": pricing.get("prompt"),
            "completion": pricing.get("completion"),
        },
        "variable_pricings": variable,
        "supported_parameters": chosen.get("supported_parameters") or [],
        "supported_apis": chosen.get("supported_apis") or [],
    }


def rub_per_token(endpoint: dict[str, Any], key: str, prompt_tokens: int) -> float:
    pricing = endpoint.get("pricing") or {}
    raw = pricing.get(key)
    base = float(raw) if isinstance(raw, (int, float)) else 0.0
    if key != "prompt":
        return base
    result = base
    for row in endpoint.get("variable_pricings") or []:
        if not isinstance(row, dict) or row.get("type") != "prompt-threshold":
            continue
        threshold = row.get("threshold")
        price = row.get("prompt")
        if isinstance(threshold, int) and prompt_tokens > threshold and isinstance(price, (int, float)):
            result = float(price)
    return result


def estimated_cost(endpoint: dict[str, Any], prompt_tokens: int, completion_tokens: int) -> float:
    return prompt_tokens * rub_per_token(endpoint, "prompt", prompt_tokens) + completion_tokens * rub_per_token(endpoint, "completion", prompt_tokens)


def canonical_task(scenario: dict[str, Any]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for event in scenario.get("events") or []:
        if not isinstance(event, dict):
            continue
        events.append({
            "event_id": event.get("event_id"),
            "kind": event.get("kind"),
            "claim_id": event.get("expected_state_delta_ref"),
            "payload": event.get("payload"),
        })
    return {
        "scenario_id": scenario.get("scenario_id"),
        "scenario_version": scenario.get("scenario_version"),
        "layer": scenario.get("layer"),
        "mission": scenario.get("mission"),
        "events": events,
        "faults": scenario.get("faults") or [],
    }


def filler_segment(chars: int, segment: int) -> str:
    line = (
        "ARCHIVE_BACKGROUND segment={segment} row={row:05d}: generic engineering log about inventory, "
        "maintenance windows, documentation formatting, routine build metadata, and non-authoritative historical notes.\n"
    )
    out: list[str] = []
    row = 0
    total = 0
    while total < chars:
        text = line.format(segment=segment, row=row)
        out.append(text)
        total += len(text)
        row += 1
    return "".join(out)[:chars]


def build_live_messages(scenario: dict[str, Any], trace_schema: dict[str, Any]) -> tuple[list[dict[str, str]], str, str]:
    task = canonical_task(scenario)
    events = task.pop("events")
    action_vocab = sorted(str(x) for x in (scenario.get("evaluator_spec") or {}).get("required_action_subsequence") or [])
    event_groups = [events[:2], events[2:4], events[4:]]
    fixed_head = (
        "ACCB LIVE CALIBRATION. Treat the mission and event stream as authoritative according to their stated kind and chronology. "
        "A distractor or stale historical note must not override newer runtime/tool evidence. Do not perform external actions. "
        "At the end emit one JSON candidate trace only.\n\n"
        "TASK HEADER:\n" + json.dumps(task, ensure_ascii=False, sort_keys=True) + "\n\n"
    )
    output_contract = (
        "\nOUTPUT CONTRACT\n"
        "Return one JSON object matching this field contract. Use claim_id values from the event stream. "
        "For action_trace choose identifiers only from ACTION_VOCABULARY and order them as the actions should occur. "
        "Do not include Markdown or chain-of-thought.\n"
        f"ACTION_VOCABULARY={json.dumps(action_vocab, ensure_ascii=False)}\n"
        f"CANDIDATE_TRACE_SCHEMA={json.dumps(trace_schema, ensure_ascii=False, sort_keys=True)}\n"
    )
    event_texts = [
        "EVENT_STREAM_PART\n" + json.dumps(group, ensure_ascii=False, sort_keys=True) + "\n"
        for group in event_groups
    ]
    fixed_chars = len(fixed_head) + len(output_contract) + sum(len(x) for x in event_texts)
    filler_total = max(TARGET_VISIBLE_CHARS - fixed_chars, 12_000)
    shares = [0.20, 0.36, 0.44]
    filler = [filler_segment(int(filler_total * share), i + 1) for i, share in enumerate(shares)]
    user = fixed_head
    for idx in range(3):
        user += filler[idx] + "\n" + event_texts[idx]
    user += output_contract
    system = "You are an ACCB benchmark subject. Follow the supplied mission state. Return only the requested JSON object; do not reveal private reasoning."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}], system, user


def build_task_probe_messages(scenario: dict[str, Any]) -> list[dict[str, str]]:
    task = json.dumps(canonical_task(scenario), ensure_ascii=False, sort_keys=True)
    return [
        {"role": "system", "content": "ACCB tokenizer/task-payload measurement probe. Reply only OK."},
        {"role": "user", "content": task},
    ]


def chat(api_key: str, model_id: str, endpoint: dict[str, Any], messages: list[dict[str, str]], *, max_tokens: int, temperature: float = 0.0, timeout: int = 240) -> tuple[dict[str, Any], float]:
    provider_tag = str(endpoint.get("tag") or "").strip()
    payload: dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "provider": {"allow_fallbacks": False},
    }
    if provider_tag:
        payload["provider"]["only"] = [provider_tag]
    _, body, elapsed = http_json(f"{BASE_URL}/chat/completions", payload=payload, api_key=api_key, timeout=timeout)
    return body, elapsed


def safe_provider_metadata(body: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("model", "provider", "system_fingerprint", "id"):
        value = body.get(key)
        if isinstance(value, (str, int, float)):
            result[key] = value
    return result


def main() -> int:
    api_key = required_env("ROUTERAI_API_KEY")
    architecture_root = Path(required_env("ACCB_ARCHITECTURE_ROOT"))
    result_path = Path(required_env("ACCB_RESULT_PATH"))
    max_budget_rub = float(required_env("ACCB_MAX_BUDGET_RUB"))
    architecture_sha = required_env("ACCB_ARCHITECTURE_SHA")
    if not (0 < max_budget_rub <= 100.0):
        raise IntegrationError("ACCB_MAX_BUDGET_RUB must be in (0, 100] for the first bounded batch")
    if not re.fullmatch(r"[0-9a-f]{40}", architecture_sha):
        raise IntegrationError("ACCB_ARCHITECTURE_SHA must be an exact 40-char SHA")

    scenario_path = architecture_root / SCENARIO_REL
    gold_path = architecture_root / GOLD_REL
    trace_schema_path = architecture_root / TRACE_SCHEMA_REL
    scorer_path = architecture_root / SCORER_REL
    scenario = read_json(scenario_path)
    gold = read_json(gold_path)
    trace_schema = read_json(trace_schema_path)
    gold_version = str(gold.get("ledger_version") or "unknown")

    census: dict[str, Any] = {}
    for model_id in MODELS:
        census[model_id] = endpoint_census(model_id)

    spent_estimate = 0.0
    model_rows: list[dict[str, Any]] = []
    integration_errors: list[str] = []
    work = result_path.parent / f"accb-live-{int(time.time())}"
    work.mkdir(parents=True, exist_ok=True)

    for model_id in MODELS:
        endpoint = census[model_id]
        row: dict[str, Any] = {
            "model_identifier": model_id,
            "endpoint": endpoint,
            "status": "started",
        }
        try:
            # Small paid probe: proves credential/model route and measures semantic task payload with the provider tokenizer.
            probe_messages = build_task_probe_messages(scenario)
            probe_upper = estimated_cost(endpoint, 8_000, 4)
            if spent_estimate + probe_upper > max_budget_rub:
                raise IntegrationError("budget guard blocks task probe")
            probe_body, probe_elapsed = chat(api_key, model_id, endpoint, probe_messages, max_tokens=4, timeout=120)
            probe_prompt, probe_completion, _ = usage(probe_body)
            if probe_prompt is None or probe_completion is None:
                raise IntegrationError("task probe returned no token usage")
            probe_cost = estimated_cost(endpoint, probe_prompt, probe_completion)
            spent_estimate += probe_cost
            row["task_probe"] = {
                "prompt_tokens": probe_prompt,
                "completion_tokens": probe_completion,
                "elapsed_seconds": round(probe_elapsed, 6),
                "estimated_cost_rub": round(probe_cost, 6),
                "provider_metadata": safe_provider_metadata(probe_body),
            }

            messages, system_text, user_text = build_live_messages(scenario, trace_schema)
            # Conservative low-point bound; actual tokenizer usage is recorded from RouterAI response.
            live_upper_tokens = 80_000
            live_upper = estimated_cost(endpoint, live_upper_tokens, MAX_OUTPUT_TOKENS)
            if spent_estimate + live_upper > max_budget_rub:
                raise IntegrationError(
                    f"budget guard blocks live call for {model_id}: spent~{spent_estimate:.3f}, next_upper~{live_upper:.3f}, ceiling={max_budget_rub:.3f}"
                )
            live_body, live_elapsed = chat(
                api_key,
                model_id,
                endpoint,
                messages,
                max_tokens=MAX_OUTPUT_TOKENS,
                timeout=360,
            )
            prompt_tokens, completion_tokens, total_tokens = usage(live_body)
            if prompt_tokens is None or completion_tokens is None:
                raise IntegrationError("live response returned no token usage")
            live_cost = estimated_cost(endpoint, prompt_tokens, completion_tokens)
            spent_estimate += live_cost
            raw_text = response_text(live_body)
            candidate = extract_json_object(raw_text)
            trace_path = work / (model_id.replace("/", "__") + ".trace.json")
            score_path = work / (model_id.replace("/", "__") + ".score.json")
            trace_path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(scorer_path), "--scenario", str(scenario_path), "--trace", str(trace_path), "--output", str(score_path)],
                text=True,
                capture_output=True,
                check=False,
            )
            if not score_path.exists():
                raise IntegrationError(f"scorer produced no score file: rc={proc.returncode}, stderr={proc.stderr[-500:]}")
            score = read_json(score_path)
            manifest = {
                "experiment_id": "ACCB-ROUTERAI-CAL-2026-08-22-LOW-001",
                "scenario_id": str(scenario.get("scenario_id")),
                "scenario_version": str(scenario.get("scenario_version")),
                "provider": str(endpoint.get("tag") or endpoint.get("provider_name") or "routerai"),
                "model_identifier": model_id,
                "snapshot_if_available": None,
                "surface": "routerai/chat-completions",
                "timestamp": utc_now(),
                "nominal_context_window": endpoint.get("context_length"),
                "lengths": {
                    "L_model_input": prompt_tokens,
                    "L_task_payload": probe_prompt,
                    "L_visible_shell": max(prompt_tokens - probe_prompt, 0),
                    "hidden_provider_context": "UNKNOWN",
                },
                "prompt_hashes": [sha256_text(system_text), sha256_text(user_text)],
                "context_assembly_version": CONTEXT_ASSEMBLY_VERSION,
                "retrieval_policy_version": None,
                "compaction_policy_version": None,
                "memory_architecture": "single-request/no-external-memory",
                "reasoning_mode": "provider_default",
                "temperature": 0.0,
                "seed": None,
                "max_output_tokens": MAX_OUTPUT_TOKENS,
                "tool_versions": {"architecture_sha": architecture_sha, "scorer": str(SCORER_REL)},
                "initial_environment_state_hash": None,
                "gold_ledger_version": gold_version,
                "trace_ref": trace_path.name,
                "state_snapshot_refs": [],
                "judge_versions": {"deterministic_scorer": architecture_sha},
                "metrics": {**(score.get("metrics") or {}), "ACI": score.get("ACI"), "ACI_min": score.get("ACI_min")},
                "critical_failures": score.get("critical_failures") or [],
                "cost_latency": {
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "tool_calls": 0,
                    "retrieval_calls": 0,
                    "wall_clock_seconds": round(live_elapsed, 6),
                    "storage_io_bytes": None,
                    "provider_cost": round(live_cost, 6),
                    "currency": "RUB",
                    "recovery_overhead_seconds": None,
                },
            }
            row.update({
                "status": "scored",
                "provider_metadata": safe_provider_metadata(live_body),
                "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": total_tokens},
                "estimated_cost_rub": round(live_cost, 6),
                "score": score,
                "candidate_trace": candidate,
                "manifest": manifest,
            })
        except Exception as exc:
            row["status"] = "integration_error"
            row["error"] = f"{type(exc).__name__}: {exc}"[:1000]
            integration_errors.append(f"{model_id}: {row['error']}")
        model_rows.append(row)

    result = {
        "schema_version": "0.1",
        "experiment_id": "ACCB-ROUTERAI-CAL-2026-08-22-LOW-001",
        "architecture_sha": architecture_sha,
        "site_auditor_sha": os.getenv("GITHUB_SHA"),
        "timestamp": utc_now(),
        "pilot_scope": "one low-context ACCB-DEV-001 call per approved model plus task-payload token probe",
        "budget_ceiling_rub": max_budget_rub,
        "estimated_spend_rub": round(spent_estimate, 6),
        "models_requested": MODELS,
        "models_scored": sum(row.get("status") == "scored" for row in model_rows),
        "integration_errors": integration_errors,
        "rows": model_rows,
        "raw_provider_reasoning_saved": False,
        "scientific_claim_boundary": "Calibration/plumbing evidence only; no universal ECC/AMCE threshold inference.",
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if spent_estimate > max_budget_rub:
        return 3
    return 0 if not integration_errors else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ACCB RouterAI live pilot failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
