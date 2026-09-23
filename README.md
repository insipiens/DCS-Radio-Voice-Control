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

1. Download and extract `DCS-Radio-Voice-Control.zip` to a permanent folder in your Windows user directory, for example:

   `C:\Users\your-name\DCS-Radio-Voice-Control`

   Do not install it in `Program Files` or run it directly from the ZIP. Keep this folder after installation — it is the application folder.

2. Open the extracted `DCS-Radio-Voice-Control` folder and run:

   ```powershell
   .\install.bat
   ```

3. Configure your microphone, audio and push-to-talk:

   ```powershell
   .\configuration.bat
   ```

4. Start DCS Radio Voice Control:

   ```powershell
   .\run.bat
   ```

5. Start DCS and enter a mission.

For a step-by-step installation guide, non-standard DCS locations and troubleshooting, see [INSTALLATION.md](INSTALLATION.md).

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
- automatic startup with Windows.

If automatic startup is enabled, DCS Radio Voice Control waits quietly until DCS is running and activates voice control when required.

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
