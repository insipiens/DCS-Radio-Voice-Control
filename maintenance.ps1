param(
    [ValidateSet("status", "reconcile")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonVersion = "3.13.15"
$PythonSha256 = "d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf"
$PygameVersion = "2.5.8"
$PygameSha256 = "f495b0eb7a5c54c59da58e964bc7f68073c3f43cf307729fd48309104a04c190"
$WhisperVersion = "b4938"
$WhisperArchives = @{
    cpu = "c2a4b60edb11f7e11a9191ffb50929535527d4d91c9903dbe3e554583bbbc63d"
    cuda12 = "c1b17166e1e31a91cc8e9c1f910d3785e3ce757bb2958bf9dce13fdb4880005f"
}
$WhisperModels = @{
    "ggml-base.en.bin" = "a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002"
    "ggml-small.en.bin" = "c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d"
    "ggml-medium.en.bin" = "cc37e93478338ec7700281a7ac30a10128929eb8f427dda2e865faa8f6da4356"
}
$PiperRelease = "2023.11.14-2"
$PiperSha256 = "f3c58906402b24f3a96d92145f58acba6d86c9b5db896d207f78dc80811efcea"
$VoiceRevision = "b15880f5cbc33fcfc97938b1f72411dc770e5bc4"
$VoiceModelMd5 = "8f6b35eeb8ef6269021c6cb6d2414c9b"
$VoiceConfigMd5 = "b11d9afd0a8f5372c42a52fbd6e021d4"

function Read-Json([string]$Path) {
    try {
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    }
    catch { return $null }
}

function Component([string]$Name, [string]$State, [string]$Detail) {
    return [ordered]@{ name = $Name; state = $State; detail = $Detail }
}

function Get-DesiredStt {
    $Model = "ggml-base.en.bin"
    $UseGpu = $false
    $Local = $env:LOCALAPPDATA
    if ($Local) {
        $Config = Read-Json (Join-Path $Local "DCSRadioVoiceControl\config.json")
        if ($null -ne $Config -and $null -ne $Config.stt) {
            if ($WhisperModels.ContainsKey([string]$Config.stt.model)) {
                $Model = [string]$Config.stt.model
            }
            if ($Config.stt.use_gpu -is [bool]) {
                $UseGpu = [bool]$Config.stt.use_gpu
            }
        }
    }
    return [ordered]@{ model = $Model; compute = $(if ($UseGpu) { "cuda12" } else { "cpu" }) }
}

function Get-RuntimeStatus {
    $Dir = Join-Path $Root "runtime"
    $Exe = Join-Path $Dir "python.exe"
    $Manifest = Read-Json (Join-Path $Dir "dcs_radio_voice_control-runtime.json")
    if (-not (Test-Path -LiteralPath $Exe -PathType Leaf) -or $null -eq $Manifest) {
        return Component "runtime" "missing" "Private Python/SDL runtime is not installed."
    }
    if ($Manifest.python_version -ne $PythonVersion -or
        $Manifest.archive_sha256 -ne $PythonSha256 -or
        $Manifest.pygame_version -ne $PygameVersion -or
        $Manifest.pygame_archive_sha256 -ne $PygameSha256) {
        return Component "runtime" "update_required" "Private Python/SDL manifest does not match the pinned component."
    }
    try {
        & $Exe -I -c "import sys; raise SystemExit(0 if sys.version_info[:3] == (3, 13, 15) else 1)" 2>$null
        if ($LASTEXITCODE -ne 0) { throw "python" }
        $env:PYGAME_HIDE_SUPPORT_PROMPT = "1"
        & $Exe -I -c "import pygame; raise SystemExit(0 if pygame.version.ver == '$PygameVersion' else 1)" 2>$null
        if ($LASTEXITCODE -ne 0) { throw "pygame" }
    }
    catch {
        return Component "runtime" "repair_required" "Private Python/SDL self-test failed."
    }
    return Component "runtime" "current" "Python $PythonVersion / pygame-ce $PygameVersion"
}

function Test-Worker([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $Path
    $StartInfo.Arguments = "--version"
    $StartInfo.UseShellExecute = $false
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true
    $StartInfo.CreateNoWindow = $true
    $Process = New-Object System.Diagnostics.Process
    $Process.StartInfo = $StartInfo
    try {
        if (-not $Process.Start()) { return $false }
        $StandardOutput = $Process.StandardOutput.ReadToEndAsync()
        $StandardError = $Process.StandardError.ReadToEndAsync()
        $Process.WaitForExit()
        $null = $StandardOutput.Result
        $null = $StandardError.Result
        return $Process.ExitCode -eq 0
    }
    catch { return $false }
    finally { $Process.Dispose() }
}

function Get-SttStatus {
    $Desired = Get-DesiredStt
    $Dir = Join-Path $Root "stt"
    $Exe = Join-Path $Dir "dcs_radio_voice_control-whisper.exe"
    $Model = Join-Path $Dir $Desired.model
    $Manifest = Read-Json (Join-Path $Dir "dcs_radio_voice_control-stt.json")
    if (-not (Test-Path -LiteralPath $Exe -PathType Leaf) -or $null -eq $Manifest) {
        return Component "stt" "missing" "Whisper worker is not installed."
    }
    if ($Manifest.whisper_version -ne $WhisperVersion -or
        $Manifest.compute -ne $Desired.compute -or
        $Manifest.whisper_archive_sha256 -ne $WhisperArchives[$Desired.compute]) {
        return Component "stt" "update_required" "Whisper worker does not match the selected pinned component."
    }
    if (-not (Test-Path -LiteralPath $Model -PathType Leaf)) {
        return Component "stt" "missing" "Selected Whisper model $($Desired.model) is not installed."
    }
    $Actual = (Get-FileHash -LiteralPath $Model -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Actual -ne $WhisperModels[$Desired.model]) {
        return Component "stt" "repair_required" "Selected Whisper model failed SHA-256 validation."
    }
    if (-not (Test-Worker $Exe)) {
        return Component "stt" "repair_required" "Whisper worker self-test failed."
    }
    return Component "stt" "current" "whisper.cpp $WhisperVersion / $($Desired.compute) / $($Desired.model)"
}

function Test-Piper([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $Path
    $StartInfo.Arguments = "--help"
    $StartInfo.UseShellExecute = $false
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true
    $StartInfo.CreateNoWindow = $true
    $Process = New-Object System.Diagnostics.Process
    $Process.StartInfo = $StartInfo
    try {
        if (-not $Process.Start()) { return $false }
        $StandardOutput = $Process.StandardOutput.ReadToEndAsync()
        $StandardError = $Process.StandardError.ReadToEndAsync()
        $Process.WaitForExit()
        $null = $StandardOutput.Result
        $null = $StandardError.Result
        return $Process.ExitCode -eq 0
    }
    catch { return $false }
    finally { $Process.Dispose() }
}

function Get-TtsStatus {
    $Dir = Join-Path $Root "tools\piper"
    $Exe = Join-Path $Dir "piper\piper.exe"
    $Manifest = Read-Json (Join-Path $Dir "dcs_radio_voice_control-tts.json")
    $Model = Join-Path $Root "models\piper\en_GB-alan-medium.onnx"
    $Config = "$Model.json"
    if (-not (Test-Path -LiteralPath $Exe -PathType Leaf) -or $null -eq $Manifest) {
        return Component "tts" "missing" "Pinned Piper installation record is missing."
    }
    if ($Manifest.schema -ne 2 -or
        $Manifest.piper_release -ne $PiperRelease -or
        $Manifest.piper_archive_sha256 -ne $PiperSha256 -or
        $Manifest.voice_revision -ne $VoiceRevision -or
        $Manifest.model_md5 -ne $VoiceModelMd5 -or
        $Manifest.config_md5 -ne $VoiceConfigMd5) {
        return Component "tts" "update_required" "Piper/Alan manifest does not match the pinned component."
    }
    if (-not (Test-Path -LiteralPath $Model -PathType Leaf) -or
        -not (Test-Path -LiteralPath $Config -PathType Leaf)) {
        return Component "tts" "missing" "Alan voice files are not installed."
    }
    if ((Get-FileHash -LiteralPath $Model -Algorithm MD5).Hash.ToLowerInvariant() -ne $VoiceModelMd5 -or
        (Get-FileHash -LiteralPath $Config -Algorithm MD5).Hash.ToLowerInvariant() -ne $VoiceConfigMd5) {
        return Component "tts" "repair_required" "Alan voice files failed their published checks."
    }
    if (-not (Test-Piper $Exe)) {
        return Component "tts" "repair_required" "Piper executable self-test failed."
    }
    return Component "tts" "current" "Piper $PiperRelease / en_GB-alan-medium"
}

function Get-Status {
    $Components = @(
        Get-RuntimeStatus
        Get-SttStatus
        Get-TtsStatus
    )
    $Ready = @($Components | Where-Object { $_.state -ne "current" }).Count -eq 0
    return [ordered]@{
        schema = 1
        ready = $Ready
        components = $Components
    }
}

if ($Action -eq "status") {
    Get-Status | ConvertTo-Json -Depth 5
    exit 0
}

$Status = Get-Status
foreach ($Component in $Status.components) {
    if ($Component.state -eq "current") {
        Write-Host "[current] $($Component.name): $($Component.detail)"
        continue
    }
    Write-Host "[$($Component.state)] $($Component.name): $($Component.detail)"
    switch ($Component.name) {
        "runtime" {
            & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "setup.ps1")
        }
        "stt" {
            $Desired = Get-DesiredStt
            $ModelKey = $Desired.model -replace "^ggml-", "" -replace "\.bin$", ""
            & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "setup-stt.ps1") -Model $ModelKey -Compute $Desired.compute
        }
        "tts" {
            & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "setup-tts.ps1")
        }
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Reconciliation failed for component $($Component.name)."
    }
}

$Final = Get-Status
if (-not $Final.ready) {
    $Problems = @($Final.components | Where-Object { $_.state -ne "current" } | ForEach-Object { "$($_.name):$($_.state)" })
    throw "Component reconciliation did not reach a ready state: $($Problems -join ', ')"
}
Write-Host "DCS Radio Voice Control components are ready."
