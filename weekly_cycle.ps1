$ErrorActionPreference = "Stop"

Write-Host "== PM-OS Weekly Cycle ==" -ForegroundColor Cyan

Write-Host "`n[1/4] Ingest: past 7 days" -ForegroundColor Yellow
python -m orchestrator.cli ingest --since-days 7

Write-Host "`n[2/4] Weekly report" -ForegroundColor Yellow
python -m orchestrator.cli weekly

Write-Host "`n[3/4] Action suggestion" -ForegroundColor Yellow
python -m orchestrator.cli action generate

Write-Host "`n[4/4] Status Check: pending signals" -ForegroundColor Yellow
python -c "import json, pathlib; p=pathlib.Path('orchestrator/data/signals.jsonl'); \
rows=[json.loads(l) for l in p.read_text(encoding='utf-8').splitlines()] if p.exists() else []; \
pending=[r['id'] for r in rows if isinstance(r.get('id'), str) and r.get('gate_status') is None]; \
print('Pending signal IDs:'); \
[print(f' - {sid}') for sid in pending] if pending else print(' - (none)')"

Write-Host "`nNext step: run gate decide for pending signals." -ForegroundColor Green
