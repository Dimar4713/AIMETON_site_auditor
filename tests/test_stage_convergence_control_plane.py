from pathlib import Path


def test_stage_convergence_is_self_hosted_and_marketplace_free():
    text = Path('.github/workflows/stage-convergence.yml').read_text(encoding='utf-8')
    assert 'ubuntu-latest' not in text
    assert 'uses: actions/' not in text
    assert 'runs-on: [self-hosted, Linux, X64, stage, auditor]' in text
    assert 'scripts/resolve_stage_convergence_gates.py' in text


def test_stage_convergence_keeps_exact_sha_and_required_gates():
    text = Path('.github/workflows/stage-convergence.yml').read_text(encoding='utf-8')
    for required in (
        'Deploy Stage',
        'Configure DaData Stage',
        'Runtime Persistence Reconcile',
        'Stage Auth Persistence Guard',
        'write_stage_convergence_marker.py',
        "payload.get('state') == 'converged'",
    ):
        assert required in text
