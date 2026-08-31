#Requires -Version 5.1
# Uruchamia Assets: przy sieci git pull + uv sync, potem Streamlit.

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$InstallDir = Join-Path $env:LOCALAPPDATA "assets"

if ($PSScriptRoot) {
    $fromScript = Split-Path -Parent $PSScriptRoot
    if (Test-Path -LiteralPath (Join-Path $fromScript ".git")) {
        $InstallDir = $fromScript
    }
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "OK  $Message" -ForegroundColor Green
}

function Write-WarnStep {
    param([string]$Message)
    Write-Host "UWAGA  $Message" -ForegroundColor Yellow
}

function Refresh-EnvPath {
    $machine = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
    $extras = @(
        (Join-Path $env:USERPROFILE ".local\bin"),
        (Join-Path $env:USERPROFILE ".cargo\bin"),
        "C:\Program Files\Git\cmd"
    )
    foreach ($extra in $extras) {
        if ((Test-Path -LiteralPath $extra) -and ($env:Path -notlike "*$extra*")) {
            $env:Path = "$extra;$env:Path"
        }
    }
}

function Test-AppCommand {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Test-GitHubOnline {
    try {
        Invoke-WebRequest -Uri "https://github.com" -UseBasicParsing -TimeoutSec 5 | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

function Update-FromGitHub {
    if (-not (Test-GitHubOnline)) {
        Write-WarnStep "Brak sieci - uruchamiam lokalna kopie"
        return
    }
    Write-Step "Aktualizacja z GitHub"
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & git -C $InstallDir pull --ff-only
    $pullCode = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($pullCode -ne 0) {
        Write-WarnStep "git pull --ff-only nie powiodl sie (konflikt albo lokalne zmiany). Startuje lokalna kopia, bez reset --hard."
        return
    }
    Write-Ok "git pull --ff-only"
    Write-Step "uv sync"
    Push-Location $InstallDir
    try {
        $ErrorActionPreference = "Continue"
        & uv sync
        $syncCode = $LASTEXITCODE
        $ErrorActionPreference = $prev
        if ($syncCode -ne 0) {
            Write-WarnStep "uv sync nie powiodl sie - startuje lokalna kopia"
            return
        }
        Write-Ok "uv sync"
    }
    finally {
        Pop-Location
        $ErrorActionPreference = $prev
    }
}

function Start-AssetsApp {
    $appDir = Join-Path $InstallDir "app"
    $script = Join-Path $appDir "app_assets.py"
    if (-not (Test-Path -LiteralPath $script)) {
        throw "Brak $script - instalacja jest niepelna. Uruchom install\install.ps1."
    }
    Write-Step "Streamlit ($script)"
    Set-Location $appDir
    & uv run streamlit run app_assets.py
    exit $LASTEXITCODE
}

Refresh-EnvPath

if (-not (Test-Path -LiteralPath (Join-Path $InstallDir ".git"))) {
    Write-Host "BLAD: Brak klonu w $InstallDir. Uruchom najpierw install\install.ps1." -ForegroundColor Red
    exit 1
}

if (-not (Test-AppCommand "git")) {
    Write-Host "BLAD: Brak Git w PATH. Uruchom instalator ponownie." -ForegroundColor Red
    exit 1
}

if (-not (Test-AppCommand "uv")) {
    Write-Host "BLAD: Brak uv w PATH. Uruchom instalator ponownie." -ForegroundColor Red
    exit 1
}

try {
    Update-FromGitHub
    Start-AssetsApp
}
catch {
    Write-Host ""
    Write-Host "BLAD: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
