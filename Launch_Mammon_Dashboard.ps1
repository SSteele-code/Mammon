$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverScript = Join-Path $root "dashboard.py"
$dashboardIndex = Join-Path $root "dashboard\index.html"
$logDir = Join-Path $root "logs"
$logFile = Join-Path $logDir "dashboard-launch.log"
$serverOut = Join-Path $logDir "dashboard-server.out.log"
$serverErr = Join-Path $logDir "dashboard-server.err.log"
$sessionFile = Join-Path $logDir "dashboard-session.json"
$mutexName = "Local\MammonDashboardLauncherMutex"

New-Item -ItemType Directory -Path $logDir -Force | Out-Null

function Log([string]$msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
    Add-Content -Path $logFile -Value "[$ts] $msg"
}

function Rotate-Log([string]$path, [int]$maxLines = 2000) {
    if (!(Test-Path $path)) { return }
    $lines = @(Get-Content -Path $path)
    if ($lines.Count -le $maxLines) { return }
    $tail = $lines | Select-Object -Last $maxLines
    Set-Content -Path $path -Value $tail -Encoding UTF8
}

function Get-FreePort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse("127.0.0.1"), 0)
    $listener.Start()
    $port = ($listener.LocalEndpoint).Port
    $listener.Stop()
    return $port
}

function Resolve-PythonExe {
    function Test-Runtime([string]$exe) {
        try {
            & $exe -c "import flask, pandas, alpaca, dotenv; print('ok')" 1>$null 2>$null
            return ($LASTEXITCODE -eq 0)
        } catch {
            return $false
        }
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $py312Exe = $null
        try {
            $py312Exe = & $pyLauncher.Source -3.12 -c "import sys; print(sys.executable)" 2>$null
        } catch {
            $py312Exe = $null
        }
        if ($py312Exe) {
            $py312Exe = $py312Exe.Trim()
            $pyw312Exe = Join-Path (Split-Path $py312Exe -Parent) "pythonw.exe"
            if ((Test-Path $pyw312Exe) -and (Test-Runtime $pyw312Exe)) { return @{ exe = $pyw312Exe; prefix = @() } }
            if (Test-Runtime $py312Exe) { return @{ exe = $py312Exe; prefix = @() } }
        }
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
        throw "python not found on PATH"
    }

    $pyExe = & $pythonCmd.Source -c "import sys; print(sys.executable)"
    if (-not $pyExe) {
        throw "python executable resolution failed"
    }

    $pyExe = $pyExe.Trim()
    $pywExe = Join-Path (Split-Path $pyExe -Parent) "pythonw.exe"
    if ((Test-Path $pywExe) -and (Test-Runtime $pywExe)) { return @{ exe = $pywExe; prefix = @() } }
    if (Test-Runtime $pyExe) { return @{ exe = $pyExe; prefix = @() } }
    throw "No Python runtime with fastapi+uvicorn available. Install into py -3.12 and relaunch."
}

function Resolve-BrowserExe {
    $candidates = @(
        "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "C:\Program Files\Google\Chrome\Application\chrome.exe",
        "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    throw "No supported browser found (Edge/Chrome)."
}

function Read-Session {
    if (!(Test-Path $sessionFile)) { return $null }
    try {
        return (Get-Content -Raw $sessionFile | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Write-Session([int]$spid, [int]$port) {
    @{
        pid = $spid
        port = $port
        started_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    } | ConvertTo-Json | Set-Content -Path $sessionFile -Encoding UTF8
}

function Clear-Session {
    if (Test-Path $sessionFile) {
        Remove-Item -Path $sessionFile -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-Shutdown([int]$port) {
    try {
        Invoke-WebRequest -Uri ("http://127.0.0.1:$port/__shutdown") -Method POST -UseBasicParsing -TimeoutSec 1 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Stop-StaleSession {
    $s = Read-Session
    if (-not $s) { return }

    $oldPid = 0
    $oldPort = 0
    try { $oldPid = [int]$s.pid } catch {}
    try { $oldPort = [int]$s.port } catch {}

    if ($oldPort -gt 0) {
        $shutdownOk = Invoke-Shutdown -port $oldPort
        Log "stale_shutdown_request port=$oldPort ok=$shutdownOk"
        Start-Sleep -Milliseconds 500
    }

    if ($oldPid -gt 0) {
        $proc = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
        if ($proc) {
            Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
            Log "stale_pid_killed pid=$oldPid"
        }
    }

    Clear-Session
}

if (!(Test-Path $serverScript)) { throw "Missing $serverScript" }
if (!(Test-Path $dashboardIndex)) { throw "Missing $dashboardIndex" }

$serverProc = $null
$browserProc = $null
$mutex = $null
$ownsMutex = $false
$sessionOwned = $false
$port = 0

try {
    Rotate-Log -path $logFile -maxLines 2000
    Rotate-Log -path $serverOut -maxLines 3000
    Rotate-Log -path $serverErr -maxLines 3000

    $createdNew = $false
    $mutex = New-Object System.Threading.Mutex($true, $mutexName, [ref]$createdNew)
    if (-not $createdNew) {
        Log "Launcher skipped: another launcher instance is active"
        return
    }
    $ownsMutex = $true

    Log "Launcher start"
    Stop-StaleSession

    $pythonInfo = Resolve-PythonExe
    $pythonExe = $pythonInfo.exe
    $browserExe = Resolve-BrowserExe
    $port = Get-FreePort
    $url = "http://127.0.0.1:$port/"

    Log "python=$pythonExe"
    Log "browser=$browserExe"
    Log "port=$port"

    if (Test-Path $serverOut) { Remove-Item $serverOut -Force }
    if (Test-Path $serverErr) { Remove-Item $serverErr -Force }

    $env:MAMMON_DASHBOARD_PORT = "$port"
    $serverArgs = @()
    $serverArgs += $pythonInfo.prefix
    $serverArgs += @($serverScript)
    $serverProc = Start-Process -FilePath $pythonExe -ArgumentList $serverArgs -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $serverOut -RedirectStandardError $serverErr -PassThru
    Log "server_pid=$($serverProc.Id)"
    Write-Session -spid $serverProc.Id -port $port
    $sessionOwned = $true

    $ready = $false
    for ($i = 0; $i -lt 150; $i++) {
        if ($serverProc.HasExited) {
            throw "Server exited early with code $($serverProc.ExitCode)."
        }
        try {
            $r = Invoke-WebRequest -Uri ($url + "__health") -UseBasicParsing -TimeoutSec 1
            if ($r.StatusCode -eq 200) {
                $ready = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 100
        }
    }
    if (-not $ready) { throw "Server readiness timeout." }
    Log "server_ready=true"

    $browserArgs = @("--new-window", "--app=$url")
    $browserProc = Start-Process -FilePath $browserExe -ArgumentList $browserArgs -PassThru
    Log "browser_pid=$($browserProc.Id)"

    while (-not $serverProc.HasExited) {
        Start-Sleep -Milliseconds 500
        $serverProc.Refresh()
    }
    Log "server_stopped"
}
catch {
    if ($serverProc -and $serverProc.HasExited -and (Test-Path $serverErr)) {
        $stderrTail = (Get-Content -Path $serverErr -ErrorAction SilentlyContinue | Select-Object -Last 5) -join " | "
        if ($stderrTail) {
            Log ("server_err_tail=" + $stderrTail)
        }
    }
    Log ("ERROR: " + $_.Exception.Message)
    throw
}
finally {
    if ($serverProc -and -not $serverProc.HasExited) {
        if ($port -gt 0) {
            Invoke-Shutdown -port $port | Out-Null
        }
        Start-Sleep -Milliseconds 400
        Stop-Process -Id $serverProc.Id -Force
        Log "server_force_stopped"
    }
    if ($sessionOwned) {
        Clear-Session
    }
    if ($mutex -and $ownsMutex) {
        $mutex.ReleaseMutex() | Out-Null
        $mutex.Dispose()
    }
    Log "Launcher end"
}
