from __future__ import annotations

import json
import math
import os
import sys
import threading
from pathlib import Path
from typing import Any

from openai import OpenAI

import llm_verifier
from app.llm_verifier_adapter import (
    LLM_VERIFIER_PINNED_SHA,
    LLMVerifierSelectionEnvelope,
    adapt_llm_verifier_selection,
)
from app.verifier_calibration import aggregate_calibration, evaluate_golden_fixture_ranking
from app.verifier_fixtures import build_sef_verification_requests


DEFAULT_MODEL = "openai/gpt-4o-mini"
DEFAULT_BASE_URL = "https://routerai.ru/api/v1"
INPUT_RUB_PER_MILLION = 15.0
OUTPUT_RUB_PER_MILLION = 61.0
MAX_PRIMARY_OUTPUT_TOKENS = 512
BUDGET_SAFETY_RESERVE_RUB = 5.0
N_EVALUATIONS = 1
PIVOTS = 2


class BudgetExhausted(RuntimeError):
    pass


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def _float_env(name: str) -> float:
    raw = _required_env(name)
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeError(f"invalid numeric environment variable: {name}") from exc


def _num(value: Any) -> int:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def _cost_rub(prompt_tokens: int, completion_tokens: int) -> float:
    return (
        prompt_tokens * INPUT_RUB_PER_MILLION
        + completion_tokens * OUTPUT_RUB_PER_MILLION
    ) / 1_000_000.0


def _letter_alternatives(position: Any) -> int:
    count = 0
    for alt in getattr(position, "top_logprobs", None) or []:
        token = str(getattr(alt, "token", "") or "").strip()
        if token.startswith(">"):
            token = token[1:].strip()
        if len(token) == 1 and "A" <= token.upper() <= "T":
            count += 1
    return count


def _score_distribution_events(response: Any, request_kwargs: dict[str, Any]) -> int:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return 0
    choice = choices[0]
    logprobs = getattr(choice, "logprobs", None)
    content = getattr(logprobs, "content", None) if logprobs is not None else None
    if not content:
        return 0

    events = 0

    # Prefill path: the tag is already present in the assistant prefix, while
    # the returned one-token distribution contains the A-T score choices.
    messages = request_kwargs.get("messages") or []
    if messages:
        last = messages[-1]
        if isinstance(last, dict) and last.get("role") == "assistant":
            prefix = str(last.get("content") or "").rstrip()
            if prefix.endswith(("<score_A>", "<score_B>")) and _letter_alternatives(content[0]) >= 2:
                events += 1

    # Direct-output path: mirror the fork tag-location logic and require a
    # non-trivial A-T distribution immediately after each score tag.
    tokens_so_far = ""
    found: dict[str, bool] = {"<score_A>": False, "<score_B>": False}
    for index, position in enumerate(content):
        token = str(getattr(position, "token", "") or "")
        tokens_so_far += token
        if not token.strip():
            continue
        for tag in found:
            if found[tag]:
                continue
            if tokens_so_far.rstrip().endswith(tag) or tokens_so_far.rstrip().endswith(tag[:-1]):
                if index + 1 < len(content) and _letter_alternatives(content[index + 1]) >= 2:
                    found[tag] = True
    events += sum(found.values())
    return events


class BudgetLedger:
    def __init__(self, max_budget_rub: float) -> None:
        self.max_budget_rub = max_budget_rub
        self._lock = threading.Lock()
        self.provider_attempts = 0
        self.provider_successes = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.responses_with_logprobs = 0
        self.score_distribution_events = 0

    @property
    def estimated_cost_rub(self) -> float:
        return _cost_rub(self.prompt_tokens, self.completion_tokens)

    def snapshot(self) -> dict[str, int | float]:
        with self._lock:
            return {
                "provider_attempts": self.provider_attempts,
                "provider_successes": self.provider_successes,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "estimated_cost_rub": self.estimated_cost_rub,
                "responses_with_logprobs": self.responses_with_logprobs,
                "score_distribution_events": self.score_distribution_events,
            }

    def prepare(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        bounded = dict(kwargs)
        requested_output = _num(bounded.get("max_tokens")) or MAX_PRIMARY_OUTPUT_TOKENS
        bounded["max_tokens"] = min(requested_output, MAX_PRIMARY_OUTPUT_TOKENS)

        # Conservative token upper bound: one token per serialized character
        # plus fixed protocol headroom. This deliberately overestimates the
        # short Golden-5 prompts before the provider call.
        serialized = json.dumps(bounded.get("messages") or [], ensure_ascii=False, default=str)
        input_upper = len(serialized) + 2048
        output_upper = bounded["max_tokens"]
        call_upper_rub = _cost_rub(input_upper, output_upper)

        with self._lock:
            if self.estimated_cost_rub + call_upper_rub > self.max_budget_rub - BUDGET_SAFETY_RESERVE_RUB:
                raise BudgetExhausted(
                    "next provider call would cross the owner budget reserve: "
                    f"spent~{self.estimated_cost_rub:.6f} RUB, "
                    f"call_upper~{call_upper_rub:.6f} RUB, "
                    f"budget={self.max_budget_rub:.2f} RUB"
                )
            self.provider_attempts += 1
        return bounded

    def record(self, response: Any, request_kwargs: dict[str, Any]) -> None:
        usage = getattr(response, "usage", None)
        prompt = _num(getattr(usage, "prompt_tokens", 0)) if usage is not None else 0
        completion = _num(getattr(usage, "completion_tokens", 0)) if usage is not None else 0

        choices = getattr(response, "choices", None) or []
        has_logprobs = False
        if choices:
            lp = getattr(choices[0], "logprobs", None)
            has_logprobs = bool(getattr(lp, "content", None)) if lp is not None else False

        events = _score_distribution_events(response, request_kwargs)

        with self._lock:
            self.provider_successes += 1
            self.prompt_tokens += prompt
            self.completion_tokens += completion
            self.responses_with_logprobs += int(has_logprobs)
            self.score_distribution_events += events


class _BudgetedCompletions:
    def __init__(self, inner: Any, ledger: BudgetLedger) -> None:
        self._inner = inner
        self._ledger = ledger

    def create(self, *args: Any, **kwargs: Any) -> Any:
        bounded = self._ledger.prepare(kwargs)
        response = self._inner.create(*args, **bounded)
        self._ledger.record(response, bounded)
        return response


class _BudgetedChat:
    def __init__(self, inner: Any, ledger: BudgetLedger) -> None:
        self.completions = _BudgetedCompletions(inner.completions, ledger)


class BudgetedOpenAIClient:
    def __init__(self, base: OpenAI, ledger: BudgetLedger, model: str) -> None:
        self.chat = _BudgetedChat(base.chat, ledger)
        self.models = base.models
        self._llm_verifier_model = model


def _delta(after: dict[str, int | float], before: dict[str, int | float]) -> dict[str, int | float]:
    keys = set(after) | set(before)
    return {key: after.get(key, 0) - before.get(key, 0) for key in keys}


def _write_result(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    api_key = _required_env("ROUTERAI_API_KEY")
    base_url = os.getenv("ROUTERAI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.getenv("VERIFIER_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    max_budget_rub = _float_env("VERIFIER_MAX_BUDGET_RUB")
    result_path = Path(_required_env("VERIFIER_RESULT_PATH"))
    benchmark_path = Path(os.getenv("VERIFIER_BENCHMARK_PATH", "benchmarks/sef/benchmark-20-v0.1.json"))
    golden_path = Path(os.getenv("VERIFIER_GOLDEN_PATH", "benchmarks/sef/golden-5-v0.1.json"))

    if model != DEFAULT_MODEL:
        raise RuntimeError(f"Golden-5 P0 calibration is pinned to {DEFAULT_MODEL}, got {model}")
    if not (BUDGET_SAFETY_RESERVE_RUB < max_budget_rub <= 100.0):
        raise RuntimeError(
            f"VERIFIER_MAX_BUDGET_RUB must be in ({BUDGET_SAFETY_RESERVE_RUB}, 100]"
        )
    if LLM_VERIFIER_PINNED_SHA != "9cabf17e3644778893666b864aec924e740006ba":
        raise RuntimeError("unexpected Site Auditor verifier pin")
    if getattr(llm_verifier, "__version__", None) != "0.2.0":
        raise RuntimeError("unexpected llm-verifier package version")

    requests = build_sef_verification_requests(benchmark_path, golden_path)
    if len(requests) != 5:
        raise RuntimeError(f"expected Golden-5 to yield 5 requests, got {len(requests)}")

    ledger = BudgetLedger(max_budget_rub)
    base_client = OpenAI(base_url=base_url, api_key=api_key)
    client = BudgetedOpenAIClient(base_client, ledger, model)

    calibrations = []
    case_rows: list[dict[str, Any]] = []
    terminal_status = "complete"

    for index, request in enumerate(requests):
        before = ledger.snapshot()
        candidate_texts = [
            json.dumps(candidate.payload, ensure_ascii=False, sort_keys=True)
            for candidate in request.candidates
        ]
        criteria = [criterion.model_dump(mode="json") for criterion in request.criteria]

        try:
            selection = llm_verifier.select(
                request.task,
                candidate_texts,
                criteria=criteria,
                n_evaluations=N_EVALUATIONS,
                pivots=PIVOTS,
                seed=0,
                max_workers=1,
                model=model,
                cache=None,
                progress=False,
                on_error="raise",
                client=client,
            )
        except BudgetExhausted as exc:
            terminal_status = "budget_stopped"
            case_rows.append(
                {
                    "request_id": request.request_id,
                    "measurement_status": "budget_stopped",
                    "reason": str(exc)[:500],
                }
            )
            break
        except Exception as exc:
            terminal_status = "integration_degraded" if index == 0 else "measurement_degraded"
            case_rows.append(
                {
                    "request_id": request.request_id,
                    "measurement_status": terminal_status,
                    "reason": f"{type(exc).__name__}: {exc}"[:500],
                }
            )
            break

        after = ledger.snapshot()
        usage_delta = _delta(after, before)
        expected_distribution_events = (
            2 * selection.n_comparisons * len(criteria) * N_EVALUATIONS
        )
        observed_distribution_events = int(usage_delta["score_distribution_events"])
        spread = max(selection.scores) - min(selection.scores) if selection.scores else 0.0
        signal_valid = (
            observed_distribution_events >= expected_distribution_events
            and math.isfinite(spread)
            and spread > 1e-9
        )

        envelope = LLMVerifierSelectionEnvelope(
            engine_revision=LLM_VERIFIER_PINNED_SHA,
            ranking_indices=selection.ranking,
            scores=selection.scores,
            signal_status="valid" if signal_valid else "degraded",
        )
        domain_result = adapt_llm_verifier_selection(request, envelope)
        calibration = evaluate_golden_fixture_ranking(request, domain_result)
        calibrations.append(calibration)

        case_rows.append(
            {
                "request_id": request.request_id,
                "case_id": request.metadata.get("case_id"),
                "measurement_status": domain_result.status,
                "reason_code": domain_result.reason_code,
                "ranking": domain_result.ranking,
                "scores": {
                    score.candidate_id: round(score.score, 9)
                    for score in domain_result.scores
                },
                "correct_rank": calibration.correct_rank,
                "correct_is_top1": calibration.correct_is_top1,
                "pairwise_accuracy": round(calibration.pairwise_accuracy, 9),
                "usable_measurement": calibration.usable_measurement,
                "n_comparisons": selection.n_comparisons,
                "expected_score_distribution_events": expected_distribution_events,
                "observed_score_distribution_events": observed_distribution_events,
                "score_spread": round(spread, 9),
                "provider_usage_delta": {
                    key: round(value, 9) if isinstance(value, float) else value
                    for key, value in usage_delta.items()
                },
            }
        )

        # The first case is also the pinned-fork -> RouterAI integration gate.
        if not calibration.usable_measurement:
            terminal_status = "integration_degraded" if index == 0 else "measurement_degraded"
            break

        # Before entering another case, require conservative room based on the
        # observed previous case in addition to the per-call hard guard.
        if index + 1 < len(requests):
            case_cost = float(usage_delta["estimated_cost_rub"])
            conservative_next_case = max(case_cost * 2.0, 1.0)
            if ledger.estimated_cost_rub + conservative_next_case > max_budget_rub - BUDGET_SAFETY_RESERVE_RUB:
                terminal_status = "budget_stopped"
                break

    aggregate = aggregate_calibration(calibrations)
    all_five_usable = (
        len(calibrations) == 5
        and all(row.usable_measurement for row in calibrations)
    )
    if not all_five_usable and terminal_status == "complete":
        terminal_status = "measurement_degraded"

    final_usage = ledger.snapshot()
    payload = {
        "schema_version": "1.0",
        "experiment": "verifier-p0-golden5-live-calibration",
        "measurement_status": terminal_status,
        "backend_id": "routerai",
        "requested_model": model,
        "verifier_engine": "llm-verifier",
        "verifier_revision": LLM_VERIFIER_PINNED_SHA,
        "llm_verifier_version": getattr(llm_verifier, "__version__", None),
        "n_evaluations": N_EVALUATIONS,
        "pivots": PIVOTS,
        "max_workers": 1,
        "max_primary_output_tokens": MAX_PRIMARY_OUTPUT_TOKENS,
        "max_budget_rub": max_budget_rub,
        "budget_safety_reserve_rub": BUDGET_SAFETY_RESERVE_RUB,
        "pricing_snapshot_rub_per_million": {
            "input": INPUT_RUB_PER_MILLION,
            "output": OUTPUT_RUB_PER_MILLION,
        },
        "pricing_source": "https://routerai.ru/models/openai/gpt-4o-mini",
        "cases_requested": 5,
        "cases_recorded": len(case_rows),
        "aggregate": aggregate,
        "cases": case_rows,
        "provider_usage": {
            key: round(value, 9) if isinstance(value, float) else value
            for key, value in final_usage.items()
        },
        "raw_provider_response_saved": False,
        "candidate_payloads_persisted": False,
        "client_release_authority": False,
        "hard_gate_override": False,
    }
    _write_result(result_path, payload)

    return 0 if all_five_usable else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Golden-5 verifier calibration failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
