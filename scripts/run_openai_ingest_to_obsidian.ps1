param(
    [Parameter(Mandatory = $true)]
    [string]$VaultRoot,

    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [string]$PythonExe = 'python',
    [int]$SinceDays = 30,
    [int]$LimitPerSource = 10,
    [double]$Threshold = 0,
    [switch]$KeepTempSources
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $VaultRoot)) {
    throw "VaultRoot does not exist: $VaultRoot"
}

Push-Location $RepoRoot
try {
    $tempSources = Join-Path ([System.IO.Path]::GetTempPath()) ("openai_only_sources_{0}.yaml" -f ([Guid]::NewGuid().ToString('N')))

    @"
- id: openai_news
  name: ""OpenAI News""
  type: rss
  url: ""https://openai.com/news/rss.xml""
  priority_weight: 1.0
  signal_type: ecosystem
"@ | Set-Content -LiteralPath $tempSources -Encoding UTF8

    Write-Host "[1/3] Running Layer-1 ingest for OpenAI RSS..." -ForegroundColor Cyan
    $cmd = @(
        '-m', 'orchestrator.cli', 'ingest',
        '--sources', $tempSources,
        '--since-days', $SinceDays,
        '--limit-per-source', $LimitPerSource,
        '--threshold', $Threshold,
        '--vault-root', $VaultRoot,
        '--writeback-signals'
    )

    $raw = & $PythonExe @cmd 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Ingest failed (exit $LASTEXITCODE):`n$($raw -join [Environment]::NewLine)"
    }

    $jsonLine = ($raw | Where-Object { $_ -match '^\s*\{' } | Select-Object -Last 1)
    if (-not $jsonLine) {
        throw "Cannot find JSON report in CLI output:`n$($raw -join [Environment]::NewLine)"
    }

    $report = $jsonLine | ConvertFrom-Json

    Write-Host "[2/3] Ingest report" -ForegroundColor Cyan
    $report | ConvertTo-Json -Depth 5

    $signalDir = Join-Path $VaultRoot '95_Signals'
    $written = @()
    if (Test-Path -LiteralPath $signalDir) {
        $written = Get-ChildItem -LiteralPath $signalDir -Filter 'SIG-*.md' | Sort-Object LastWriteTime -Descending | Select-Object -First 10
    }

    Write-Host "[3/3] Latest signal notes in Obsidian" -ForegroundColor Cyan
    if ($written.Count -eq 0) {
        Write-Warning "No SIG-*.md found under $signalDir"
    } else {
        $written | ForEach-Object { Write-Host (" - {0}" -f $_.FullName) }
    }

    if ($report.failed_count -gt 0) {
        Write-Warning "Some sources failed. Check failures field in report."
    }

    if ($report.vault_written -le 0) {
        Write-Warning "No new notes were written (possible duplicates or no recent items)."
    } else {
        Write-Host "Done. New notes written: $($report.vault_written)" -ForegroundColor Green
    }
}
finally {
    if ($tempSources -and (Test-Path -LiteralPath $tempSources) -and (-not $KeepTempSources)) {
        Remove-Item -LiteralPath $tempSources -Force -ErrorAction SilentlyContinue
    }
    Pop-Location
}
