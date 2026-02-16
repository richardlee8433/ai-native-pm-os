# Weekly Task Scheduler Snippet (Layer 1 Intake)

Use Windows Task Scheduler to run weekly Layer-1 signal intake on **Monday 09:10**.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$env:PM_OS_VAULT_ROOT='G:\My Drive\AI Native PM\AI Native PM\'; cd 'C:\Users\richard_lee\ai-native-pm-os'; python -m orchestrator.cli ingest --since-days 7 --limit-per-source 10 --threshold 0 --writeback-signals"
```

This writes newly ingested signal notes to `<PM_OS_VAULT_ROOT>\98_Signals\SIG-*.md`.
