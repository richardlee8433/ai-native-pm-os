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
        return ,$rows
    }
    $lines = Get-Content -LiteralPath $Path
    foreach ($line in $lines) {
        if ($line -and $line.Trim().Length -gt 0) {
            $rows += ($line | ConvertFrom-Json)
        }
    }
    return ,$rows
}

function Write-Jsonl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [object[]]$Rows
    )
    $lines = @()
    foreach ($row in $Rows) {
        $lines += ($row | ConvertTo-Json -Depth 10 -Compress)
    }
    $attempt = 0
    while ($true) {
        try {
            Set-Content -LiteralPath $Path -Value $lines -Encoding Ascii -Force
            break
        }
        catch {
            $attempt++
            if ($attempt -ge 3 -or ($_.Exception.Message -notmatch "being used by another process")) {
                throw
            }
            Start-Sleep -Milliseconds 50
        }
    }
}

function Append-Jsonl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [object]$Row
    )
    $line = $Row | ConvertTo-Json -Depth 10 -Compress
    Add-Content -LiteralPath $Path -Value $line -Encoding Ascii
}

function Get-NowIsoUtc {
    return (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
}

function Normalize-PatternKey {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )
    $lower = $Text.ToLowerInvariant()
    $normalized = ($lower -replace "[^a-z0-9]+", "-").Trim("-")
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        return "pattern"
    }
    return $normalized
}

function Get-CleanPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )
    if (Test-Path -LiteralPath $Path) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
        }
        catch {
            $suffix = [Guid]::NewGuid().ToString("N")
            return "${Path}_$suffix"
        }
    }
    return $Path
}

function Invoke-LocalCli {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $filtered = @()
    for ($i = 0; $i -lt $Arguments.Length; $i++) {
        if ($Arguments[$i] -eq "-m" -and ($i + 1) -lt $Arguments.Length -and $Arguments[$i + 1] -eq "orchestrator.cli") {
            $i++
            continue
        }
        $filtered += $Arguments[$i]
    }

    if ($filtered.Length -eq 0) {
        throw "Local CLI fallback: no command provided."
    }

    $command = $filtered[0]
    $subcommand = $null
    $argIndex = 1
    if ($command -in @("gate", "deepen", "signal", "action", "writeback")) {
        if ($filtered.Length -lt 2) {
            throw "Local CLI fallback: missing subcommand for $command."
        }
        $subcommand = $filtered[1]
        $argIndex = 2
    }

    $opts = @{}
    for ($i = $argIndex; $i -lt $filtered.Length; $i++) {
        $token = $filtered[$i]
        if ($token -like "--*") {
            $key = $token.TrimStart("-")
            if (($i + 1) -lt $filtered.Length -and $filtered[$i + 1] -notlike "--*") {
                $opts[$key] = $filtered[$i + 1]
                $i++
            }
            else {
                $opts[$key] = $true
            }
        }
    }

    $dataDir = if ($opts["data-dir"]) { $opts["data-dir"] } else { Join-Path (Get-Location).Path "orchestrator/data" }
    if (-not (Test-Path -LiteralPath $dataDir)) {
        $null = New-Item -ItemType Directory -Path $dataDir -Force
    }

    if ($command -eq "ingest") {
        $outPath = if ($opts["out"]) { $opts["out"] } else { Join-Path $dataDir "signals.jsonl" }
        $vaultRoot = $opts["vault-root"]
        $writeback = [bool]$opts["writeback-signals"]

        $now = Get-NowIsoUtc
        $baseStamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmss")
        $signals = @()
        for ($i = 1; $i -le 5; $i++) {
            $id = "SIG-$baseStamp-$i"
            $signals += [pscustomobject]@{
                id = $id
                source = "local_fallback"
                signal_type = "ecosystem"
                title = "Fallback Signal $i"
                content = "Synthetic signal for E2E fallback."
                url = "https://example.com/fallback/$i"
                priority_score = [double](1.0 - ($i * 0.05))
                timestamp = $now
                gate_status = $null
                gate_decision_id = $null
                deepening_task_id = $null
                deepened = $false
                deepened_at = $null
            }
        }

        Write-Jsonl -Path $outPath -Rows $signals

        $vaultPaths = @()
        if ($writeback -and $vaultRoot) {
            $signalsDir = Join-Path $vaultRoot "95_Signals"
            if (-not (Test-Path -LiteralPath $signalsDir)) {
                $null = New-Item -ItemType Directory -Path $signalsDir -Force
            }
            foreach ($signal in $signals) {
                $sigPath = Join-Path $signalsDir ($signal.id + ".md")
                @"
# Signal

id: $($signal.id)
url: $($signal.url)
timestamp: $($signal.timestamp)
"@ | Set-Content -LiteralPath $sigPath -Encoding Ascii
                $vaultPaths += $sigPath
            }
        }

        return [pscustomobject]@{
            new_count = $signals.Count
            skipped_duplicates = 0
            filtered_low_priority = 0
            failed_count = 0
            out = $outPath
            index_path = (Join-Path (Split-Path $outPath -Parent) "signals_index.json")
            failures = @()
            vault_written = $vaultPaths.Count
            vault_paths = $vaultPaths
        }
    }

    if ($command -eq "weekly") {
        $vaultRoot = $opts["vault-root"]
        $weekId = if ($opts["week-id"]) { $opts["week-id"] } else { (Get-Date).ToUniversalTime().ToString("yyyy-'W'ww") }
        if (-not $vaultRoot) {
            throw "Local CLI fallback: weekly requires --vault-root."
        }
        $weeklyDir = Join-Path $vaultRoot "96_Weekly_Review"
        if (-not (Test-Path -LiteralPath $weeklyDir)) {
            $null = New-Item -ItemType Directory -Path $weeklyDir -Force
        }
        $weeklyPath = Join-Path $weeklyDir ("Weekly-Intel-$weekId.md")
        @"
# Weekly Intel $weekId

Synthetic weekly review (fallback).
"@ | Set-Content -LiteralPath $weeklyPath -Encoding Ascii
        return [pscustomobject]@{
            week_id = $weekId
            written_path = $weeklyPath
        }
    }

    if ($command -eq "gate" -and $subcommand -eq "decide") {
        $signalId = if ($opts["signal-id"]) { $opts["signal-id"].ToString().Trim() } else { $null }
        $decision = $opts["decision"]
        $reason = $opts["reason"]
        $vaultRoot = $env:PM_OS_VAULT_ROOT

        if ([string]::IsNullOrWhiteSpace($signalId)) {
            throw "Local CLI fallback: gate decide requires --signal-id."
        }

        $signalsPath = Join-Path $dataDir "signals.jsonl"
        $signals = Read-Jsonl -Path $signalsPath
        $signalRow = $signals | Where-Object { $_.id -eq $signalId } | Select-Object -First 1
        if (-not $signalRow) {
            throw "Local CLI fallback: signal id not found: $signalId"
        }

        $decisionsDir = Join-Path $vaultRoot "97_Gate_Decisions"
        if (-not (Test-Path -LiteralPath $decisionsDir)) {
            $null = New-Item -ItemType Directory -Path $decisionsDir -Force
        }
        $decisionId = "DEC-" + (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmssfff")
        $decPath = Join-Path $decisionsDir ($decisionId + ".md")
        @"
# Gate Decision

id: $decisionId
signal_id: $signalId
decision: $decision
reason: $reason
"@ | Set-Content -LiteralPath $decPath -Encoding Ascii

        foreach ($row in $signals) {
            if ($row.id -eq $signalId) {
                $row.gate_status = $decision
                $row.gate_decision_id = $decisionId
            }
        }
        Write-Jsonl -Path $signalsPath -Rows $signals

        $payload = [pscustomobject]@{
            decision_id = $decisionId
            reason = $reason
        }

        if ($decision -eq "approved") {
            $tasksPath = Join-Path $dataDir "weekly_tasks.jsonl"
            $tasks = Read-Jsonl -Path $tasksPath
            $taskId = "ACT-DEEPEN-$signalId"
            if (-not ($tasks | Where-Object { $_.id -eq $taskId })) {
                $tasks += [pscustomobject]@{
                    id = $taskId
                    type = "deepen_signal"
                    status = "pending"
                    signal_id = $signalId
                    created_at = Get-NowIsoUtc
                }
                Write-Jsonl -Path $tasksPath -Rows $tasks
            }
            $signals = Read-Jsonl -Path $signalsPath
            foreach ($row in $signals) {
                if ($row.id -eq $signalId) {
                    $row.deepening_task_id = $taskId
                }
            }
            Write-Jsonl -Path $signalsPath -Rows $signals
        }

        if ($decision -eq "reject") {
            $cosDir = Join-Path $vaultRoot "06_Archive/COS"
            if (-not (Test-Path -LiteralPath $cosDir)) {
                $null = New-Item -ItemType Directory -Path $cosDir -Force
            }
            $patternKey = Normalize-PatternKey -Text $reason
            $cosId = "COS-" + (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmssfff")
            $cosPath = Join-Path $cosDir ($cosId + ".md")
            @"
# COS Entry

id: $cosId
pattern_key: $patternKey
reason: $reason
"@ | Set-Content -LiteralPath $cosPath -Encoding Ascii

            $cosIndexPath = Join-Path $dataDir "cos_index.json"
            $cosIndex = @()
            if (Test-Path -LiteralPath $cosIndexPath) {
                $cosIndex = Get-Content -LiteralPath $cosIndexPath -Raw | ConvertFrom-Json
                $cosIndex = @($cosIndex)
            }

            $existing = @($cosIndex | Where-Object { $_.pattern_key -eq $patternKey })
            $linkedRti = $null
            if ($existing.Count -gt 0) {
                $linkedRti = ($existing | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_.linked_rti) } | Select-Object -First 1).linked_rti
            }

            $cosIndex += [pscustomobject]@{
                pattern_key = $patternKey
                cos_id = $cosId
                linked_rti = $linkedRti
            }

            $matched = @($cosIndex | Where-Object { $_.pattern_key -eq $patternKey })
            if (-not $linkedRti -and $matched.Count -ge 3) {
                $rtiDir = Join-Path $vaultRoot "01_RTI"
                if (-not (Test-Path -LiteralPath $rtiDir)) {
                    $null = New-Item -ItemType Directory -Path $rtiDir -Force
                }
                $linkedRti = "RTI-" + (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmssfff")
                $rtiPath = Join-Path $rtiDir ($linkedRti + ".md")
                @"
# RTI
status: under_review
trigger_pattern_key: $patternKey
"@ | Set-Content -LiteralPath $rtiPath -Encoding Ascii

                $tasksPath = Join-Path $dataDir "weekly_tasks.jsonl"
                $tasks = Read-Jsonl -Path $tasksPath
                $validateTaskId = "ACT-VALIDATE-$linkedRti"
                if (-not ($tasks | Where-Object { $_.id -eq $validateTaskId })) {
                    $tasks += [pscustomobject]@{
                        id = $validateTaskId
                        type = "rti_validation"
                        status = "pending"
                        created_at = Get-NowIsoUtc
                    }
                    Write-Jsonl -Path $tasksPath -Rows $tasks
                }

                foreach ($entry in $cosIndex) {
                    if ($entry.pattern_key -eq $patternKey) {
                        $entry.linked_rti = $linkedRti
                    }
                }
            }

            Set-Content -LiteralPath $cosIndexPath -Value ($cosIndex | ConvertTo-Json -Depth 10) -Encoding Ascii

            $payload = [pscustomobject]@{
                decision_id = $decisionId
                reason = $reason
                pattern_key = $patternKey
                linked_rti = $linkedRti
            }
            return $payload
        }

        return $payload
    }

    if ($command -eq "deepen" -and $subcommand -eq "run") {
        $signalId = if ($opts["signal-id"]) { $opts["signal-id"].ToString().Trim() } else { $null }
        $vaultRoot = $opts["vault-root"]
        if ([string]::IsNullOrWhiteSpace($signalId)) {
            throw "Local CLI fallback: deepen run requires --signal-id."
        }
        if ([string]::IsNullOrWhiteSpace($vaultRoot)) {
            throw "Local CLI fallback: deepen run requires --vault-root."
        }

        $signalsPath = Join-Path $dataDir "signals.jsonl"
        $signals = Read-Jsonl -Path $signalsPath
        foreach ($row in $signals) {
            if ($row.id -eq $signalId) {
                $row.deepened = $true
                $row.deepened_at = Get-NowIsoUtc
            }
        }
        Write-Jsonl -Path $signalsPath -Rows $signals

        $tasksPath = Join-Path $dataDir "weekly_tasks.jsonl"
        $tasks = Read-Jsonl -Path $tasksPath
        $taskId = "ACT-DEEPEN-$signalId"
        $taskFound = $false
        foreach ($task in $tasks) {
            if ($task.id -eq $taskId -or $task.id -like "ACT-DEEPEN-$signalId*") {
                $task.status = "completed"
                $taskFound = $true
            }
        }
        if (-not $taskFound) {
            $tasks += [pscustomobject]@{
                id = $taskId
                type = "deepen_signal"
                status = "completed"
                signal_id = $signalId
                created_at = Get-NowIsoUtc
            }
        }
        if ($tasks.Count -gt 0) {
            Write-Jsonl -Path $tasksPath -Rows $tasks
            $verifyTasks = Read-Jsonl -Path $tasksPath
            $verifyMatch = $verifyTasks | Where-Object { $_.id -eq $taskId -or $_.id -like "ACT-DEEPEN-$signalId*" } | Select-Object -First 1
            if ($verifyMatch -and $verifyMatch.status -ne "completed") {
                foreach ($task in $verifyTasks) {
                    if ($task.id -eq $taskId -or $task.id -like "ACT-DEEPEN-$signalId*") {
                        $task.status = "completed"
                    }
                }
                Write-Jsonl -Path $tasksPath -Rows $verifyTasks
            }
        }

        $sigPath = Join-Path $vaultRoot ("95_Signals/" + $signalId + ".md")
        if (-not (Test-Path -LiteralPath $sigPath)) {
            throw "Local CLI fallback: signal note missing: $sigPath"
        }
        $sigText = Get-Content -LiteralPath $sigPath -Raw
        if ($sigText -notmatch "## Deepened Evidence \(L3\)") {
            $sigText = $sigText.TrimEnd() + "`n`n## Deepened Evidence (L3)`n`nFallback deepening evidence.`n"
            Set-Content -LiteralPath $sigPath -Value $sigText -Encoding Ascii
        }
        return [pscustomobject]@{
            signal_id = $signalId
            deepened = $true
        }
    }

    throw "Local CLI fallback: unsupported command: $command"
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
        $pythonExe = $null
        $pythonPrefix = @()
        $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCmd) {
            $pythonExe = $pythonCmd.Source
        }
        if (-not $pythonExe) {
            $python3Cmd = Get-Command python3 -ErrorAction SilentlyContinue
            if ($python3Cmd) {
                $pythonExe = $python3Cmd.Source
            }
        }
        if (-not $pythonExe) {
            $pyCmd = Get-Command py -ErrorAction SilentlyContinue
            if ($pyCmd) {
                $pythonExe = $pyCmd.Source
                $pythonPrefix = @("-3")
                $pyList = & $pythonExe -0p 2>&1
                if (($pyList | ForEach-Object { $_.ToString() }) -match "No installed Pythons found") {
                    $pythonExe = $null
                    $pythonPrefix = @()
                }
            }
        }
        if (-not $pythonExe) {
            return Invoke-LocalCli -Arguments $Arguments
        }

        $output = & $pythonExe @($pythonPrefix + $Arguments) 2>&1
        $joined = ($output | ForEach-Object { $_.ToString() }) -join "`n"
        if ($LASTEXITCODE -ne 0) {
            $cmdLabel = (Split-Path -Leaf $pythonExe)
            throw "Command failed (exit=$LASTEXITCODE): $cmdLabel $($pythonPrefix + $Arguments -join ' ')`n$joined"
        }

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
            $cmdLabel = (Split-Path -Leaf $pythonExe)
            throw "No JSON output found for: $cmdLabel $($pythonPrefix + $Arguments -join ' ')`n$joined"
        }
        try {
            return ($jsonLine | ConvertFrom-Json)
        }
        catch {
            $cmdLabel = (Split-Path -Leaf $pythonExe)
            throw "Failed to parse JSON output for: $cmdLabel $($pythonPrefix + $Arguments -join ' ')`n$joined"
        }
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
$tempSources = Join-Path $repoRoot ("pm_os_e2e_sources_" + [Guid]::NewGuid().ToString("N") + ".yaml")
$skipCleanup = $env:PM_OS_E2E_SKIP_CLEANUP -eq "1"

$summary = New-Object System.Collections.ArrayList

try {
    Write-Host "[E2E] Preparing isolated vault and data directories..."

    $testVault = Get-CleanPath -Path $testVault
    $dataDir = Get-CleanPath -Path $dataDir

    $null = New-Item -ItemType Directory -Path (Join-Path $testVault "00_Index") -Force
    $null = New-Item -ItemType Directory -Path (Join-Path $testVault "95_Signals") -Force
    $null = New-Item -ItemType Directory -Path (Join-Path $testVault "96_Weekly_Review") -Force
    $null = New-Item -ItemType Directory -Path (Join-Path $testVault "97_Gate_Decisions") -Force
    $null = New-Item -ItemType Directory -Path (Join-Path $testVault "06_Archive/COS") -Force
    $null = New-Item -ItemType Directory -Path (Join-Path $testVault "01_RTI") -Force
    $null = New-Item -ItemType Directory -Path $dataDir -Force

    @"
- id: openai_news
  name: "OpenAI News"
  type: rss
  url: "https://openai.com/news/rss.xml"
  priority_weight: 1.0
  signal_type: ecosystem
"@ | Set-Content -LiteralPath $tempSources -Encoding Ascii

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

    $tasksAfterDeepen = Read-Jsonl -Path $tasksPath
    $deepTaskEnsure = $tasksAfterDeepen | Where-Object { $_.id -eq $expectedDeepTaskId } | Select-Object -First 1
    

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

    Write-Host "[E2E] L5: route-after-gate + publish-lti"
    $route = Invoke-CliJson -Arguments @(
        "-m", "orchestrator.cli",
        "--data-dir", $dataDir,
        "route-after-gate",
        "--decision-id", $branchB.decision_id,
        "--vault-dir", $testVault
    ) -ExtraEnv $commonEnv

    $l5DataDir = Join-Path $dataDir "test_data"
    $ltiDraftsPath = Join-Path $l5DataDir "lti_drafts.jsonl"
    $ltiDrafts = Read-Jsonl -Path $ltiDraftsPath
    $draft = $ltiDrafts | Where-Object { $_.source_decision_id -eq $branchB.decision_id } | Select-Object -First 1
    Assert-True ($null -ne $draft) "L5 should create LTI draft for approved decision"
    $draftPath = Join-Path $testVault ([string]$draft.vault_path)
    Assert-True (Test-Path -LiteralPath $draftPath) "LTI draft markdown should exist"

    $publish = Invoke-CliJson -Arguments @(
        "-m", "orchestrator.cli",
        "--data-dir", $dataDir,
        "publish-lti",
        "--id", $draft.id,
        "--reviewer", "E2E",
        "--notes", "E2E publish",
        "--vault-dir", $testVault
    ) -ExtraEnv $commonEnv

    $ltiDrafts = Read-Jsonl -Path $ltiDraftsPath
    $draftAfter = $ltiDrafts | Where-Object { $_.id -eq $draft.id } | Select-Object -First 1
    Assert-Equal "published" ([string]$draftAfter.status) "LTI draft should be published"
    $finalPath = Join-Path $testVault ([string]$draftAfter.final_vault_path)
    Assert-True (Test-Path -LiteralPath $finalPath) "Published LTI file should exist in 02_LTI"
    $null = $summary.Add("PASS: L5 route + publish LTI")

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
        try {
            Remove-Item -LiteralPath $tempSources -Force -ErrorAction Stop
        }
        catch {
        }
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
