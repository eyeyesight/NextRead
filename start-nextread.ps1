[CmdletBinding()]
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$projectPath = $PSScriptRoot
$dockerDesktopPath = Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\Docker Desktop.exe"
$dockerPath = Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\resources\bin\docker.exe"
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

function Invoke-DockerCommand {
    param(
        [string]$Arguments,
        [int]$TimeoutMilliseconds,
        [string]$LogName
    )

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $dockerPath
    $startInfo.Arguments = $Arguments
    $startInfo.WorkingDirectory = $projectPath
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    $process.Start() | Out-Null
    $standardOutput = $process.StandardOutput.ReadToEndAsync()
    $standardError = $process.StandardError.ReadToEndAsync()

    if (-not $process.WaitForExit($TimeoutMilliseconds)) {
        $process.Kill()
        $process.WaitForExit()
        return 124
    }

    $standardOutput.Wait()
    $standardError.Wait()
    [System.IO.File]::WriteAllText(
        (Join-Path $logPath "$LogName.out.log"),
        $standardOutput.Result,
        [System.Text.UTF8Encoding]::new($true)
    )
    [System.IO.File]::WriteAllText(
        (Join-Path $logPath "$LogName.err.log"),
        $standardError.Result,
        [System.Text.UTF8Encoding]::new($true)
    )
    return $process.ExitCode
}

function Test-DockerReady {
    return (Invoke-DockerCommand "info" 5000 "docker-info") -eq 0
}

function Stop-ExistingStreamlit {
    Write-LauncherStatus "正在重新啟動分析介面..."
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
    throw "舊的分析介面仍占用 $appUrl。請關閉占用 8501 連接埠的程式後再試一次。"
}

try {
    Set-Location -LiteralPath $projectPath
    Write-LauncherStatus "正在啟動 NextRead..." Cyan

    if (-not (Test-Path -LiteralPath $dockerPath)) {
        throw "找不到 Docker 命令列工具：$dockerPath"
    }

    if (-not (Test-DockerReady)) {
        if (-not (Test-Path -LiteralPath $dockerDesktopPath)) {
            throw "找不到 Docker Desktop：$dockerDesktopPath"
        }
        Write-LauncherStatus "正在啟動 Docker Desktop，第一次啟動可能需要一分鐘。"
        Start-Process -FilePath $dockerDesktopPath -WindowStyle Hidden
        $dockerReady = $false
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            Start-Sleep -Seconds 2
            if (Test-DockerReady) {
                $dockerReady = $true
                break
            }
        }
        if (-not $dockerReady) {
            throw "Docker Desktop 未能在兩分鐘內啟動。請開啟 Docker Desktop 查看狀態。"
        }
    }

    Write-LauncherStatus "正在確認 GROBID 服務..."
    $composeExitCode = Invoke-DockerCommand "compose up -d grobid" 60000 "docker-compose"
    if ($composeExitCode -eq 124) {
        throw "GROBID 啟動逾時。詳細內容已寫入 logs\docker-compose.err.log。"
    }
    if ($composeExitCode -ne 0) {
        throw "GROBID 啟動失敗。詳細內容已寫入 logs\docker-compose.err.log。"
    }

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
        throw "分析介面未能在 45 秒內啟動。請查看 logs 資料夾中的啟動紀錄。"
    }

    if ($NoBrowser) {
        Write-LauncherStatus "啟動檢查完成。" Green
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
