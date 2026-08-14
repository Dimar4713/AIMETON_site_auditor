from pathlib import Path
import re

models = Path("app/models.py")
text = models.read_text(encoding="utf-8")
needle = '''class HuntResult(BaseModel):
    region: str
    search_zone: str | None = None
    queries: list[str] = Field(default_factory=list)
    discovered: int
    candidates: list[HuntCandidate] = Field(default_factory=list)
    funnel: HuntFunnel = Field(default_factory=HuntFunnel)
    notes: list[str] = Field(default_factory=list)
    search: SearchDiagnostics | None = None
'''
replacement = '''class HuntResult(BaseModel):
    region: str
    search_zone: str | None = None
    queries: list[str] = Field(default_factory=list)
    discovered: int
    candidates: list[HuntCandidate] = Field(default_factory=list)
    funnel: HuntFunnel = Field(default_factory=HuntFunnel)
    notes: list[str] = Field(default_factory=list)
    search: SearchDiagnostics | None = None
    trace_mission_id: str | None = Field(default=None, exclude=True, repr=False)
    trace_attempt_id: str | None = Field(default=None, exclude=True, repr=False)
'''
assert text.count(needle) == 1
models.write_text(text.replace(needle, replacement, 1), encoding="utf-8")

discovery = Path("app/discovery.py")
text = discovery.read_text(encoding="utf-8")
pattern = re.compile(r"(?m)^(\s*)return HuntResult\(\n")
matches = list(pattern.finditer(text))
assert len(matches) == 2
text = pattern.sub(
    lambda match: (
        f"{match.group(1)}return HuntResult(\n"
        f"{match.group(1)}    trace_mission_id=mission_id,\n"
        f"{match.group(1)}    trace_attempt_id=correlation_id,\n"
    ),
    text,
)
discovery.write_text(text, encoding="utf-8")

main = Path("app/main.py")
text = main.read_text(encoding="utf-8")
import_marker = "from app.search_gap_shadow_refinement import build_shadow_follow_up_queries\n"
assert text.count(import_marker) == 1
text = text.replace(
    import_marker,
    import_marker + "from app.search_gap_shadow_trace import persist_shadow_follow_up_suggestions\n",
    1,
)
return_marker = '''    payload["search_refinement_shadow"] = {
        "gap_count": len(refinement.gaps),
        "gaps": [
            {"code": gap.code, "evidence_target": gap.evidence_target, "reason": gap.reason}
            for gap in refinement.gaps
        ],
        "suggestion_count": len(refinement.suggestions),
        "suggestions": [
            {
                "query": item.query,
                "reason_code": item.reason_code,
                "evidence_target": item.evidence_target,
            }
            for item in refinement.suggestions
        ],
        "routing_changed": False,
        "steering_enabled": False,
    }
    return payload
'''
replacement = '''    payload["search_refinement_shadow"] = {
        "gap_count": len(refinement.gaps),
        "gaps": [
            {"code": gap.code, "evidence_target": gap.evidence_target, "reason": gap.reason}
            for gap in refinement.gaps
        ],
        "suggestion_count": len(refinement.suggestions),
        "suggestions": [
            {
                "query": item.query,
                "reason_code": item.reason_code,
                "evidence_target": item.evidence_target,
            }
            for item in refinement.suggestions
        ],
        "routing_changed": False,
        "steering_enabled": False,
    }
    trace_mission_id = getattr(result, "trace_mission_id", None)
    trace_attempt_id = getattr(result, "trace_attempt_id", None)
    if trace_mission_id and trace_attempt_id:
        persist_shadow_follow_up_suggestions(
            mission_id=trace_mission_id,
            attempt_id=trace_attempt_id,
            effective_regime=effective_regime,
            plan=refinement,
        )
    return payload
'''
assert text.count(return_marker) == 1
main.write_text(text.replace(return_marker, replacement, 1), encoding="utf-8")
