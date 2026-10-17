[CmdletBinding()]
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$projectPath = $PSScriptRoot
$pythonPath = Join-Path $projectPath ".venv\Scripts\python.exe"
$appPath = Join-Path $projectPath "app.py"
$appUrl = "http://localhost:8501"
$logPath = Join-Path $projectPath "logs"
$launcherLog = Join-Path $logPath "launcher.log"
$streamlitPidPath = Join-Path $logPath "streamlit.pid"

New-Item -ItemType Directory -Path $logPath -Force | Out-Null

function Write-LauncherStatus {
    param(
        [string]$Message,
        [ConsoleColor]$Color = [ConsoleColor]::Gray
    )
    Write-Host $Message -ForegroundColor $Color
    Add-Content -LiteralPath $launcherLog -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message" -Encoding UTF8
}

function Test-HttpEndpoint {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

function Get-NextReadStartTime {
    param($Process)
    if (-not $Process.CreationDate) { return "" }
    return ([datetime]$Process.CreationDate).ToUniversalTime().Ticks.ToString()
}

function Test-NextReadProcess {
    param($Process, [string]$PythonPath, [string]$AppPath, [string]$ExpectedStartTime = "")
    if (-not $Process -or $Process.ExecutablePath -ne $PythonPath) { return $false }
    $startTime = Get-NextReadStartTime $Process
    if (-not $startTime -or ($ExpectedStartTime -and $startTime -ne $ExpectedStartTime)) { return $false }
    $executable = [regex]::Escape($PythonPath)
    $application = [regex]::Escape($AppPath)
    $command = '^\s*(?:"' + $executable + '"|' + $executable + ')\s+-m\s+streamlit\s+run\s+"' + $application + '"\s+--server.port\s+8501\s+--server.headless\s+true\s*$'
    return $Process.CommandLine -imatch $command
}

function Get-NextReadPortOwners {
    return @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
        Where-Object { $_.LocalPort -eq 8501 } |
        Select-Object -ExpandProperty OwningProcess -Unique)
}

function Wait-NextReadProcess {
    param([int]$ProcessId, [string]$PythonPath, [string]$AppPath)
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId"
        if (Test-NextReadProcess $process $PythonPath $AppPath) { return $process }
        Start-Sleep -Milliseconds 100
    }
    return $null
}

function Stop-ExistingStreamlit {
    $savedProcess = $null

    if (Test-Path -LiteralPath $streamlitPidPath) {
        try { $savedProcess = Get-Content -LiteralPath $streamlitPidPath -Raw | ConvertFrom-Json }
        catch { $savedProcess = $null }
    }

    $pythonProcesses = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'")
    $projectProcesses = @($pythonProcesses |
        Where-Object {
            $expectedStart = ""
            if ($savedProcess -and $_.ProcessId -eq $savedProcess.ProcessId) {
                $expectedStart = [string]$savedProcess.StartTime
                if (-not $expectedStart) { return $false }
            }
            Test-NextReadProcess $_ $pythonPath $appPath $expectedStart
        })
    # Windows venv launchers can forward execution to a base Python child.
    $childProcesses = @($pythonProcesses | Where-Object {
        $child = $_
        $parent = $projectProcesses | Where-Object { $_.ProcessId -eq $child.ParentProcessId } | Select-Object -First 1
        $parent -and $child.CreationDate -ge $parent.CreationDate -and
            (Test-NextReadProcess $child $child.ExecutablePath $appPath)
    })
    $projectProcesses = @($childProcesses) + @($projectProcesses)
    foreach ($ownerId in (Get-NextReadPortOwners)) {
        if ($ownerId -notin $projectProcesses.ProcessId) {
            throw "8501 連接埠已被其他程式或舊版網站占用（PID：$ownerId）。請自行關閉該程式後重試，NextRead 不會代為結束。"
        }
    }

    if ($projectProcesses.Count) { Write-LauncherStatus "正在重新啟動 NextRead..." }
    foreach ($process in $projectProcesses) {
        $current = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.ProcessId)"
        if (Test-NextReadProcess $current $process.ExecutablePath $appPath (Get-NextReadStartTime $process)) {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
        }
    }
    Remove-Item -LiteralPath $streamlitPidPath -Force -ErrorAction SilentlyContinue

    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        if (-not (Get-NextReadPortOwners)) {
            return
        }
        Start-Sleep -Milliseconds 250
    }
    throw "無法使用 $appUrl。請先關閉占用 8501 連接埠的程式，再試一次。"
}

try {
    Set-Location -LiteralPath $projectPath
    Write-LauncherStatus "正在啟動 NextRead..." Cyan

    if (-not (Test-Path -LiteralPath $pythonPath)) {
        throw "找不到 Python：$pythonPath"
    }
    Stop-ExistingStreamlit
    $streamlitProcess = Start-Process -FilePath $pythonPath `
        -ArgumentList @("-m", "streamlit", "run", ('"{0}"' -f $appPath), "--server.port", "8501", "--server.headless", "true") `
        -WorkingDirectory $projectPath `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logPath "streamlit-launcher.out.log") `
        -RedirectStandardError (Join-Path $logPath "streamlit-launcher.err.log") `
        -PassThru
    $startedProcess = Wait-NextReadProcess $streamlitProcess.Id $pythonPath $appPath
    if (-not $startedProcess) {
        throw "無法確認 NextRead 啟動程序，請查看 logs 資料夾中的啟動紀錄。"
    }
    @{ ProcessId = $startedProcess.ProcessId; StartTime = (Get-NextReadStartTime $startedProcess) } |
        ConvertTo-Json | Set-Content -LiteralPath $streamlitPidPath -Encoding ASCII

    $appReady = $false
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        Start-Sleep -Seconds 1
        if (Test-HttpEndpoint "$appUrl/_stcore/health") {
            $appReady = $true
            break
        }
    }
    if (-not $appReady) {
        throw "NextRead 未能在 45 秒內啟動。請查看 logs 資料夾中的啟動紀錄。"
    }

    if ($NoBrowser) {
        Write-LauncherStatus "NextRead 已啟動。" Green
    }
    else {
        Write-LauncherStatus "啟動完成，正在開啟瀏覽器。" Green
        Start-Process $appUrl
    }
}
catch {
    $failureMessage = "啟動失敗：$($_.Exception.Message)"
    Write-LauncherStatus $failureMessage Red
    Add-Content -LiteralPath $launcherLog -Value ($_ | Out-String) -Encoding UTF8
    exit 1
}
