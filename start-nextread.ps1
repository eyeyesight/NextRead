[CmdletBinding()]
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$projectPath = $PSScriptRoot
$streamlitPath = Join-Path $projectPath ".venv\Scripts\streamlit.exe"
$pythonPath = Join-Path $projectPath ".venv\Scripts\python.exe"
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

function Stop-ExistingStreamlit {
    Write-LauncherStatus "正在重新啟動 NextRead..."
    $processIds = @()

    if (Test-Path -LiteralPath $streamlitPidPath) {
        $savedPid = 0
        if ([int]::TryParse((Get-Content -LiteralPath $streamlitPidPath -Raw).Trim(), [ref]$savedPid)) {
            $processIds += $savedPid
        }
    }

    $projectProcesses = Get-Process -Name "python", "streamlit" -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $pythonPath -or $_.Path -eq $streamlitPath }
    $processIds += $projectProcesses.Id

    foreach ($processId in ($processIds | Sort-Object -Unique)) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $streamlitPidPath -Force -ErrorAction SilentlyContinue

    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        if (-not (Test-HttpEndpoint "$appUrl/_stcore/health")) {
            return
        }
        Start-Sleep -Milliseconds 250
    }
    throw "無法使用 $appUrl。請先關閉占用 8501 連接埠的程式，再試一次。"
}

try {
    Set-Location -LiteralPath $projectPath
    Write-LauncherStatus "正在啟動 NextRead..." Cyan

    if (-not (Test-Path -LiteralPath $streamlitPath)) {
        throw "找不到 Streamlit：$streamlitPath"
    }
    Stop-ExistingStreamlit
    $streamlitProcess = Start-Process -FilePath $streamlitPath `
        -ArgumentList @("run", "app.py", "--server.port", "8501", "--server.headless", "true") `
        -WorkingDirectory $projectPath `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logPath "streamlit-launcher.out.log") `
        -RedirectStandardError (Join-Path $logPath "streamlit-launcher.err.log") `
        -PassThru
    Set-Content -LiteralPath $streamlitPidPath -Value $streamlitProcess.Id -Encoding ASCII

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
