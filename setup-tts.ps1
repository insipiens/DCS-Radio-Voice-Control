$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PiperDir = Join-Path $Root 'tools\piper'
$ModelDir = Join-Path $Root 'models\piper'
$PiperExe = Join-Path $PiperDir 'piper\piper.exe'
$Model = Join-Path $ModelDir 'en_GB-alan-medium.onnx'
$Config = "$Model.json"
$Manifest = Join-Path $PiperDir 'dcs_radio_voice_control-tts.json'
$PiperRelease = '2023.11.14-2'
$PiperUrl = "https://github.com/rhasspy/piper/releases/download/$PiperRelease/piper_windows_amd64.zip"
$PiperSha256 = 'f3c58906402b24f3a96d92145f58acba6d86c9b5db896d207f78dc80811efcea'
$VoiceRevision = 'b15880f5cbc33fcfc97938b1f72411dc770e5bc4'
$VoiceBaseUrl = "https://huggingface.co/rhasspy/piper-voices/resolve/$VoiceRevision/en/en_GB/alan/medium"
$ModelUrl = "$VoiceBaseUrl/en_GB-alan-medium.onnx?download=true"
$ConfigUrl = "$VoiceBaseUrl/en_GB-alan-medium.onnx.json?download=true"
$ModelMd5 = '8f6b35eeb8ef6269021c6cb6d2414c9b'
$ConfigMd5 = 'b11d9afd0a8f5372c42a52fbd6e021d4'

function Get-Md5([string]$Path) {
    return (Get-FileHash -Algorithm MD5 -LiteralPath $Path).Hash.ToLowerInvariant()
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

function Install-VerifiedFile([string]$Url, [string]$Target, [string]$ExpectedMd5, [string]$Description) {
    if ((Test-Path -LiteralPath $Target -PathType Leaf) -and (Get-Md5 $Target) -eq $ExpectedMd5) {
        return
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Target) | Out-Null
    $Staged = "$Target.new." + [guid]::NewGuid().ToString("N")
    try {
        Write-Host "Downloading $Description..."
        Invoke-WebRequest -Uri $Url -OutFile $Staged -UseBasicParsing
        if ((Get-Md5 $Staged) -ne $ExpectedMd5) {
            throw "$Description failed its published MD5 check."
        }
        Move-Item -LiteralPath $Staged -Destination $Target -Force
    }
    finally {
        if (Test-Path -LiteralPath $Staged) { Remove-Item -LiteralPath $Staged -Force }
    }
}

$TemporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("DCSRadioVoiceControl-TTS-" + [guid]::NewGuid().ToString("N"))
$StagingDirectory = Join-Path $Root ("tools\piper.new." + [guid]::NewGuid().ToString("N"))
$BackupDirectory = Join-Path $Root ("tools\piper.old." + [guid]::NewGuid().ToString("N"))
$LiveMoved = $false

try {
    New-Item -ItemType Directory -Force -Path $TemporaryRoot, $ModelDir | Out-Null

    Install-VerifiedFile $ModelUrl $Model $ModelMd5 'the en_GB-alan-medium Piper voice'
    Install-VerifiedFile $ConfigUrl $Config $ConfigMd5 'the Piper voice configuration'

    $ExistingManifest = $null
    try {
        if (Test-Path -LiteralPath $Manifest -PathType Leaf) {
            $ExistingManifest = Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json
        }
    }
    catch { $ExistingManifest = $null }

    $PiperCurrent = (
        $null -ne $ExistingManifest -and
        $ExistingManifest.schema -eq 2 -and
        $ExistingManifest.piper_release -eq $PiperRelease -and
        $ExistingManifest.piper_archive_sha256 -match '^[0-9a-f]{64}
    if (-not $PiperCurrent) {
        $Zip = Join-Path $TemporaryRoot 'piper_windows_amd64.zip'
        $Expanded = Join-Path $TemporaryRoot 'expanded'
        Write-Host 'Downloading the pinned standalone Piper Windows build...'
        Invoke-WebRequest -Uri $PiperUrl -OutFile $Zip -UseBasicParsing
        $ArchiveSha256 = (Get-FileHash -LiteralPath $Zip -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ArchiveSha256 -ne $PiperSha256) {
            throw "Piper archive hash mismatch. Expected $PiperSha256 but received $ArchiveSha256."
        }
        Expand-Archive -LiteralPath $Zip -DestinationPath $Expanded
        $StagedPiper = Join-Path $Expanded 'piper'
        $StagedExe = Join-Path $StagedPiper 'piper.exe'
        if (-not (Test-Piper $StagedExe)) {
            throw 'The staged Piper executable failed its self-test.'
        }

        New-Item -ItemType Directory -Path $StagingDirectory | Out-Null
        Move-Item -LiteralPath $StagedPiper -Destination (Join-Path $StagingDirectory 'piper')
        [ordered]@{
            schema = 2
            piper_release = $PiperRelease
            piper_source_url = $PiperUrl
            piper_archive_sha256 = $ArchiveSha256
            voice_revision = $VoiceRevision
            model_md5 = $ModelMd5
            config_md5 = $ConfigMd5
            configured_at = [DateTime]::UtcNow.ToString("o")
        } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $StagingDirectory 'dcs_radio_voice_control-tts.json') -Encoding UTF8

        if (Test-Path -LiteralPath $PiperDir) {
            Move-Item -LiteralPath $PiperDir -Destination $BackupDirectory
            $LiveMoved = $true
        }
        try {
            Move-Item -LiteralPath $StagingDirectory -Destination $PiperDir
        }
        catch {
            if ($LiveMoved -and -not (Test-Path -LiteralPath $PiperDir)) {
                Move-Item -LiteralPath $BackupDirectory -Destination $PiperDir
                $LiveMoved = $false
            }
            throw
        }
        if (-not (Test-Piper $PiperExe)) {
            Remove-Item -LiteralPath $PiperDir -Recurse -Force
            if ($LiveMoved) {
                Move-Item -LiteralPath $BackupDirectory -Destination $PiperDir
                $LiveMoved = $false
            }
            throw 'The installed Piper executable failed its post-install self-test.'
        }
        if ($LiveMoved -and (Test-Path -LiteralPath $BackupDirectory)) {
            Remove-Item -LiteralPath $BackupDirectory -Recurse -Force
            $LiveMoved = $false
        }
    }
    else {
        $ExistingManifest | Add-Member -NotePropertyName voice_revision -NotePropertyValue $VoiceRevision -Force
        $ExistingManifest | Add-Member -NotePropertyName model_md5 -NotePropertyValue $ModelMd5 -Force
        $ExistingManifest | Add-Member -NotePropertyName config_md5 -NotePropertyValue $ConfigMd5 -Force
        $ExistingManifest | ConvertTo-Json | Set-Content -LiteralPath $Manifest -Encoding UTF8
    }

    Write-Host 'Piper TTS is ready.'
    Write-Host "Executable: $PiperExe"
    Write-Host "Voice:      $Model"
}
finally {
    if (Test-Path -LiteralPath $TemporaryRoot) {
        Remove-Item -LiteralPath $TemporaryRoot -Recurse -Force
    }
    if (Test-Path -LiteralPath $StagingDirectory) {
        Remove-Item -LiteralPath $StagingDirectory -Recurse -Force
    }
    if ($LiveMoved -and (Test-Path -LiteralPath $BackupDirectory) -and
        -not (Test-Path -LiteralPath $PiperDir)) {
        Move-Item -LiteralPath $BackupDirectory -Destination $PiperDir
        $LiveMoved = $false
    }
}
 -and
        (Test-Piper $PiperExe)
    )

    if (-not $PiperCurrent) {
        $Zip = Join-Path $TemporaryRoot 'piper_windows_amd64.zip'
        $Expanded = Join-Path $TemporaryRoot 'expanded'
        Write-Host 'Downloading the pinned standalone Piper Windows build...'
        Invoke-WebRequest -Uri $PiperUrl -OutFile $Zip -UseBasicParsing
        $ArchiveSha256 = (Get-FileHash -LiteralPath $Zip -Algorithm SHA256).Hash.ToLowerInvariant()
        Expand-Archive -LiteralPath $Zip -DestinationPath $Expanded
        $StagedPiper = Join-Path $Expanded 'piper'
        $StagedExe = Join-Path $StagedPiper 'piper.exe'
        if (-not (Test-Piper $StagedExe)) {
            throw 'The staged Piper executable failed its self-test.'
        }

        New-Item -ItemType Directory -Path $StagingDirectory | Out-Null
        Move-Item -LiteralPath $StagedPiper -Destination (Join-Path $StagingDirectory 'piper')
        [ordered]@{
            schema = 2
            piper_release = $PiperRelease
            piper_source_url = $PiperUrl
            piper_archive_sha256 = $ArchiveSha256
            voice_revision = $VoiceRevision
            model_md5 = $ModelMd5
            config_md5 = $ConfigMd5
            configured_at = [DateTime]::UtcNow.ToString("o")
        } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $StagingDirectory 'dcs_radio_voice_control-tts.json') -Encoding UTF8

        if (Test-Path -LiteralPath $PiperDir) {
            Move-Item -LiteralPath $PiperDir -Destination $BackupDirectory
            $LiveMoved = $true
        }
        try {
            Move-Item -LiteralPath $StagingDirectory -Destination $PiperDir
        }
        catch {
            if ($LiveMoved -and -not (Test-Path -LiteralPath $PiperDir)) {
                Move-Item -LiteralPath $BackupDirectory -Destination $PiperDir
                $LiveMoved = $false
            }
            throw
        }
        if (-not (Test-Piper $PiperExe)) {
            Remove-Item -LiteralPath $PiperDir -Recurse -Force
            if ($LiveMoved) {
                Move-Item -LiteralPath $BackupDirectory -Destination $PiperDir
                $LiveMoved = $false
            }
            throw 'The installed Piper executable failed its post-install self-test.'
        }
        if ($LiveMoved -and (Test-Path -LiteralPath $BackupDirectory)) {
            Remove-Item -LiteralPath $BackupDirectory -Recurse -Force
            $LiveMoved = $false
        }
    }
    else {
        $ExistingManifest | Add-Member -NotePropertyName voice_revision -NotePropertyValue $VoiceRevision -Force
        $ExistingManifest | Add-Member -NotePropertyName model_md5 -NotePropertyValue $ModelMd5 -Force
        $ExistingManifest | Add-Member -NotePropertyName config_md5 -NotePropertyValue $ConfigMd5 -Force
        $ExistingManifest | ConvertTo-Json | Set-Content -LiteralPath $Manifest -Encoding UTF8
    }

    Write-Host 'Piper TTS is ready.'
    Write-Host "Executable: $PiperExe"
    Write-Host "Voice:      $Model"
}
finally {
    if (Test-Path -LiteralPath $TemporaryRoot) {
        Remove-Item -LiteralPath $TemporaryRoot -Recurse -Force
    }
    if (Test-Path -LiteralPath $StagingDirectory) {
        Remove-Item -LiteralPath $StagingDirectory -Recurse -Force
    }
    if ($LiveMoved -and (Test-Path -LiteralPath $BackupDirectory) -and
        -not (Test-Path -LiteralPath $PiperDir)) {
        Move-Item -LiteralPath $BackupDirectory -Destination $PiperDir
        $LiveMoved = $false
    }
}
