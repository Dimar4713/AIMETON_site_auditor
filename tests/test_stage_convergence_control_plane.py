from pathlib import Path


CONVERGENCE_PATH = (
    '.github/workflows/deploy-stage.yml',
    '.github/workflows/configure-dadata-stage.yml',
    '.github/workflows/runtime-persistence-reconcile.yml',
    '.github/workflows/stage-auth-persistence-guard.yml',
    '.github/workflows/stage-convergence.yml',
)


def test_full_stage_convergence_path_is_self_hosted_and_marketplace_free():
    for path in CONVERGENCE_PATH:
        text = Path(path).read_text(encoding='utf-8')
        assert 'ubuntu-latest' not in text, path
        assert 'uses: actions/' not in text, path
        assert 'self-hosted' in text, path


def test_post_deploy_mutators_require_real_parent_job_gate():
    dadata = Path('.github/workflows/configure-dadata-stage.yml').read_text(encoding='utf-8')
    persistence = Path('.github/workflows/runtime-persistence-reconcile.yml').read_text(encoding='utf-8')
    auth = Path('.github/workflows/stage-auth-persistence-guard.yml').read_text(encoding='utf-8')
    assert 'require_successful_parent_job.py' in dadata
    assert '--job-name deploy' in dadata
    assert 'require_successful_parent_job.py' in persistence
    assert '--job-name deploy' in persistence
    assert 'require_successful_parent_job.py' in auth
    assert '--job-name reconcile' in auth
    assert 'Require exact deployed source identity' in persistence
    assert 'Require exact deployed source identity' in auth


def test_stage_convergence_is_event_driven_and_does_not_hold_runner_waiting():
    text = Path('.github/workflows/stage-convergence.yml').read_text(encoding='utf-8')
    for trigger in (
        '- Deploy Stage',
        '- Configure DaData Stage',
        '- Runtime Persistence Reconcile',
        '- Stage Auth Persistence Guard',
    ):
        assert trigger in text
    assert 'timeout-minutes: 3' in text
    assert '--timeout-seconds' not in text
    assert '--poll-seconds' not in text
    assert "if: needs.resolve-gates.outputs.ready == 'true'" in text


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
