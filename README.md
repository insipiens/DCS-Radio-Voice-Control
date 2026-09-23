# DCS Radio Voice Control

DCS Radio Voice Control lets you operate the DCS radio menu by voice.

Hold your HOTAS push-to-talk button, say a command such as:

> “Flight, Cover Me”

and release the button. The command is matched against the radio options actually available in DCS and, when the match is sufficiently clear, is executed.

Speech recognition runs locally on your PC. Recorded speech is not sent to a cloud service.

## Features

- Control DCS radio commands using your voice.
- Uses the live DCS radio menu, including mission-specific F10 commands.
- HOTAS push-to-talk or keyboard push-to-talk.
- Direct commands for things you already know.
- Guided voice navigation for commands you don't remember.
- Spoken command lists as a quick in-cockpit aide-mémoire.
- Local speech recognition using Whisper.
- Configurable command aliases, microphone, audio output and HOTAS button.
- Optional automatic startup with Windows; the application waits for DCS when it is not needed.

## Quick start

Requires Windows 11 x64 and DCS World.

1. Download `DCS-Radio-Voice-Control.zip`.

2. Open your **Downloads** folder, right-click `DCS-Radio-Voice-Control.zip` and select **Extract All**.

3. Choose your Windows user folder as the destination, for example:

   `C:\Users\your-name`

   Windows will create:

   `C:\Users\your-name\DCS-Radio-Voice-Control`

4. Open the new `DCS-Radio-Voice-Control` folder.

5. Right-click an empty area inside the folder and select **Open in Terminal**. This opens a PowerShell terminal in the correct folder.

6. Type:

   ```powershell
   .\install.bat
   ```

   and press **Enter**. Installation may take several minutes the first time.

7. When installation is complete, the configuration page opens automatically. Select your microphone, audio output and push-to-talk button. **Create a Desktop shortcut** is selected by default; you can also choose whether DCS Radio Voice Control starts with Windows. Then choose **Save configuration and start**.

8. DCS Radio Voice Control will start and wait for DCS. Start DCS and enter a mission.

For more detailed installation instructions, non-standard DCS locations and troubleshooting, see [INSTALLATION.md](INSTALLATION.md).

## Using DCS Radio Voice Control

There are three ways to use it: **Direct**, **List** and **Show**.

### Direct commands

If you know the command, simply say it:

> “Flight, Cover Me”

> “Two, Rejoin”

> “Ground Crew, Request Rearming”

The command is resolved against the options currently available in DCS and executed directly. You do not need to open or navigate the radio menu first.

### List — tell me what's available

`List` is an audible aide-mémoire. It tells you the choices without opening or changing the DCS radio menu.

For example:

> “List ATC commands”

responds with the currently available ATC choices.

You can also ask for another part of the menu:

> “List Flight commands”

> “List F10 commands”

Nothing is selected or executed by a `List` command.

### Show — let me navigate the menu

`Show` opens the DCS radio menu and starts guided navigation.

For example:

> “Show Menu”

The DCS radio menu appears. You can then speak one of the choices shown on screen:

> “Flight”

If that opens another menu, speak the next displayed choice:

> “Formation”

> “Go Line Abreast”

Each phrase selects only an option on the menu currently displayed. Selecting a submenu moves to that submenu; selecting a command executes it and finishes guided navigation.

You can also select displayed choices by saying their function key:

> “F2”

`Previous Menu` or `F11` goes back one level.

`Exit Menu` or `F12` closes the radio menu.

### Command aliases

DCS terminology is not always what a pilot would naturally say. DCS Radio Voice Control therefore supports configurable aliases.

For example:

> “Two, Rejoin”

can resolve to:

> `Wingman > Rejoin Formation`

Aliases can be edited without changing the program. They change the vocabulary used to identify a command; they do not allow an unrelated command to be selected.

## Configuration

Run:

```powershell
.\configuration.bat
```

The configuration page lets you select and test:

- microphone;
- audio output;
- HOTAS push-to-talk;
- speech-recognition model;
- command-matching settings;
- audio feedback; and
- Desktop shortcut; and
- automatic startup with Windows.

The Desktop shortcut gives you a simple manual way to start DCS Radio Voice Control. You can move or pin the shortcut using the normal Windows controls. If automatic startup is enabled, DCS Radio Voice Control waits quietly until DCS is running and activates voice control when required.

## Updating

You normally do not need to uninstall before updating.

Close DCS and DCS Radio Voice Control, copy the files from the new version over your existing installation, and run `run.bat`.

Your configuration and downloaded speech models are retained.

See [INSTALLATION.md](INSTALLATION.md) for detailed update instructions.

## Uninstalling

Close DCS and run:

```powershell
.\uninstall.bat
```

The uninstaller restores the DCS file backed up during installation and removes the files managed by DCS Radio Voice Control.

See [INSTALLATION.md](INSTALLATION.md) if the uninstaller reports that DCS has changed since installation.

## More information

[INSTALLATION.md](INSTALLATION.md) — installation, updates, unusual DCS locations and troubleshooting.
