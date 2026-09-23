$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

$PythonVersion = "3.13.15"
$PythonArchive = "python-3.13.15-embed-amd64.zip"
$PythonUrl = "https://www.python.org/ftp/python/3.13.15/$PythonArchive"
$PythonSha256 = "d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf"
$PygameVersion = "2.5.8"
$PygameArchive = "pygame_ce-2.5.8-cp313-cp313-win_amd64.whl"
$PygameUrl = "https://files.pythonhosted.org/packages/c0/1b/da9186e5b88714c16fdb23bc4ba0bca4a75c21e3a5cf9607765773f68d22/$PygameArchive"
$PygameSha256 = "f495b0eb7a5c54c59da58e964bc7f68073c3f43cf307729fd48309104a04c190"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDirectory = Join-Path $ProjectRoot "runtime"
$RuntimeManifest = Join-Path $RuntimeDirectory "dcs_radio_voice_control-runtime.json"

function Test-DcsRadioVoiceControlRuntime([string]$Directory = $RuntimeDirectory) {
    $PythonExe = Join-Path $Directory "python.exe"
    $ManifestPath = Join-Path $Directory "dcs_radio_voice_control-runtime.json"
    if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf) -or
        -not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        return $false
    }
    try {
        $Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
        if ($Manifest.python_version -ne $PythonVersion -or
            $Manifest.archive_sha256 -ne $PythonSha256 -or
            $Manifest.pygame_version -ne $PygameVersion -or
            $Manifest.pygame_archive_sha256 -ne $PygameSha256) {
            return $false
        }
        & $PythonExe -I -c "import sys; raise SystemExit(0 if sys.version_info[:3] == (3, 13, 15) else 1)"
        if ($LASTEXITCODE -ne 0) { return $false }
        $env:PYGAME_HIDE_SUPPORT_PROMPT = "1"
        & $PythonExe -I -c "import pygame; raise SystemExit(0 if pygame.version.ver == '$PygameVersion' else 1)"
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

if (Test-DcsRadioVoiceControlRuntime) {
    Write-Host "DCS Radio Voice Control private Python $PythonVersion and SDL controller support are already ready."
    exit 0
}

$TemporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("DCSRadioVoiceControl-runtime-" + [guid]::NewGuid().ToString("N"))
$PythonDownload = Join-Path $TemporaryRoot $PythonArchive
$PygameDownload = Join-Path $TemporaryRoot $PygameArchive
$StagingDirectory = Join-Path $ProjectRoot ("runtime.new." + [guid]::NewGuid().ToString("N"))
$BackupDirectory = Join-Path $ProjectRoot ("runtime.old." + [guid]::NewGuid().ToString("N"))
$LiveMoved = $false

try {
    New-Item -ItemType Directory -Path $TemporaryRoot, $StagingDirectory | Out-Null

    Write-Host "Downloading official CPython $PythonVersion embedded runtime..."
    Invoke-WebRequest -Uri $PythonUrl -OutFile $PythonDownload -UseBasicParsing
    $ActualPythonSha256 = (Get-FileHash -LiteralPath $PythonDownload -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualPythonSha256 -ne $PythonSha256) {
        throw "Python archive hash mismatch. Expected $PythonSha256 but received $ActualPythonSha256."
    }
    Expand-Archive -LiteralPath $PythonDownload -DestinationPath $StagingDirectory

    $PathConfiguration = Join-Path $StagingDirectory "python313._pth"
    if (-not (Test-Path -LiteralPath $PathConfiguration -PathType Leaf)) {
        throw "The verified Python archive did not contain python313._pth."
    }
    @(
        "python313.zip"
        "."
        "site-packages"
        "..\src"
        ".."
    ) | Set-Content -LiteralPath $PathConfiguration -Encoding ASCII

    Write-Host "Downloading pygame-ce $PygameVersion for SDL HOTAS support..."
    Invoke-WebRequest -Uri $PygameUrl -OutFile $PygameDownload -UseBasicParsing
    $ActualPygameSha256 = (Get-FileHash -LiteralPath $PygameDownload -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualPygameSha256 -ne $PygameSha256) {
        throw "pygame-ce archive hash mismatch. Expected $PygameSha256 but received $ActualPygameSha256."
    }
    $SitePackages = Join-Path $StagingDirectory "site-packages"
    New-Item -ItemType Directory -Path $SitePackages | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($PygameDownload, $SitePackages)

    [ordered]@{
        schema = 2
        python_version = $PythonVersion
        architecture = "amd64"
        source_url = $PythonUrl
        archive_sha256 = $PythonSha256
        pygame_version = $PygameVersion
        pygame_source_url = $PygameUrl
        pygame_archive_sha256 = $PygameSha256
        configured_at = [DateTime]::UtcNow.ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $StagingDirectory "dcs_radio_voice_control-runtime.json") -Encoding UTF8

    if (-not (Test-DcsRadioVoiceControlRuntime $StagingDirectory)) {
        throw "The staged Python/SDL runtime failed validation."
    }

    if (Test-Path -LiteralPath $RuntimeDirectory) {
        Move-Item -LiteralPath $RuntimeDirectory -Destination $BackupDirectory
        $LiveMoved = $true
    }
    try {
        Move-Item -LiteralPath $StagingDirectory -Destination $RuntimeDirectory
    }
    catch {
        if ($LiveMoved -and -not (Test-Path -LiteralPath $RuntimeDirectory)) {
            Move-Item -LiteralPath $BackupDirectory -Destination $RuntimeDirectory
            $LiveMoved = $false
        }
        throw
    }

    if (-not (Test-DcsRadioVoiceControlRuntime)) {
        Remove-Item -LiteralPath $RuntimeDirectory -Recurse -Force
        if ($LiveMoved) {
            Move-Item -LiteralPath $BackupDirectory -Destination $RuntimeDirectory
            $LiveMoved = $false
        }
        throw "The installed Python/SDL runtime failed post-install validation."
    }

    if ($LiveMoved -and (Test-Path -LiteralPath $BackupDirectory)) {
        Remove-Item -LiteralPath $BackupDirectory -Recurse -Force
        $LiveMoved = $false
    }
    Write-Host "DCS Radio Voice Control private Python $PythonVersion and SDL controller support are ready."
}
finally {
    if (Test-Path -LiteralPath $TemporaryRoot) {
        Remove-Item -LiteralPath $TemporaryRoot -Recurse -Force
    }
    if (Test-Path -LiteralPath $StagingDirectory) {
        Remove-Item -LiteralPath $StagingDirectory -Recurse -Force
    }
    if ($LiveMoved -and (Test-Path -LiteralPath $BackupDirectory) -and
        -not (Test-Path -LiteralPath $RuntimeDirectory)) {
        Move-Item -LiteralPath $BackupDirectory -Destination $RuntimeDirectory
        $LiveMoved = $false
    }
}
