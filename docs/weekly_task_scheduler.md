# Weekly Task Scheduler Snippet (Layer 1 Intake)

Use Windows Task Scheduler to run weekly Layer-1 signal intake on **Monday 09:10**.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$env:PM_OS_VAULT_ROOT='G:\My Drive\AI Native PM\AI Native PM\'; cd 'C:\Users\richard_lee\ai-native-pm-os'; python -m orchestrator.cli ingest --since-days 7 --limit-per-source 10 --threshold 0 --writeback-signals"
```

This writes newly ingested signal notes to `<PM_OS_VAULT_ROOT>\95_Signals\SIG-*.md`.


## One-click PowerShell script (OpenAI RSS only)

Use `scripts/run_openai_ingest_to_obsidian.ps1` to test OpenAI RSS end-to-end (fetch → normalize → writeback to Obsidian).

```powershell
pwsh -File .\scripts\run_openai_ingest_to_obsidian.ps1 -VaultRoot "G:\My Drive\AI Native PM\AI Native PM\"
```

Optional parameters:
- `-RepoRoot <path>`
- `-PythonExe python`
- `-SinceDays 30`
- `-LimitPerSource 10`
- `-Threshold 0`
- `-KeepTempSources`
