# DCS Radio Voice Control installation guide

This guide describes the current Windows installer, configuration, update, repair and uninstall procedures.

> **CombatAI:** remove an old CombatAI installation with its own uninstaller before installing DCS Radio Voice Control. DRVC deliberately refuses to overwrite the old CombatAI hook.

## Requirements

- Windows 11 x64.
- DCS World already installed and launched at least once.
- Internet access during initial setup.
- A microphone.
- Optional HOTAS button for push-to-talk; Space is the keyboard fallback.

Close DCS before installing, updating, repairing or uninstalling the DCS integration.

## Installation

[Download the development installer (Windows EXE)](https://github.com/insipiens/DCS-Radio-Voice-Control/releases/download/development-installer/DCS-Radio-Voice-Control-Setup.exe).

1. Run `DCS-Radio-Voice-Control-Setup.exe`.
2. Read the integration notice and choose **Install**.
3. Setup installs the application for the current Windows user at:

   `%LOCALAPPDATA%\Programs\DCS Radio Voice Control`

4. Setup reconciles the private Python/SDL runtime, Whisper and Piper/Alan components. Downloads are staged and verified before replacing a live component. Components already at the pinned version are reused.
5. DRVC locates DCS and its Saved Games folder. When the protected DCS radio-menu file needs changing, Windows displays a UAC prompt for that operation only.
6. The original DCS radio-menu file is verified and backed up before DRVC replaces it. If the existing file is unexpected, installation stops rather than forcing a replacement.
7. On the final Setup page, leave **Configure DCS Radio Voice Control** selected. The configuration page opens in your browser. After **Save configuration and close**, Setup starts the separate notification-area controller; you may close the browser tab.

The normal installer recognises the standard standalone and default Steam DCS locations. A previously recorded DCS/Saved Games location is also reused. The current installer has no path-selection page for a new non-standard DCS location; the command-line installation tool remains available for development use until that UI is added.

## Configuration

The first configuration run offers **Save configuration and close**.

1. Select the microphone and run the three-second level test.
2. Select the playback device and test Alan/cues if required.
3. Choose **Learn a HOTAS button**, or **Use Space only**.
4. Leave `base.en`, CPU recognition and the default matching thresholds for the first test.
5. **Create a Desktop shortcut** is selected on first setup; clear it if unwanted.
6. Optionally enable **Start when DCS starts**.
7. Choose **Save configuration and close**.

Later, open **Start > DCS Radio Voice Control > Configure DCS Radio Voice Control**. The normal button is then **Save configuration**.

Configuration is stored at `%LOCALAPPDATA%\DCSRadioVoiceControl\config.json`. Aliases are stored beside it in `aliases.json`. They are not program files and are preserved by updates and repair.

## First DCS test

Start DCS and enter a mission. DRVC waits for the live DCS command catalogue before enabling voice control.

Useful non-destructive first commands are:

```text
List commands
List ATC commands
Show F10
```

A direct command such as `Flight, Cover Me` is resolved against the complete live executable catalogue. A successful direct command also ends any guided menu session.

`List` speaks the immediate choices without changing the DCS menu.

`Show` starts guided navigation at a named/root menu. `Show ATC`, `Show Flight` and `Show F1`–`Show F10` are absolute visual requests. The app reads the immediate options of the displayed menu. Say either a bare `F1`–`F10` key or the visible option name to enter its submenu or execute its leaf command. Menu punctuation such as `ATC....` is ignored; wrapper phrases such as `Go F5` are not guided selections. `Repeat` reads the current choices again. `Back`/`F11` goes back; `Exit`/`F12` closes the menu. A safe direct command takes precedence while a guided menu is open.

Recipient aliases such as `Two` → `Wingman` restrict matching to the corresponding live subtree; they do not contribute matching confidence by themselves. Action aliases can then resolve inside that subtree, for example `Two, Rejoin`.

## Everyday start

Use either:

- **Start > DCS Radio Voice Control > Start DCS Radio Voice Control**;
- the optional Desktop shortcut; or
- **Start when DCS starts**, if enabled in Configuration.

With Start when DCS starts enabled, Windows starts a visible notification-area controller at sign-in. It waits for DCS; Whisper, Piper, microphone capture and optional GPU support are loaded only when a mission and current DCS hook are ready.

Left-click the notification-area icon for status. Right-click it for **Open runtime log**, **Configure**, **Repair**, **Download update**, and **Exit**.

## Updating

Do not uninstall first.

1. Exit the notification-area controller, then close DCS.
2. [Download the current development installer](https://github.com/insipiens/DCS-Radio-Voice-Control/releases/download/development-installer/DCS-Radio-Voice-Control-Setup.exe) and run it.
3. Setup uses the same AppId and installation directory, replacing the application files in place.
4. Component reconciliation leaves valid unchanged Python/SDL, Whisper and Piper components alone.
5. The DCS hook is updated only if its existing installation can be verified; UAC is requested only if the protected DCS file actually needs changing.
6. Existing configuration, HOTAS/PTT settings and aliases are retained.

If the DCS radio-menu file changed outside DRVC after installation, the update is refused rather than restoring or overwriting an old file.

## Repair

Close DCS, then choose **Repair** from the notification-area menu or open **Start > DCS Radio Voice Control > Repair DCS Radio Voice Control**.

Repair checks the private runtime, Whisper, Piper/Alan and the DCS integration. Missing, outdated or invalid DRVC-owned components are staged, verified and replaced. The DCS integration is repaired/updated only when the existing state proves it is safe to do so.

If Repair reports that the DCS panel or installation record is unexpected, stop and keep the error. There is no **Force** or **Replace anyway** path.

Repair preserves configuration, PTT settings and aliases.

## Uninstall

1. Close DCS and DRVC.
2. Open **Windows Settings > Apps > Installed apps**.
3. Find **DCS Radio Voice Control** and choose **Uninstall**.
4. Approve UAC if Windows requires it to restore the protected DCS file.
5. DRVC verifies the installed panel and its backup before restoring the original. If either has changed unexpectedly, uninstall stops without overwriting DCS.
6. Choose whether to keep configuration and aliases for a future reinstall. Keeping them is the default/recommended path; deleting them is an explicit choice.

A successful uninstall removes the application, private runtime, speech components, Start-menu entries, canonical Desktop shortcut, Start when DCS starts registration, logs and DRVC Saved Games integration state.

## Troubleshooting

| What you see | Action |
|---|---|
| Setup cannot locate DCS | The current Setup UI auto-detects standard locations only. Do not point it at a guessed folder; record the error for investigation. |
| Download/component setup fails | Read `%LOCALAPPDATA%\DCSRadioVoiceControl\logs\installer-components.log` for the component and underlying error. Check the connection and antivirus history, then run Setup again or use **Repair** if the application is installed. Verified existing components are reused. |
| Configuration page does not open | Leave its window running and open `http://127.0.0.1:34385/` locally. |
| Microphone test is silent | Check the selected input and Windows microphone permissions. |
| HOTAS is absent | Connect/power it before opening Configuration, then reopen Configuration. Space remains available. |
| DRVC waits for DCS | Enter an active mission and ensure only one DRVC controller/test process is running. |
| DRVC reports **Restart DCS** | Close DCS completely and start it again so the current hook is loaded. |
| Repair/install says the DCS panel changed | Stop. Do not manually overwrite the panel or restore an old backup. |
| Uninstall refuses to restore DCS | Leave the DCS file alone. The safety check has detected an unverified change. |

Diagnostic logs are stored under `%LOCALAPPDATA%\DCSRadioVoiceControl\logs`. Recorded speech is not retained.

## Managed locations

| Purpose | Location |
|---|---|
| Application and private components | `%LOCALAPPDATA%\Programs\DCS Radio Voice Control` |
| Configuration and aliases | `%LOCALAPPDATA%\DCSRadioVoiceControl` |
| Remembered DCS/Saved Games paths | `%LOCALAPPDATA%\DCSRadioVoiceControl\installation.json` |
| DCS integration record/backups | `Saved Games\DCS\Scripts\DCSRadioVoiceControl` |
| DCS integration target | `<DCS>\Scripts\UI\RadioCommandDialogPanel\RadioCommandDialogsPanel.lua` |

## Developer/batch workflow

The repository still contains `install.bat`, `run.bat`, `configuration.bat`, `uninstall.bat` and component setup scripts for development and diagnostics. They are not the normal installed-user procedure. The public installer should be used for installation, update, configuration, repair and uninstall testing.
