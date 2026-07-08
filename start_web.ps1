<#
.SYNOPSIS
    Launch utm_moc52 Web console

.DESCRIPTION
    Auto-detect conda, check deps, start web_server.py.
    Default port 5000, use -Port to override.

.PARAMETER Port
    Web server listen port (default 5000)

.EXAMPLE
    .\start_web.ps1
    Start on port 5000

.EXAMPLE
    .\start_web.ps1 -Port 8080
    Start on port 8080
#>

param(
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# ============================================================
# 1. Locate conda
# ============================================================
$CondaPaths = @(
    "C:\ProgramData\anaconda3\Scripts\conda.exe",
    "C:\ProgramData\anaconda3\condabin\conda.bat",
    "$env:USERPROFILE\anaconda3\Scripts\conda.exe",
    "$env:USERPROFILE\miniconda3\Scripts\conda.exe"
)

$CondaExe = $null
foreach ($p in $CondaPaths) {
    if (Test-Path $p) {
        $CondaExe = $p
        break
    }
}

# Fallback: search registry
if (-not $CondaExe) {
    try {
        $RegPath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
        $Anaconda = Get-ItemProperty $RegPath | Where-Object { $_.DisplayName -like "*Anaconda*" }
        if ($Anaconda) {
            $InstallPath = $Anaconda.InstallLocation
            if ($InstallPath) {
                $Candidate = Join-Path $InstallPath "Scripts\conda.exe"
                if (Test-Path $Candidate) { $CondaExe = $Candidate }
            }
        }
    } catch { }
}

if (-not $CondaExe) {
    Write-Host "[ERROR] conda not found. Please install Anaconda/Miniconda first." -ForegroundColor Red
    exit 1
}

Write-Host "[INFO] conda: $CondaExe" -ForegroundColor Cyan

# ============================================================
# 2. Create / select conda environment
# ============================================================
$CondaDir = Split-Path -Parent (Split-Path -Parent $CondaExe)
$EnvName = "utm"
$PythonExe = Join-Path $CondaDir "envs\utm\python.exe"

# Check if 'utm' env exists
$EnvList = & $CondaExe env list 2>&1
$UtmExists = $EnvList -match "utm\s"

if (-not $UtmExists) {
    Write-Host "[INFO] Creating conda environment 'utm' (Python 3.11)..." -ForegroundColor Yellow
    & $CondaExe create -n utm python=3.11 -y 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to create 'utm' environment" -ForegroundColor Red
        exit 1
    }
    Write-Host "[INFO] Environment 'utm' created successfully" -ForegroundColor Green
} else {
    Write-Host "[INFO] Using existing 'utm' environment" -ForegroundColor Green
}

Write-Host "[INFO] conda env: $EnvName" -ForegroundColor Cyan
Write-Host "[INFO] python: $PythonExe" -ForegroundColor Cyan

# ============================================================
# 3. Check / install dependencies (批量检查，一次 conda run)
# ============================================================
$RequiredPkgs = @(
    @{Name="flask"; Pip="flask"},
    @{Name="flask_socketio"; Pip="flask-socketio"},
    @{Name="redis"; Pip="redis"},
    @{Name="kafka"; Pip="kafka-python"},
    @{Name="pydantic"; Pip="pydantic"},
    @{Name="pytest"; Pip="pytest"},
    @{Name="pytest_cov"; Pip="pytest-cov"},
    @{Name="requests"; Pip="requests"},
    @{Name="websocket"; Pip="websocket-client"}
)

# 构建批量 import 脚本 → 写入临时文件，避免 -c 传参过长/转义问题
$CheckScript = "import sys; missing=[]`n"
foreach ($pkg in $RequiredPkgs) {
    $CheckScript += "try:`n"
    $CheckScript += "    import $($pkg.Name)`n"
    $CheckScript += "    print('  OK: $($pkg.Name)')`n"
    $CheckScript += "except ImportError:`n"
    $CheckScript += "    missing.append('$($pkg.Pip)')`n"
    $CheckScript += "    print('  MISS: $($pkg.Pip)')`n"
}
$CheckScript += "if missing:`n    print('__MISSING__:' + ','.join(missing))`n"

$CheckFile = Join-Path $env:TEMP "utm_dep_check_$PID.py"
Set-Content -Path $CheckFile -Value $CheckScript -Encoding UTF8

Write-Host "[INFO] Checking dependencies (batch)..." -ForegroundColor Cyan
$CheckOutput = & $CondaExe run -n $EnvName python $CheckFile 2>&1
Remove-Item $CheckFile -ErrorAction SilentlyContinue
Write-Host $CheckOutput

$MissingLine = $CheckOutput | Select-String "__MISSING__:"
if ($MissingLine) {
    $MissingPkgs = ($MissingLine -replace ".*__MISSING__:", "").Split(",")
    Write-Host "[INFO] Installing missing packages: $($MissingPkgs -join ', ')" -ForegroundColor Yellow
    & $CondaExe run -n $EnvName pip install $MissingPkgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Package installation failed" -ForegroundColor Red
        exit 1
    }
    Write-Host "[INFO] Packages installed OK" -ForegroundColor Green
} else {
    Write-Host "[INFO] All dependencies satisfied" -ForegroundColor Green
}

# ============================================================
# 4. Port conflict detection
# ============================================================
$PortInUse = netstat -ano 2>$null | Select-String ":$Port " | Select-String "LISTENING"
if ($PortInUse) {
    $PidMatch = [regex]::Match($PortInUse, '\s+(\d+)\s*$')
    if ($PidMatch.Success) {
        $OccupiedPid = $PidMatch.Groups[1].Value
        Write-Host "[WARN] Port $Port is in use by PID $OccupiedPid" -ForegroundColor Yellow
        $Choice = Read-Host "Kill that process? (y/n)"
        if ($Choice -eq 'y') {
            Stop-Process -Id $OccupiedPid -Force
            Write-Host "[INFO] Killed PID $OccupiedPid" -ForegroundColor Green
            Start-Sleep -Seconds 1
        } else {
            Write-Host "[ERROR] Port $Port is occupied, cannot start" -ForegroundColor Red
            exit 1
        }
    }
}

# ============================================================
# 5. Launch
# ============================================================
$env:WEB_PORT = "$Port"

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "  utm_moc52 Web Console" -ForegroundColor Green
Write-Host "  URL:  http://localhost:$Port" -ForegroundColor Green
Write-Host "  Env:  $EnvName" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host ""

Push-Location "$ScriptDir\utm_simulator"
try {
    & $PythonExe web_server.py
} finally {
    Pop-Location
}
