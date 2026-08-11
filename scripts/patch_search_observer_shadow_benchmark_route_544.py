from pathlib import Path

path = Path('.github/workflows/aimeton-command-router.yml')
text = path.read_text(encoding='utf-8')
old = 'accept-hunter-real-e2e-stage)\\s+([0-9a-f]{40})$/);'
new = 'accept-hunter-real-e2e-stage|benchmark-search-observer-shadow-stage)\\s+([0-9a-f]{40})$/);'
if old not in text:
    raise SystemExit('command regex anchor not found')
text = text.replace(old, new, 1)
anchor = """              'accept-hunter-real-e2e-stage': {
                issue_number: 441,
                workflow_id: 'accept-hunter-real-e2e-stage.yml',
                inputs: {
                  expected_sha: sha,
                  region: 'Красноярск',
                  industry: 'Стоматология',
                  expected_providers: 'searxng,yandex',
                  minimum_returned: '10',
                  minimum_direct_returned: '10',
                  allow_paid_calls: 'true',
                },
              },
"""
insertion = anchor + """              'benchmark-search-observer-shadow-stage': {
                issue_number: 544,
                workflow_id: 'benchmark-search-observer-shadow-stage.yml',
                inputs: {
                  expected_sha: sha,
                  allow_paid_calls: 'true',
                },
              },
"""
if anchor not in text:
    raise SystemExit('route insertion anchor not found')
text = text.replace(anchor, insertion, 1)
path.write_text(text, encoding='utf-8')
print('patched owner-gated Search Observer shadow benchmark route')
