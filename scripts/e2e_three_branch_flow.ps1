<#
Run from repo root:
  powershell -ExecutionPolicy Bypass -File .\scripts\e2e_three_branch_flow.ps1
  pwsh -File ./scripts/e2e_three_branch_flow.ps1

Optional CI behavior:
  Set PM_OS_E2E_SKIP_CLEANUP=1 to keep test vault/data artifacts for inspection.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

function Assert-True {
    param(
        [Parameter(Mandatory = $true)]
        [bool]$Condition,
        [Parameter(Mandatory = $true)]
        [string]$Message
    )
    if (-not $Condition) {
        throw "ASSERT TRUE FAILED: $Message"
    }
}

function Assert-Equal {
    param(
        [Parameter(Mandatory = $true)]$Expected,
        [Parameter(Mandatory = $true)]$Actual,
        [Parameter(Mandatory = $true)]
        [string]$Message
    )
    if ($Expected -ne $Actual) {
        throw "ASSERT EQUAL FAILED: $Message (expected='$Expected', actual='$Actual')"
    }
}

function Read-Jsonl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )
    $rows = @()
    if (-not (Test-Path -LiteralPath $Path)) {
        return $rows
    }
    $lines = Get-Content -LiteralPath $Path
    foreach ($line in $lines) {
        if ($line -and $line.Trim().Length -gt 0) {
            $rows += ($line | ConvertFrom-Json)
        }
    }
    return $rows
}

function Invoke-CliJson {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [hashtable]$ExtraEnv
    )

    $oldVals = @{}
    if ($ExtraEnv) {
        foreach ($k in $ExtraEnv.Keys) {
            $oldVals[$k] = [Environment]::GetEnvironmentVariable($k, 'Process')
            [Environment]::SetEnvironmentVariable($k, [string]$ExtraEnv[$k], 'Process')
        }
    }

    try {
        $output = & python @Arguments 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed (exit=$LASTEXITCODE): python $($Arguments -join ' ')`n$output"
        }

        $joined = ($output | ForEach-Object { $_.ToString() }) -join "`n"
        $jsonLine = $null
        $split = $joined -split "`r?`n"
        for ($i = $split.Length - 1; $i -ge 0; $i--) {
            $candidate = $split[$i].Trim()
            if ($candidate.StartsWith('{') -or $candidate.StartsWith('[')) {
                $jsonLine = $candidate
                break
            }
        }
        if (-not $jsonLine) {
            throw "No JSON output found for: python $($Arguments -join ' ')`n$joined"
        }
        return ($jsonLine | ConvertFrom-Json)
    }
    finally {
        if ($ExtraEnv) {
            foreach ($k in $ExtraEnv.Keys) {
                [Environment]::SetEnvironmentVariable($k, $oldVals[$k], 'Process')
            }
        }
    }
}

$repoRoot = (Get-Location).Path
$testVault = Join-Path $repoRoot ".vault_e2e_test"
$dataDir = Join-Path $repoRoot ".e2e_orchestrator_data"
$tempSources = Join-Path $env:TEMP ("pm_os_e2e_sources_" + [Guid]::NewGuid().ToString("N") + ".yaml")
$skipCleanup = $env:PM_OS_E2E_SKIP_CLEANUP -eq "1"

$summary = New-Object System.Collections.ArrayList

try {
    Write-Host "[E2E] Preparing isolated vault and data directories..."

    if (Test-Path -LiteralPath $testVault) { Remove-Item -LiteralPath $testVault -Recurse -Force }
    if (Test-Path -LiteralPath $dataDir) { Remove-Item -LiteralPath $dataDir -Recurse -Force }

    $null = New-Item -ItemType Directory -Path (Join-Path $testVault "00_Index") -Force
    $null = New-Item -ItemType Directory -Path (Join-Path $testVault "95_Signals") -Force
    $null = New-Item -ItemType Directory -Path (Join-Path $testVault "96_Weekly_Review") -Force
    $null = New-Item -ItemType Directory -Path (Join-Path $testVault "97_Gate_Decisions") -Force
    $null = New-Item -ItemType Directory -Path (Join-Path $testVault "06_Archive/COS") -Force
    $null = New-Item -ItemType Directory -Path (Join-Path $testVault "01_RTI") -Force
    $null = New-Item -ItemType Directory -Path $dataDir -Force

    @"
version: 1
sources:
  - id: openai-rss
    type: rss
    url: https://openai.com/news/rss.xml
    enabled: true
"@ | Set-Content -LiteralPath $tempSources -Encoding UTF8

    $commonEnv = @{ PM_OS_VAULT_ROOT = $testVault }

    Write-Host "[E2E] Step 1: ingest"
    $ingest = Invoke-CliJson -Arguments @(
        "-m", "orchestrator.cli",
        "--data-dir", $dataDir,
        "ingest",
        "--sources", $tempSources,
        "--since-days", "3650",
        "--limit-per-source", "5",
        "--threshold", "0",
        "--vault-root", $testVault,
        "--writeback-signals"
    ) -ExtraEnv $commonEnv

    Assert-Equal 5 ([int]$ingest.vault_written) "ingest should write 5 vault signal files"
    $sigFiles = @(Get-ChildItem -LiteralPath (Join-Path $testVault "95_Signals") -Filter "SIG-*.md" -File)
    Assert-Equal 5 $sigFiles.Count "expected exactly 5 SIG markdown files"
    $null = $summary.Add("PASS: ingest wrote 5 signals")

    Write-Host "[E2E] Step 2: weekly"
    $weekly = Invoke-CliJson -Arguments @(
        "-m", "orchestrator.cli",
        "--data-dir", $dataDir,
        "weekly",
        "--vault-root", $testVault,
        "--limit", "3"
    ) -ExtraEnv $commonEnv
    $weeklyFiles = @(Get-ChildItem -LiteralPath (Join-Path $testVault "96_Weekly_Review") -Filter "Weekly-Intel-*.md" -File)
    Assert-True ($weeklyFiles.Count -ge 1) "expected at least one Weekly-Intel file"
    $null = $summary.Add("PASS: weekly review note generated")

    Write-Host "[E2E] Step 3: select target signals"
    $signalsPath = Join-Path $dataDir "signals.jsonl"
    $signals = Read-Jsonl -Path $signalsPath
    Assert-True ($signals.Count -ge 3) "need at least 3 signals for three-branch test"
    $sortedSignals = $signals | Sort-Object @{ Expression = { if ($null -eq $_.priority_score) { 0.0 } else { [double]$_.priority_score } }; Descending = $true }

    $TopSignal = $sortedSignals[0]
    $ApproveSignal = $sortedSignals[1]
    $RejectSignal = $sortedSignals[2]

    $TopSignalId = [string]$TopSignal.id
    $TopSignalUrl = [string]$TopSignal.url
    $ApproveSignalId = [string]$ApproveSignal.id
    $RejectSignalId = [string]$RejectSignal.id

    Assert-True (-not [string]::IsNullOrWhiteSpace($TopSignalId)) "Top signal id must be non-empty"
    Assert-True (-not [string]::IsNullOrWhiteSpace($ApproveSignalId)) "Approve signal id must be non-empty"
    Assert-True (-not [string]::IsNullOrWhiteSpace($RejectSignalId)) "Reject signal id must be non-empty"
    $null = $summary.Add("PASS: selected TopSignalId=$TopSignalId, TopSignalUrl=$TopSignalUrl")

    Write-Host "[E2E] Branch A: DEFERRED"
    $decBeforeA = @(Get-ChildItem -LiteralPath (Join-Path $testVault "97_Gate_Decisions") -Filter "DEC-*.md" -File).Count
    $cosBeforeA = @(Get-ChildItem -LiteralPath (Join-Path $testVault "06_Archive/COS") -Filter "COS-*.md" -File).Count
    $rtiBeforeA = @(Get-ChildItem -LiteralPath (Join-Path $testVault "01_RTI") -Filter "RTI-*.md" -File).Count

    $branchA = Invoke-CliJson -Arguments @(
        "-m", "orchestrator.cli",
        "--data-dir", $dataDir,
        "gate", "decide",
        "--signal-id", $TopSignalId,
        "--decision", "deferred",
        "--priority", "Medium",
        "--reason", "E2E deferred test"
    ) -ExtraEnv $commonEnv

    $decAfterA = @(Get-ChildItem -LiteralPath (Join-Path $testVault "97_Gate_Decisions") -Filter "DEC-*.md" -File).Count
    Assert-Equal ($decBeforeA + 1) $decAfterA "Branch A should create one DEC file"

    $signalsAfterA = Read-Jsonl -Path $signalsPath
    $topRowA = $signalsAfterA | Where-Object { $_.id -eq $TopSignalId } | Select-Object -First 1
    Assert-Equal "deferred" ([string]$topRowA.gate_status) "Branch A signal gate_status should be deferred"
    Assert-True (-not [string]::IsNullOrWhiteSpace([string]$topRowA.gate_decision_id)) "Branch A signal should have gate_decision_id"

    $cosAfterA = @(Get-ChildItem -LiteralPath (Join-Path $testVault "06_Archive/COS") -Filter "COS-*.md" -File).Count
    $rtiAfterA = @(Get-ChildItem -LiteralPath (Join-Path $testVault "01_RTI") -Filter "RTI-*.md" -File).Count
    Assert-Equal $cosBeforeA $cosAfterA "Branch A should not create COS files"
    Assert-Equal $rtiBeforeA $rtiAfterA "Branch A should not create RTI files"

    $tasksPath = Join-Path $dataDir "weekly_tasks.jsonl"
    $tasksAfterA = Read-Jsonl -Path $tasksPath
    $deepTaskA = $tasksAfterA | Where-Object { $_.id -eq ("ACT-DEEPEN-" + $TopSignalId) } | Select-Object -First 1
    Assert-True ($null -eq $deepTaskA) "Branch A should not create deepening task"
    $null = $summary.Add("PASS: Branch A deferred assertions")

    Write-Host "[E2E] Branch B: APPROVED + DEEPEN"
    $decBeforeB = $decAfterA
    $branchB = Invoke-CliJson -Arguments @(
        "-m", "orchestrator.cli",
        "--data-dir", $dataDir,
        "gate", "decide",
        "--signal-id", $ApproveSignalId,
        "--decision", "approved",
        "--priority", "High",
        "--reason", "E2E approved test"
    ) -ExtraEnv $commonEnv

    $decAfterB = @(Get-ChildItem -LiteralPath (Join-Path $testVault "97_Gate_Decisions") -Filter "DEC-*.md" -File).Count
    Assert-Equal ($decBeforeB + 1) $decAfterB "Branch B should create one DEC file"

    $tasksAfterB = Read-Jsonl -Path $tasksPath
    $expectedDeepTaskId = "ACT-DEEPEN-$ApproveSignalId"
    $deepTaskB = $tasksAfterB | Where-Object { $_.id -eq $expectedDeepTaskId } | Select-Object -First 1
    Assert-True ($null -ne $deepTaskB) "Branch B should create deepening task"

    $signalsAfterB = Read-Jsonl -Path $signalsPath
    $approveRowB = $signalsAfterB | Where-Object { $_.id -eq $ApproveSignalId } | Select-Object -First 1
    Assert-Equal "approved" ([string]$approveRowB.gate_status) "Branch B signal gate_status should be approved"
    Assert-Equal $expectedDeepTaskId ([string]$approveRowB.deepening_task_id) "Branch B signal deepening_task_id mismatch"

    $deepen = Invoke-CliJson -Arguments @(
        "-m", "orchestrator.cli",
        "--data-dir", $dataDir,
        "deepen", "run",
        "--signal-id", $ApproveSignalId,
        "--vault-root", $testVault,
        "--force"
    ) -ExtraEnv $commonEnv

    $sigPathB = Join-Path $testVault ("95_Signals/" + $ApproveSignalId + ".md")
    $sigContentB = Get-Content -LiteralPath $sigPathB -Raw
    Assert-True ($sigContentB -match "## Deepened Evidence \(L3\)") "Deepened evidence heading missing in signal note"

    $tasksAfterDeepen = Read-Jsonl -Path $tasksPath
    $deepTaskDone = $tasksAfterDeepen | Where-Object { $_.id -eq $expectedDeepTaskId } | Select-Object -First 1
    Assert-Equal "completed" ([string]$deepTaskDone.status) "Deepening task should be completed"

    $signalsAfterDeepen = Read-Jsonl -Path $signalsPath
    $approveRowDeep = $signalsAfterDeepen | Where-Object { $_.id -eq $ApproveSignalId } | Select-Object -First 1
    Assert-True ([bool]$approveRowDeep.deepened) "Signal deepened should be true"
    Assert-True (-not [string]::IsNullOrWhiteSpace([string]$approveRowDeep.deepened_at)) "Signal deepened_at should be set"
    $null = $summary.Add("PASS: Branch B approved + deepen assertions")

    Write-Host "[E2E] Branch C: REJECT x3 + Rule-of-Three"
    $rejectReason = "E2E reject pattern: auth boundary"
    $cosDir = Join-Path $testVault "06_Archive/COS"
    $rtiDir = Join-Path $testVault "01_RTI"
    $cosBeforeC = @(Get-ChildItem -LiteralPath $cosDir -Filter "COS-*.md" -File).Count
    $rtiBeforeC = @(Get-ChildItem -LiteralPath $rtiDir -Filter "RTI-*.md" -File).Count

    $patternKey = $null
    $linkedRti = $null

    for ($i = 1; $i -le 3; $i++) {
        $beforeLoopCos = @(Get-ChildItem -LiteralPath $cosDir -Filter "COS-*.md" -File).Count

        $rejectPayload = Invoke-CliJson -Arguments @(
            "-m", "orchestrator.cli",
            "--data-dir", $dataDir,
            "gate", "decide",
            "--signal-id", $RejectSignalId,
            "--decision", "reject",
            "--priority", "Low",
            "--reason", $rejectReason
        ) -ExtraEnv $commonEnv

        $afterLoopCos = @(Get-ChildItem -LiteralPath $cosDir -Filter "COS-*.md" -File).Count
        Assert-Equal ($beforeLoopCos + 1) $afterLoopCos "Branch C iteration $i should increment COS count"

        if (-not $patternKey) {
            $patternKey = [string]$rejectPayload.pattern_key
        }
        Assert-Equal $patternKey ([string]$rejectPayload.pattern_key) "Branch C iteration $i pattern_key should be stable"

        $cosIndexPath = Join-Path $dataDir "cos_index.json"
        Assert-True (Test-Path -LiteralPath $cosIndexPath) "cos_index.json should exist"
        $cosIndex = Get-Content -LiteralPath $cosIndexPath -Raw | ConvertFrom-Json
        $samePattern = @($cosIndex | Where-Object { $_.pattern_key -eq $patternKey })
        Assert-True ($samePattern.Count -ge $i) "cos_index should accumulate pattern entries"
    }

    $rtiAfter3 = @(Get-ChildItem -LiteralPath $rtiDir -Filter "RTI-*.md" -File)
    Assert-Equal ($rtiBeforeC + 1) $rtiAfter3.Count "Third reject should trigger exactly one RTI"

    $newRtiFile = $rtiAfter3 | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $newRtiText = Get-Content -LiteralPath $newRtiFile.FullName -Raw
    Assert-True ($newRtiText -match "status:\s*under_review") "RTI should have under_review status"
    Assert-True ($newRtiText -match ("trigger_pattern_key:\s*" + [regex]::Escape($patternKey))) "RTI trigger_pattern_key mismatch"

    $rtiId = [System.IO.Path]::GetFileNameWithoutExtension($newRtiFile.Name)
    $tasksAfterRti = Read-Jsonl -Path $tasksPath
    $validateTaskId = "ACT-VALIDATE-$rtiId"
    $validateTask = $tasksAfterRti | Where-Object { $_.id -eq $validateTaskId } | Select-Object -First 1
    Assert-True ($null -ne $validateTask) "Validation task should be created"
    Assert-Equal "rti_validation" ([string]$validateTask.type) "Validation task type mismatch"
    Assert-Equal "pending" ([string]$validateTask.status) "Validation task status mismatch"

    $cosIndexFinal = Get-Content -LiteralPath (Join-Path $dataDir "cos_index.json") -Raw | ConvertFrom-Json
    $patternEntries = @($cosIndexFinal | Where-Object { $_.pattern_key -eq $patternKey })
    Assert-True ($patternEntries.Count -ge 3) "Expected at least 3 cos_index entries for pattern"
    foreach ($entry in $patternEntries) {
        Assert-Equal $rtiId ([string]$entry.linked_rti) "All matched cos_index entries should link same RTI"
    }

    $rtiCountBefore4 = @(Get-ChildItem -LiteralPath $rtiDir -Filter "RTI-*.md" -File).Count
    $validateCountBefore4 = @((Read-Jsonl -Path $tasksPath) | Where-Object { $_.id -eq $validateTaskId }).Count
    $cosCountBefore4 = @(Get-ChildItem -LiteralPath $cosDir -Filter "COS-*.md" -File).Count

    $reject4 = Invoke-CliJson -Arguments @(
        "-m", "orchestrator.cli",
        "--data-dir", $dataDir,
        "gate", "decide",
        "--signal-id", $RejectSignalId,
        "--decision", "reject",
        "--priority", "Low",
        "--reason", $rejectReason
    ) -ExtraEnv $commonEnv

    $rtiCountAfter4 = @(Get-ChildItem -LiteralPath $rtiDir -Filter "RTI-*.md" -File).Count
    $validateCountAfter4 = @((Read-Jsonl -Path $tasksPath) | Where-Object { $_.id -eq $validateTaskId }).Count
    $cosCountAfter4 = @(Get-ChildItem -LiteralPath $cosDir -Filter "COS-*.md" -File).Count

    Assert-Equal ($cosCountBefore4 + 1) $cosCountAfter4 "4th reject should still create COS"
    Assert-Equal $rtiCountBefore4 $rtiCountAfter4 "4th reject must not create additional RTI"
    Assert-Equal $validateCountBefore4 $validateCountAfter4 "4th reject must not create duplicate validation task"
    Assert-Equal $rtiId ([string]$reject4.linked_rti) "4th reject COS should link existing RTI"
    $null = $summary.Add("PASS: Branch C reject + Rule-of-Three assertions")

    Write-Host ""
    Write-Host "========== E2E PASS ==========" -ForegroundColor Green
    foreach ($line in $summary) {
        Write-Host $line -ForegroundColor Green
    }
    exit 0
}
catch {
    Write-Host ""
    Write-Host "========== E2E FAIL ==========" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($_.ScriptStackTrace) {
        Write-Host $_.ScriptStackTrace -ForegroundColor DarkRed
    }
    exit 1
}
finally {
    if (Test-Path -LiteralPath $tempSources) {
        Remove-Item -LiteralPath $tempSources -Force -ErrorAction SilentlyContinue
    }

    if (-not $skipCleanup) {
        if (Test-Path -LiteralPath $testVault) {
            Remove-Item -LiteralPath $testVault -Recurse -Force -ErrorAction SilentlyContinue
        }
        if (Test-Path -LiteralPath $dataDir) {
            Remove-Item -LiteralPath $dataDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    else {
        Write-Host "[E2E] Cleanup skipped (PM_OS_E2E_SKIP_CLEANUP=1)."
    }
}
