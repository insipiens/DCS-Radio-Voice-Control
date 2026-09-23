# DCS Radio Voice Control

DCS Radio Voice Control operates the live DCS radio menu by voice. Hold push-to-talk, say a command such as **“Flight, Cover Me”**, and release. Speech recognition runs locally; recorded speech is not sent to a cloud service.

## Features

- Direct voice commands against the options currently available in DCS.
- Guided **Show** navigation and spoken **List** command reminders.
- Mission-specific F10 commands.
- HOTAS or keyboard push-to-talk.
- Local Whisper speech recognition and Piper speech output.
- Configurable aliases, microphone, audio output and matching thresholds.
- Optional Desktop shortcut and Start with Windows.

## Install

Requires Windows 11 x64 and DCS World.

**[Download the development installer (Windows EXE)](https://github.com/insipiens/DCS-Radio-Voice-Control/releases/download/development-installer/DCS-Radio-Voice-Control-Setup.exe)**

1. Close DCS and DCS Radio Voice Control.
2. Run `DCS-Radio-Voice-Control-Setup.exe`.
3. Read the DCS integration notice and choose **Install**.
4. Setup installs DRVC for your Windows account and downloads/verifies its private Python, Whisper and Piper components. Approve Windows elevation only when the protected DCS radio-menu file needs changing.
5. On the final page, leave **Configure DCS Radio Voice Control** selected. Choose your microphone, audio output and PTT button, then **Save configuration and start**.

The program is installed under `%LOCALAPPDATA%\Programs\DCS Radio Voice Control`. User configuration and aliases are kept separately under `%LOCALAPPDATA%\DCSRadioVoiceControl`.

See [INSTALLATION.md](INSTALLATION.md) for the full procedure and troubleshooting.

## Use

Direct commands execute a complete live command without navigating the menu first:

> “Flight, Cover Me”

> “Two, Rejoin”

`List` speaks the choices without changing the DCS menu:

> “List ATC commands”

`Show` opens a known menu path for guided navigation:

> “Show ATC”

> “Show F10”

Once a guided menu is visible, say the displayed option or its bare function key. Bare `F1`–`F10` are relative to the visible menu; `Show F1`–`Show F10` start from the root radio menu. `Previous Menu`/`F11` goes back and `Exit Menu`/`F12` closes the menu.

Aliases can make DCS terminology more natural. For example, `Two, Rejoin` can resolve to `Wingman > Rejoin Formation` without bypassing command matching.

## Configuration

Open **Start > DCS Radio Voice Control > Configure DCS Radio Voice Control**. Configuration controls the microphone, audio output, HOTAS/PTT, Whisper model, matching thresholds, feedback, Desktop shortcut and Start with Windows.

## Updating

Close DRVC and [download the current development Setup EXE](https://github.com/insipiens/DCS-Radio-Voice-Control/releases/download/development-installer/DCS-Radio-Voice-Control-Setup.exe), then run it. The stable installer identity updates the existing installation in place. Valid unchanged runtime, Whisper and Piper components are reused; configuration, PTT settings and aliases are preserved.

## Repair

Open **Start > DCS Radio Voice Control > Repair DCS Radio Voice Control**. Repair verifies the managed components and DCS integration and replaces only items that can be safely identified. It stops rather than overwriting an unexpected DCS radio-menu file.

## Uninstall

Use **Windows Settings > Apps > Installed apps > DCS Radio Voice Control > Uninstall**. The uninstaller restores the verified original DCS radio-menu file and removes DRVC-owned program files, shortcuts, startup registration and disposable files.

Configuration and aliases are retained by default. During uninstall you can explicitly choose to delete the remaining user data.

## More information

[INSTALLATION.md](INSTALLATION.md) — installation, configuration, updates, repair, removal and troubleshooting.

[PIPER.md](PIPER.md) — local speech output.

[INSTALLER_ARCHITECTURE.md](INSTALLER_ARCHITECTURE.md) — installer ownership and safety contract.
