# Piper speech in DCS Radio Voice Control

DRVC uses the pinned standalone Piper Windows release `2023.11.14-2` and the `en_GB-alan-medium` voice. Setup downloads the pinned assets and verifies them before use; the Piper Windows archive is checked against its pinned SHA-256.

The live path is entirely in memory:

```text
response text -> piper.exe --output-raw -> PCM memory -> pygame-ce/SDL -> selected output
```

Piper runs once per response. Synthesis is performed on a background thread; pressing PTT terminates active speech/playback before microphone capture starts.

DRVC uses the voice model's native synthesis settings. The configuration page exposes the output device and a voice test.

Within the installed application, the executable is under `tools\piper` and the Alan model/configuration are under `models\piper`. No Python Piper package, cloud speech request or temporary WAV file is used.
