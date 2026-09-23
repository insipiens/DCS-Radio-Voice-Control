$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PiperDir = Join-Path $Root 'tools\piper'
$ModelDir = Join-Path $Root 'models\piper'
$Zip = Join-Path $PiperDir 'piper_windows_amd64.zip'
$PiperExe = Join-Path $PiperDir 'piper\piper.exe'
$Model = Join-Path $ModelDir 'en_GB-alan-medium.onnx'
$Config = "$Model.json"
$Manifest = Join-Path $PiperDir 'dcs_radio_voice_control-tts.json'
$PiperRelease = '2023.11.14-2'

$PiperUrl = "https://github.com/rhasspy/piper/releases/download/$PiperRelease/piper_windows_amd64.zip"
$VoiceRevision = 'b15880f5cbc33fcfc97938b1f72411dc770e5bc4'
$VoiceBaseUrl = "https://huggingface.co/rhasspy/piper-voices/resolve/$VoiceRevision/en/en_GB/alan/medium"
$ModelUrl = "$VoiceBaseUrl/en_GB-alan-medium.onnx?download=true"
$ConfigUrl = "$VoiceBaseUrl/en_GB-alan-medium.onnx.json?download=true"
$ModelMd5 = '8f6b35eeb8ef6269021c6cb6d2414c9b'
$ConfigMd5 = 'b11d9afd0a8f5372c42a52fbd6e021d4'

New-Item -ItemType Directory -Force -Path $PiperDir, $ModelDir | Out-Null

if (-not (Test-Path $PiperExe)) {
    Write-Host 'Downloading the pinned standalone Piper Windows build...'
    Invoke-WebRequest -Uri $PiperUrl -OutFile $Zip -UseBasicParsing
    Expand-Archive -LiteralPath $Zip -DestinationPath $PiperDir -Force
    Remove-Item $Zip -Force
}

function Get-Md5([string]$Path) {
    return (Get-FileHash -Algorithm MD5 -LiteralPath $Path).Hash.ToLowerInvariant()
}

if (-not (Test-Path $Model) -or (Get-Md5 $Model) -ne $ModelMd5) {
    Write-Host 'Downloading the en_GB-alan-medium Piper voice...'
    Invoke-WebRequest -Uri $ModelUrl -OutFile $Model -UseBasicParsing
}
if ((Get-Md5 $Model) -ne $ModelMd5) {
    throw 'Piper voice model failed its published MD5 check.'
}

if (-not (Test-Path $Config) -or (Get-Md5 $Config) -ne $ConfigMd5) {
    Write-Host 'Downloading the Piper voice configuration...'
    Invoke-WebRequest -Uri $ConfigUrl -OutFile $Config -UseBasicParsing
}
if ((Get-Md5 $Config) -ne $ConfigMd5) {
    throw 'Piper voice configuration failed its published MD5 check.'
}

if (-not (Test-Path $PiperExe)) {
    throw "Piper executable was not found after extraction: $PiperExe"
}

[ordered]@{
    schema = 1
    piper_release = $PiperRelease
    piper_source_url = $PiperUrl
    voice_revision = $VoiceRevision
    model_md5 = $ModelMd5
    config_md5 = $ConfigMd5
    configured_at = [DateTime]::UtcNow.ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $Manifest -Encoding UTF8

Write-Host 'Piper TTS is ready.'
Write-Host "Executable: $PiperExe"
Write-Host "Voice:      $Model"
