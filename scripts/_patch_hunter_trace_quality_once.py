from pathlib import Path

path = Path("app/discovery.py")
text = path.read_text(encoding="utf-8")
old_returned = '''                metadata={
                    "qualification": candidate.qualification,
                    "deep_analysis_performed": candidate.deep_analysis_performed,
                    "source_role": _candidate_rank_role(candidate),
                    "lead_fit": candidate.lead_fit,
'''
new_returned = '''                metadata={
                    "qualification": candidate.qualification,
                    "deep_analysis_performed": candidate.deep_analysis_performed,
                    "region_confirmed": candidate.region_confirmed,
                    "industry_match": candidate.pre_score_factors.get("industry_match"),
                    "source_role": _candidate_rank_role(candidate),
                    "lead_fit": candidate.lead_fit,
'''
old_omitted = '''                metadata={
                    "qualification": candidate.qualification,
                    "source_role": _candidate_rank_role(candidate),
                    "lead_fit": candidate.lead_fit,
'''
new_omitted = '''                metadata={
                    "qualification": candidate.qualification,
                    "region_confirmed": candidate.region_confirmed,
                    "industry_match": candidate.pre_score_factors.get("industry_match"),
                    "source_role": _candidate_rank_role(candidate),
                    "lead_fit": candidate.lead_fit,
'''
if text.count(old_returned) != 1 or text.count(old_omitted) != 1:
    raise SystemExit("unexpected discovery.py trace metadata shape")
path.write_text(text.replace(old_returned, new_returned, 1).replace(old_omitted, new_omitted, 1), encoding="utf-8")

test_path = Path("tests/test_hunter_forensic_trace.py")
test = test_path.read_text(encoding="utf-8")
marker = '''    final = hunter_events[-1]
    assert final.counters == {
'''
insert = '''    returned_event = next(event for event in hunter_events if event.operation == "candidate_returned")
    omitted_event = next(event for event in hunter_events if event.operation == "candidate_output_omitted")
    for candidate_event in (returned_event, omitted_event):
        assert candidate_event.metadata["region_confirmed"] is True
        assert candidate_event.metadata["industry_match"] == 25

    final = hunter_events[-1]
    assert final.counters == {
'''
if test.count(marker) != 1:
    raise SystemExit("unexpected forensic trace test shape")
test_path.write_text(test.replace(marker, insert, 1), encoding="utf-8")
