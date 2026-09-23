# DCS Radio Voice Control installation guide

> **If CombatAI is currently installed:** close DCS and run `uninstall.bat` from the old
> CombatAI folder before continuing. This renamed version starts with new settings, models,
> logs, backups and installation records; it deliberately will not install over the old hook.

This guide assumes no programming knowledge. It covers installation, configuration, the
first test in DCS, updates, and safe removal.

## What DCS Radio Voice Control installs

DCS Radio Voice Control adds a small hook to DCS's radio-menu file and keeps the rest of the software in the
DCS Radio Voice Control folder. It downloads its own private Python runtime, local Whisper speech recognition,
and the Alan speech voice. It does not require a separate Python installation, does not change
the Windows `PATH`, and does not send recorded speech to a cloud service.

## Before you begin

You need:

- Windows 11 on a 64-bit PC;
- DCS World already installed;
- an internet connection for the first setup;
- a microphone;
- a HOTAS button if you want one for push-to-talk (the Space key also works); and
- permission to approve a Windows administrator prompt when the DCS hook is installed.

Launch DCS at least once before installing DCS Radio Voice Control. This creates the DCS folder under
`Saved Games`, which the installer needs. Then close DCS before continuing.

## 1. Download and extract DCS Radio Voice Control

1. Download the release asset named `DCS-Radio-Voice-Control.zip`. Do not use GitHub's
   automatically generated **Source code** or branch ZIPs.
2. Open your Downloads folder in File Explorer.
3. Right-click the ZIP and select **Extract All**.
4. Choose your Windows user folder as the destination; for example,
   `C:\Users\your-name`.
5. Windows will create `C:\Users\your-name\DCS-Radio-Voice-Control`.
6. Open the new `DCS-Radio-Voice-Control` folder and check that it contains `install.bat`,
   `configuration.bat`, and `run.bat`.

Do not run DCS Radio Voice Control from inside the ZIP preview. Do not put it in `Program Files`. Keep the
extracted folder after installation: it contains the program and is also needed for safe
updates and removal.

If Windows shows an **Unblock** checkbox in the ZIP's **Properties** window, select it before
extracting. This can prevent Windows from marking every extracted script as downloaded from
the internet.

## 2. Open PowerShell in the DCS Radio Voice Control folder

The easiest method is:

1. Open the extracted DCS Radio Voice Control folder in File Explorer.
2. Right-click an empty area inside the folder and select **Open in Terminal**.

A PowerShell terminal will open in that folder. Its prompt should end with the name of your
DCS Radio Voice Control folder, for example:

```text
PS C:\Users\your-name\DCS-Radio-Voice-Control>
```

Leave this window open for the following commands. You can paste a command into PowerShell
and press Enter to run it.

## 3. Install DCS Radio Voice Control

Make sure DCS is closed, then run:

```powershell
.\install.bat
```

The first run downloads and verifies the private runtime, SDL controller support, Whisper's
`base.en` model, and the Alan voice. The speech model alone is about 142 MiB, so this stage can
take several minutes. Later runs reuse files that are already valid.

Windows will ask whether the installer may make changes to the computer. Approve this prompt.
Administrator access is used to update the DCS program file; the other DCS Radio Voice Control files remain
in the extracted folder or your own user folders.

When installation succeeds, PowerShell prints JSON containing an `outcome`. On a first install
this describes the installed DCS panel. The configuration page then opens automatically. When applying a
later DCS Radio Voice Control patch it may instead say `updated_active_dcs_panel` or `already_current`.

### If DCS is in the usual location

No path is normally needed. DCS Radio Voice Control checks these locations:

- `C:\Program Files\Eagle Dynamics\DCS World`
- `C:\Program Files\Eagle Dynamics\DCS World OpenBeta`
- `C:\Program Files (x86)\Steam\steamapps\common\DCSWorld`

### If DCS is elsewhere, including another Steam library

Run the installer with the actual DCS folder. The correct folder is the one containing DCS's
`bin` and `Scripts` folders.

For a Steam installation, open Steam's **Library**, right-click **DCS World Steam Edition**,
select **Manage > Browse local files**, and copy the folder path from File Explorer's address
bar. For a standalone installation, right-click the DCS shortcut, select **Properties**, and
use the installation folder shown in the **Target** field rather than the path to the `.exe`
itself.

For example:

```powershell
.\install.bat `
  --dcs-install "D:\SteamLibrary\steamapps\common\DCSWorld" `
  --saved-games "$env:USERPROFILE\Saved Games\DCS"
```

The backtick at the end of the first two lines tells PowerShell that the command continues on
the next line. You may instead put the whole command on one line:

```powershell
.\install.bat --dcs-install "D:\SteamLibrary\steamapps\common\DCSWorld" --saved-games "$env:USERPROFILE\Saved Games\DCS"
```

Use `DCS.openbeta` instead of `DCS` in the Saved Games path if that is the folder DCS created.
Providing both paths is also the solution if DCS Radio Voice Control reports that it found more than one DCS
installation or more than one Saved Games DCS folder.

## 4. Configure your microphone, sound, and push-to-talk

On a first installation, `install.bat` opens the local configuration page automatically. If you
want to change the settings later, run:

```powershell
.\configuration.bat
```

If the browser does not open, browse to `http://127.0.0.1:34385/` while the configuration
window is running.

On the page:

1. Select your recording device and click **Run three-second level test**. Speak at your normal
   cockpit volume and confirm that the test reports a signal rather than silence.
2. Select the playback device on which you want to hear Alan and the accepted/rejected cues.
   Use **Test Alan voice** and the two cue-test buttons.
3. Under **Push to talk**, click **Learn a HOTAS button**, then press and release the button you
   want. If you do not want to use a controller, click **Use Space only**.
4. Leave the default `base.en`, CPU, and command-matching settings selected for the first test.
5. **Create a Desktop shortcut** is selected by default on the first installation. Leave it selected if
   you want an obvious manual way to start DCS Radio Voice Control later. You can move or pin that shortcut
   using the normal Windows controls.
6. Optional: select **Start DCS Radio Voice Control with Windows**. This installs a per-user sign-in entry;
   it does not require administrator permission.
7. On the first installation, click **Save configuration and start**. Your settings are saved,
   the configuration program closes cleanly, and DCS Radio Voice Control starts automatically.

When you open `configuration.bat` later, the button is **Save configuration** and does not
start another controller. Configuration is stored at
`%LOCALAPPDATA%\DCSRadioVoiceControl\config.json` and is retained during updates.

## 5. Run DCS Radio Voice Control in DCS

1. After **Save configuration and start**, leave the Terminal window open. DCS Radio Voice Control
   is now running and waiting for DCS.
2. Start DCS and enter a mission in which the radio menu is available. DCS Radio Voice Control will wait for a
   live DCS command catalogue.
3. Hold your configured HOTAS button, or Space, speak a command, and then release the button.

For later manual starts, use the **DCS Radio Voice Control** Desktop shortcut if you created it. You can
still run `.\run.bat` from the DCS Radio Voice Control folder. `run.bat`
checks whether the installed DCS hook matches this version and asks for administrator permission
only if the hook must be installed or updated.

For the first flight, start with commands that are easy to observe and do not trigger an
aircraft action:

```text
List commands
List ATC commands
Show F10
```

`List` makes Alan speak the immediate choices without changing the on-screen DCS menu. `Show`
starts guided menu mode. DCS Radio Voice Control keeps the DCS menu visible and accepts only choices shown on
that menu. A submenu choice advances one level; a displayed command executes and ends guided
mode. This is intended for commands you do not remember well.

While a guided menu is visible, you may say either the displayed option name or its bare
function key from `F1` through `F10`. For example, saying `F5` at the main radio menu selects
the item currently displayed beside F5. Function keys are always interpreted relative to the
visible menu; they are never fuzzy-matched or replayed as an absolute path. `Show F5` does not
execute a command: say `F5` by itself to select the displayed item.

For example:

```text
Show ATC
```

Opens the DCS **F5 ATC** menu.

```text
Show Biggin Hill
```

Opens the **Biggin Hill** submenu within ATC.

```text
Request Start-Up
```

Executes the displayed command.

For a familiar command, omit `Show` and give the complete command directly:

```text
Flight, Cover Me
```

DCS Radio Voice Control attempts that command once without putting you into guided navigation. Repeating the
same completed demand does not create a queue of additional menu selections; a different valid
command or menu choice must occur before the same command can be issued again.

To move back up or close the displayed menu:

```text
Previous Menu
```

Selects DCS's displayed **F11 Previous Menu** control.

```text
Exit Menu
```

Selects DCS's **F12 Exit** behaviour and closes the radio menu. You may also say `F11`, `Back`,
`F12`, or `Close Menu` respectively.

`Repeat` only says Alan's last spoken response again, principally after a `List` request. It
never sends or repeats a DCS action. If Alan has not spoken, DCS Radio Voice Control reports `Nothing spoken
to repeat.`

Rejected phrases that resemble a command are recorded for review in:

```text
%LOCALAPPDATA%\DCSRadioVoiceControl\pending_aliases.json
```

Application-side phrases such as an unrecognised `List` request are recorded separately in
`pending_meta_aliases.json` in the same folder. A `null` value is only a candidate and has no
effect. To approve an alias, replace `null` with one exact, unambiguous command path, for
example:

```json
"flight rejoin": "Flight > Rejoin Formation"
```

Reviewed mappings are loaded automatically. Their targets must exactly identify one current
DCS command; an invalid or ambiguous mapping is rejected rather than fuzzily reinterpreted.

DCS Radio Voice Control sends a command only when the recognition result passes both configured safety gates.
An accepted response confirms that DCS ran the menu action; a mission script can still decide
what gameplay effect follows.

To stop DCS Radio Voice Control, return to its PowerShell window and press Ctrl+C.

## Everyday use

If **Start DCS Radio Voice Control with Windows** is disabled, use this manual sequence for each session:

1. Double-click the **DCS Radio Voice Control** Desktop shortcut, or run `.\run.bat` from the DCS Radio Voice Control folder.
2. Start DCS and enter the mission.
3. Leave the DCS Radio Voice Control window open while flying.
4. Press Ctrl+C in that window when finished.

Only one DCS Radio Voice Control test or runner can listen to DCS at a time. Close any earlier DCS Radio Voice Control
PowerShell window before starting another one.

If **Start DCS Radio Voice Control with Windows** is enabled, no daily command is needed. The lightweight
controller starts when you sign in and waits for DCS. Whisper, Piper, the microphone, SDL, and
optional CUDA support remain unloaded until DCS has entered a mission and the current hook is
responding. DCS Radio Voice Control then becomes **Ready** and stops the voice worker automatically when DCS
exits. Disable the switch on the configuration page to stop automatic operation.

## Applying a DCS Radio Voice Control update or patch

You normally do **not** need to uninstall DCS Radio Voice Control first.

1. Close DCS and DCS Radio Voice Control.
2. Extract the new ZIP to a temporary folder, then open the
   `DCS-Radio-Voice-Control` folder it creates. You should see `install.bat` inside.
3. Select everything inside that folder, copy it, and paste it into your existing DCS Radio Voice Control folder.
   Choose **Replace the files in the destination** when Windows asks. Do not delete the old
   folder first; this preserves the downloaded runtime and models.
4. Open PowerShell in the existing DCS Radio Voice Control folder and run `.\run.bat`. DCS Radio Voice Control checks and,
   when safe, updates the hook automatically. It prompts for administrator permission only when
   a change is required.
5. If DCS was open, restart DCS when DCS Radio Voice Control asks. A hook already loaded into a running DCS
   process cannot be replaced in memory.
6. For an advanced manual check, run the status command from step 4 of this guide and confirm
   that `healthy` is `true`.

The installer checks hashes before changing anything. If DCS, VAICOM, another mod, or a DCS
update changed the radio-panel file after DCS Radio Voice Control was installed, the update is deliberately
refused. In that case, do not force-copy the hook and do not uninstall immediately: an old
backup may no longer be the correct file for the updated DCS version. Keep the error and status
output and resolve the changed base file before continuing.

## Advanced installation check

If you need to verify the installed DCS hook manually, run:

```powershell
.\runtime\python.exe .\tools\install.py status
```

A healthy installation reports `"healthy": true`. If you installed DCS using explicit
`--dcs-install` or `--saved-games` paths, supply the same paths to the status command.

## Optional speech models

The default `base.en` model is the right starting point. Larger models require more disk space,
memory, and recognition time. To install one for comparison:

```powershell
.\setup-stt.bat small.en
.\setup-stt.bat medium.en
```

`small.en` is about 466 MiB and `medium.en` about 1.5 GiB. After installation, select the model
on the configuration page and save the change.

An experimental NVIDIA CUDA 12 worker can be installed with:

```powershell
.\setup-stt.bat base.en cuda12
```

CPU mode remains the recommended baseline until testing on your PC shows that GPU recognition
improves the overall result without interfering with DCS.

## Troubleshooting

| What you see | What to do |
|---|---|
| `install.bat` is not found | PowerShell is not in the extracted DCS Radio Voice Control folder. Repeat step 2 and check the prompt. |
| DCS Radio Voice Control cannot locate DCS | Use `--dcs-install` and `--saved-games` as shown in step 3. This is expected for a Steam library on another drive. |
| More than one DCS or Saved Games folder was found | Supply both explicit paths so the installer cannot choose the wrong one. |
| A download fails | Check the internet connection, VPN/proxy, and antivirus history, then run the same batch file again. Setup safely reuses downloads that already passed verification. |
| The browser configuration page does not open | Leave the configuration window running and browse to `http://127.0.0.1:34385/`. If the port is already in use, close the older configuration window first. |
| The microphone test reports silence | Select a different recording device and check Windows **Settings > System > Sound > Input** and microphone privacy permissions. |
| The HOTAS is not listed | Connect and power it before opening the configuration page, then restart `configuration.bat`. Use **Space only** as a fallback. |
| DCS Radio Voice Control waits for DCS indefinitely | Enter an active mission, confirm the installation status is healthy, and make sure only one DCS Radio Voice Control runner is open. |
| DCS Radio Voice Control says `Restart DCS` | The file on disk is current but the running DCS process loaded an older hook. Close DCS completely and start it again. |
| DCS Radio Voice Control says `Repair required` | Run `install.bat` in PowerShell and preserve its complete output. DCS Radio Voice Control detected a missing, altered, or ambiguous installation that it will not overwrite automatically. |
| DCS has no DCS Radio Voice Control catalogue | Check `Saved Games\DCS\Logs\dcs.log`. Advanced checks: DCS should own UDP port `34383`, and DCS Radio Voice Control should own `34384`. |
| `Previous Menu` or `Exit Menu` is rejected as an ordinary command | Rerun `install.bat`; these controls require both the current Windows application and the current DCS hook. |
| The installer refuses because the panel changed | Stop. Do not overwrite it manually. Preserve the full error/status output; the safety check is protecting a DCS update or another modification. |

Text and JSONL diagnostic logs are stored under `%LOCALAPPDATA%\DCSRadioVoiceControl\logs`. Recorded audio
is not retained.

## Uninstalling

Close DCS and DCS Radio Voice Control, open PowerShell in the DCS Radio Voice Control folder, and run:

```powershell
.\uninstall.bat
```

Approve the administrator prompt. A successful uninstall restores the exact DCS file that was
backed up during installation and removes DCS Radio Voice Control's Saved Games state, local configuration,
logs, private runtime, speech models, and Alan voice. The extracted source folder is retained;
after the uninstaller reports success, you may delete that folder yourself.

Removal is refused if the installed DCS panel changed after installation or if the backup
cannot be verified. This is intentional: it prevents an older backup from overwriting a DCS
update or another modification. Do not manually replace the panel when this happens.

## Files DCS Radio Voice Control uses

| Purpose | Location |
|---|---|
| Program, private runtime, Whisper, and Alan | The extracted DCS Radio Voice Control folder |
| Settings | `%LOCALAPPDATA%\DCSRadioVoiceControl\config.json` |
| Logs | `%LOCALAPPDATA%\DCSRadioVoiceControl\logs` |
| Installation record and backups | `Saved Games\DCS\Scripts\DCSRadioVoiceControl` |
| DCS hook target | The active DCS installation's `Scripts\UI\RadioCommandDialogPanel\RadioCommandDialogsPanel.lua` |
