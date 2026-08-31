#Requires -Version 5.1
# Jednorazowa instalacja assets na Windows.
# Bootstrap (nowy PC): irm https://raw.githubusercontent.com/pmalczak/assets/main/install/install.ps1 | iex

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$RepoUrl = "https://github.com/pmalczak/assets.git"
$InstallDir = Join-Path $env:LOCALAPPDATA "assets"
$PythonVersion = "3.13"
$ShortcutName = "Assets.lnk"

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

function Install-GitIfMissing {
    if (Test-AppCommand "git") {
        Write-Ok "Git juz jest"
        return
    }
    Write-Step "Instalacja Git (winget)"
    if (-not (Test-AppCommand "winget")) {
        throw "Brak Git i brak winget. Zainstaluj Git recznie: https://git-scm.com/download/win"
    }
    & winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements --disable-interactivity
    Refresh-EnvPath
    if (-not (Test-AppCommand "git")) {
        throw "Git zainstalowany, ale nie jest w PATH. Zamknij to okno i uruchom instalator ponownie."
    }
    Write-Ok "Git zainstalowany"
}

function Install-UvIfMissing {
    if (Test-AppCommand "uv") {
        Write-Ok "uv juz jest"
        return
    }
    Write-Step "Instalacja uv"
    $installed = $false
    try {
        Invoke-RestMethod "https://astral.sh/uv/install.ps1" | Invoke-Expression
        $installed = $true
    }
    catch {
        Write-WarnStep "Oficjalny instalator uv nie zadzialal, probe winget"
    }
    if (-not $installed) {
        if (-not (Test-AppCommand "winget")) {
            throw "Nie udalo sie zainstalowac uv (brak winget jako zapas)."
        }
        & winget install --id astral-sh.uv -e --source winget --accept-package-agreements --accept-source-agreements --disable-interactivity
    }
    Refresh-EnvPath
    if (-not (Test-AppCommand "uv")) {
        throw "uv zainstalowane, ale nie jest w PATH. Zamknij to okno i uruchom instalator ponownie."
    }
    Write-Ok "uv zainstalowane"
}

function Get-OriginUrl {
    param([string]$Dir)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $url = & git -C $Dir remote get-url origin 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $url) { return $null }
        return ([string]$url).Trim()
    }
    finally {
        $ErrorActionPreference = $prev
    }
}

function Normalize-GitUrl {
    param([string]$Url)
    if ([string]::IsNullOrWhiteSpace($Url)) { return "" }
    $n = $Url.Trim().TrimEnd("/").ToLowerInvariant()
    if ($n.EndsWith(".git")) {
        $n = $n.Substring(0, $n.Length - 4)
    }
    return $n
}

function Install-RepoClone {
    Write-Step "Repozytorium w $InstallDir"
    $want = Normalize-GitUrl $RepoUrl
    $gitDir = Join-Path $InstallDir ".git"
    if (Test-Path -LiteralPath $gitDir) {
        $have = Normalize-GitUrl (Get-OriginUrl $InstallDir)
        if ($have -ne $want) {
            throw "Katalog $InstallDir to inne repo ($have). Usun go albo wskaz inny folder."
        }
        if (Test-GitHubOnline) {
            $prev = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            & git -C $InstallDir pull --ff-only
            $code = $LASTEXITCODE
            $ErrorActionPreference = $prev
            if ($code -ne 0) {
                Write-WarnStep "git pull nie powiodl sie - zostaje lokalna kopia"
            }
            else {
                Write-Ok "git pull --ff-only"
            }
        }
        else {
            Write-WarnStep "Brak sieci - pomijam git pull"
        }
        return
    }
    if (Test-Path -LiteralPath $InstallDir) {
        $items = @(Get-ChildItem -LiteralPath $InstallDir -Force -ErrorAction SilentlyContinue)
        if ($items.Count -gt 0) {
            throw "Katalog $InstallDir istnieje i nie jest klonem git. Usun go i uruchom instalator ponownie."
        }
    }
    & git clone $RepoUrl $InstallDir
    if ($LASTEXITCODE -ne 0) {
        throw "git clone nie powiodl sie"
    }
    Write-Ok "Sklonowano $RepoUrl"
}

function Install-PythonEnv {
    Write-Step "Python $PythonVersion + zaleznosci (uv)"
    Push-Location $InstallDir
    try {
        & uv python install $PythonVersion
        if ($LASTEXITCODE -ne 0) {
            throw "uv python install $PythonVersion nie powiodlo sie"
        }
        & uv sync
        if ($LASTEXITCODE -ne 0) {
            throw "uv sync nie powiodlo sie"
        }
    }
    finally {
        Pop-Location
    }
    Write-Ok "Srodowisko gotowe"
}

function Test-DropboxConfig {
    $config = Join-Path $env:USERPROFILE "Dropbox\INWESTYCJE\assets\a_config.xlsx"
    if (Test-Path -LiteralPath $config) {
        Write-Ok "Znaleziono $config"
    }
    else {
        Write-WarnStep "Brak $config. Zsynchronizuj Dropbox (folder INWESTYCJE) zanim uruchomisz dashboard."
    }
}

function Install-DesktopShortcut {
    Write-Step "Skrot na Pulpicie"
    $desktop = [Environment]::GetFolderPath("Desktop")
    $lnk = Join-Path $desktop $ShortcutName
    $target = Join-Path $InstallDir "install\launch.bat"
    if (-not (Test-Path -LiteralPath $target)) {
        throw "Brak $target - klon repozytorium jest niepelny (brak install/launch.bat na GitHub)."
    }
    $wsh = New-Object -ComObject WScript.Shell
    $shortcut = $wsh.CreateShortcut($lnk)
    $shortcut.TargetPath = $target
    $shortcut.WorkingDirectory = $InstallDir
    $shortcut.Description = "Assets Dashboard"
    $shortcut.WindowStyle = 1
    $shortcut.Save()
    Write-Ok "Skrot: $lnk (bez Menu Start)"
}

Refresh-EnvPath
try {
    Install-GitIfMissing
    Install-UvIfMissing
    Install-RepoClone
    Install-PythonEnv
    Test-DropboxConfig
    Install-DesktopShortcut
    Write-Host ""
    Write-Host "Instalacja zakonczona. Uruchom Assets ze skrotu na Pulpicie." -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host "BLAD: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
