<#!
Cross-platform wrapper.
Preferred invocation:
  python scripts/e2e_three_branch_flow.py --offline
#>

[CmdletBinding()]
param(
    [switch]$Offline,
    [string]$NowIso,
    [switch]$KeepRun
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$argsList = @("scripts/e2e_three_branch_flow.py")
if ($Offline) { $argsList += "--offline" }
if ($NowIso) { $argsList += @("--now-iso", $NowIso) }
if ($KeepRun) { $argsList += "--keep-run" }

& python @argsList
exit $LASTEXITCODE
