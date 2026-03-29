param(
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action = "start"
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$pidFile = Join-Path $root "run_all.pids.json"

$services = @(
    @{ Name = "Auth";     Script = "run_auth.ps1";     Url = "http://127.0.0.1:8001/api/v1/health" },
    @{ Name = "User";     Script = "run_user.ps1";     Url = "http://127.0.0.1:8002/api/v1/health" },
    @{ Name = "Follow";   Script = "run_follow.ps1";   Url = "http://127.0.0.1:8003/api/v1/health" },
    @{ Name = "Book";     Script = "run_book.ps1";     Url = "http://127.0.0.1:8004/api/v1/health" },
    @{ Name = "BookV2";   Script = "run_bookv2.ps1";   Url = "http://127.0.0.1:8007/api/v2/health" },
    @{ Name = "Recommendation"; Script = "run_recommendation.ps1"; Url = "http://127.0.0.1:8008/api/v1/health" },
    @{ Name = "Social";   Script = "run_social.ps1";   Url = "http://127.0.0.1:8005/api/v1/health" },
    @{ Name = "RAG";      Script = "run_rag.ps1";      Url = "http://127.0.0.1:8006/health" },
    @{ Name = "Frontend"; Script = "run_frontend.ps1"; Url = "http://127.0.0.1:8080/" }
)

function Get-TrackedProcesses {
    if (-not (Test-Path $pidFile)) {
        return @()
    }

    $raw = Get-Content -Path $pidFile -Raw
    if (-not $raw.Trim()) {
        return @()
    }

    $entries = $raw | ConvertFrom-Json
    if ($entries -isnot [System.Array]) {
        return @($entries)
    }

    return $entries
}

function Save-TrackedProcesses([array]$entries) {
    $entries | ConvertTo-Json -Depth 4 | Set-Content -Path $pidFile -Encoding UTF8
}

function Start-AllServices {
    $existing = Get-TrackedProcesses
    if ($existing.Count -gt 0) {
        Write-Host "Tracked services already exist. Run '.\\run_all.ps1 -Action status' or '-Action restart'." -ForegroundColor Yellow
        return
    }

    $started = @()
    foreach ($svc in $services) {
        $scriptPath = Join-Path $root $svc.Script
        if (-not (Test-Path $scriptPath)) {
            Write-Host "Skipping $($svc.Name): script not found ($scriptPath)" -ForegroundColor Red
            continue
        }

        $argList = @(
            "-NoExit",
            "-ExecutionPolicy", "Bypass",
            "-File", "`"$scriptPath`""
        )

        $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $argList -WorkingDirectory $root -PassThru
        $started += [PSCustomObject]@{
            name   = $svc.Name
            pid    = $proc.Id
            script = $svc.Script
            url    = $svc.Url
        }
        Start-Sleep -Milliseconds 200
    }

    if ($started.Count -gt 0) {
        Save-TrackedProcesses -entries $started
        Write-Host "Started services in separate PowerShell windows:" -ForegroundColor Green
        $started | ForEach-Object {
            Write-Host " - $($_.name) (PID $($_.pid)) -> $($_.url)"
        }
        Write-Host "Use '.\\run_all.ps1 -Action stop' to stop all tracked windows."
    }
}

function Stop-AllServices {
    $entries = Get-TrackedProcesses
    if ($entries.Count -eq 0) {
        Write-Host "No tracked service processes found." -ForegroundColor Yellow
        return
    }

    foreach ($entry in $entries) {
        try {
            $proc = Get-Process -Id ([int]$entry.pid) -ErrorAction Stop
            Stop-Process -Id $proc.Id -Force -ErrorAction Stop
            Write-Host "Stopped $($entry.name) (PID $($entry.pid))." -ForegroundColor Green
        }
        catch {
            Write-Host "PID $($entry.pid) for $($entry.name) is not running." -ForegroundColor DarkYellow
        }
    }

    Remove-Item -Path $pidFile -ErrorAction SilentlyContinue
}

function Show-Status {
    $entries = Get-TrackedProcesses
    if ($entries.Count -eq 0) {
        Write-Host "No tracked service processes found." -ForegroundColor Yellow
        return
    }

    Write-Host "Tracked services:" -ForegroundColor Cyan
    foreach ($entry in $entries) {
        $state = "stopped"
        try {
            $null = Get-Process -Id ([int]$entry.pid) -ErrorAction Stop
            $state = "running"
        }
        catch {}

        Write-Host " - $($entry.name): PID $($entry.pid), $state, $($entry.url)"
    }
}

switch ($Action) {
    "start"   { Start-AllServices }
    "stop"    { Stop-AllServices }
    "restart" { Stop-AllServices; Start-AllServices }
    "status"  { Show-Status }
}

