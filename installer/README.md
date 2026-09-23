# Windows installer

Compile `DCSRadioVoiceControl.iss` with Inno Setup 7. The output is `dist\DCS-Radio-Voice-Control-Setup.exe`.

The installer is per-user and uses a stable AppId for in-place updates. Setup reconciles the private runtime/speech components, then invokes the existing verified DCS integration. Only a required protected DCS file change requests elevation.

Test the installed Start-menu entries for **DCS Radio Voice Control**, **Configure** and **Repair**, then test removal through Windows **Installed apps**. Normal uninstall preserves configuration/aliases unless the user explicitly chooses to delete them.
