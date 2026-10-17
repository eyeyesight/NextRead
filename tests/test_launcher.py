"""Exercise launcher identity checks without starting or stopping real processes."""

import base64
from pathlib import Path
import shutil
import subprocess

import pytest


POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh")


@pytest.mark.skipif(not POWERSHELL, reason="PowerShell is required for launcher tests")
def test_launcher_stops_only_verified_nextread_processes():
    launcher = Path(__file__).resolve().parents[1] / "start-nextread.ps1"
    script = r"""
$ErrorActionPreference = 'Stop'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile('__LAUNCHER__', [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'Launcher has syntax errors' }
$functions = $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false)
foreach ($function in $functions) { . ([scriptblock]::Create($function.Extent.Text)) }
$pythonPath = 'C:\Next Read\.venv\Scripts\python.exe'
$appPath = 'C:\Next Read\app.py'
$valid = [pscustomobject]@{
    ProcessId = 101
    ExecutablePath = $pythonPath
    CommandLine = '"C:\Next Read\.venv\Scripts\python.exe" -m streamlit run "C:\Next Read\app.py" --server.port 8501 --server.headless true'
    CreationDate = [datetime]'2026-10-17T08:00:00Z'
}
if (-not (Test-NextReadProcess $valid $pythonPath $appPath)) { throw 'Real NextRead command was rejected' }
foreach ($command in @(
    '"C:\Next Read\.venv\Scripts\python.exe" -m pytest',
    '"C:\Next Read\.venv\Scripts\python.exe" scripts\benchmark.py',
    '"C:\Next Read\.venv\Scripts\python.exe" -m streamlit run "C:\Other\app.py" --server.port 8501 --server.headless true',
    '"C:\Next Read\.venv\Scripts\python.exe" -m streamlit run app.py --server.port 8501 --server.headless true',
    '"C:\Next Read\.venv\Scripts\python.exe" -m streamlit run "C:\Next Read\app.py" --server.port 8502 --server.headless true'
)) {
    $other = $valid.PSObject.Copy()
    $other.CommandLine = $command
    if (Test-NextReadProcess $other $pythonPath $appPath) { throw "Unrelated command accepted: $command" }
}
$foreign = $valid.PSObject.Copy()
$foreign.ExecutablePath = 'C:\Other\python.exe'
if (Test-NextReadProcess $foreign $pythonPath $appPath) { throw 'Foreign executable accepted' }
$startTime = Get-NextReadStartTime $valid
if (-not (Test-NextReadProcess $valid $pythonPath $appPath $startTime)) { throw 'Saved identity rejected' }
$reused = $valid.PSObject.Copy()
$reused.CreationDate = $valid.CreationDate.AddMinutes(1)
if (Test-NextReadProcess $reused $pythonPath $appPath $startTime) { throw 'Reused PID accepted' }

# Exercise the stop workflow with every OS operation replaced by a fake.
$streamlitPidPath = 'fake.pid'
$appUrl = 'http://localhost:8501'
$script:stopped = @()
$script:portReads = 0
$script:foreignOwner = $false
$script:changedIdentity = $false
$script:savedState = $null
$script:delayedReads = 0
$child = $valid.PSObject.Copy()
$child.ProcessId = 102
$child | Add-Member -NotePropertyName ParentProcessId -NotePropertyValue 101
$child.ExecutablePath = 'C:\Base Python\python.exe'
$child.CommandLine = '"C:\Base Python\python.exe" -m streamlit run "C:\Next Read\app.py" --server.port 8501 --server.headless true'
function Write-LauncherStatus { param($Message) }
function Test-Path { param($LiteralPath) return $null -ne $script:savedState }
function Get-Content { param($LiteralPath, [switch]$Raw) return $script:savedState }
function Remove-Item { param($LiteralPath, [switch]$Force, $ErrorAction) }
function Start-Sleep { param($Milliseconds) }
function Stop-Process { param($Id, [switch]$Force, $ErrorAction) $script:stopped += $Id }
function Get-CimInstance {
    param($ClassName, $Filter)
    if ($Filter -like 'Name*') { return @($valid, $other, $foreign, $child) }
    if ($script:delayedReads -gt 0) { $script:delayedReads--; return $null }
    if ($Filter -eq 'ProcessId = 102') { return $child }
    if ($script:changedIdentity) { return $reused }
    return $valid
}
function Get-NextReadPortOwners {
    $script:portReads++
    if ($script:foreignOwner) { return @(999) }
    if ($script:portReads -eq 1) { return @(102) }
    return @()
}
$script:delayedReads = 2
$started = Wait-NextReadProcess 101 $pythonPath $appPath
if (-not $started -or $script:delayedReads) { throw 'Delayed CIM process registration was not retried' }
Stop-ExistingStreamlit
if ($script:stopped.Count -ne 2 -or $script:stopped[0] -ne 102 -or $script:stopped[1] -ne 101) { throw 'Stop workflow touched an unrelated process or missed the venv child' }

$script:stopped = @()
$script:foreignOwner = $true
try { Stop-ExistingStreamlit; throw 'Expected foreign listener rejection' }
catch { if ($_.Exception.Message -notlike '*999*') { throw } }
if ($script:stopped.Count) { throw 'Foreign listener caused process termination' }

$script:foreignOwner = $false
$script:portReads = 1
$script:changedIdentity = $true
$child.CommandLine = '"C:\Base Python\python.exe" scripts\benchmark.py'
Stop-ExistingStreamlit
if ($script:stopped.Count) { throw 'PID reuse between discovery and stop was not rejected' }

$script:changedIdentity = $false
$script:portReads = 0
$script:savedState = @{ ProcessId = 101; StartTime = (Get-NextReadStartTime $reused) } | ConvertTo-Json
try { Stop-ExistingStreamlit; throw 'Expected saved process identity rejection' }
 catch { if ($_.Exception.Message -notlike '*102*') { throw } }
if ($script:stopped.Count) { throw 'Stale saved PID was terminated' }
'Launcher process identity checks passed'
""".replace("__LAUNCHER__", str(launcher).replace("'", "''"))
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
