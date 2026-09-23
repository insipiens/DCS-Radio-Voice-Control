# Windows Installer Architecture

DRVC is a **per-user application**, not a system component. Installation and maintenance must leave Windows and DCS safe even when DRVC fails.

## Ownership

Program files:

```text
%LOCALAPPDATA%\Programs\DCS Radio Voice Control\
```

Persistent user data:

```text
%LOCALAPPDATA%\DCSRadioVoiceControl\
```

DRVC owns its application files, private dependencies, installation record, canonical shortcuts, startup registration and temporary files.

The user owns configuration, HOTAS/PTT settings and aliases. Updates and repair preserve them. Normal uninstall preserves them unless the user explicitly chooses to remove them.

DCS belongs to DCS. DRVC may modify only its defined radio-menu integration target and its own Saved Games integration state.

User-created copies, renamed shortcuts, taskbar pins or other derivatives are not DRVC's responsibility.

## Privileges

Normal install, update, configuration, repair, operation and removal run with ordinary user privileges.

DRVC must not install or modify Windows system files, services, drivers, scheduled tasks, system PATH or machine-wide configuration.

Any operation requiring privileges beyond the user/DRVC boundary requires explicit user authorisation when it occurs. The expected case is modifying the protected DCS integration file.

Elevation must be temporary and limited to that operation. Cancelling it must leave DCS unchanged. DRVC and its installer must not run generally as Administrator.

## DCS safety

Before modifying DCS, DRVC must:

1. identify the exact permitted target;
2. verify its current state;
3. preserve a verified original;
4. stage and validate the replacement;
5. replace only after those checks succeed;
6. verify the installed result.

A known DRVC-installed DCS file may be updated without another file-replacement prompt.

If the DCS file is unexpected, **stop**. There is no **Force** or **Replace anyway** option.

Uninstall must never restore an old backup over a DCS file that has subsequently changed. If safe restoration cannot be proven, leave the DCS file alone and report the condition.

## Updates and repair

DRVC has one stable installer identity. A newer installer updates the existing per-user installation rather than creating another copy.

Component maintenance follows:

```text
inspect -> stage -> verify -> replace -> verify
```

`maintenance.ps1` is the installer-facing reconciliation entry point. It classifies the private runtime, Whisper and Piper/voice components as `current`, `missing`, `update_required` or `repair_required`, and invokes only the setup operation needed for a non-current component.

Verified current components are left alone. Downloaded executable components use HTTPS and pinned cryptographic hashes before installation or execution.

Repair reconciles DRVC-owned components with their expected state. It does not attempt to repair Windows or DCS generally.

A failed download, validation, replacement or cancelled privilege request must not leave a partially installed live component.

## Shortcuts and startup

The installer/maintenance system owns DRVC's canonical shortcuts and user-level startup registration. Configuration determines whether optional Desktop and startup integration should exist.

No elevation is required for these operations.

## Uninstall

Uninstall removes DRVC-owned program files, canonical shortcuts, startup registration and disposable files.

It removes/restores the DCS integration only when doing so is verified safe.

Persistent configuration and aliases are retained by default; deleting them requires explicit user choice.

## Confirmation

The user authorises operations, not routine replacement of individual DRVC-owned files.

Explicit authorisation is required for:

- the initial external DCS modification;
- later operations requiring privileges beyond the user/DRVC boundary;
- deletion of persistent user data.

Confirmation must never bypass a safety check.

## Release checks

Before release verify:

1. clean per-user install and in-place update;
2. unchanged Python/Whisper/Piper components are not reinstalled;
3. HOTAS/PTT settings and custom aliases survive update and repair;
4. cancelling DCS elevation leaves DCS unchanged;
5. an unexpected DCS target is refused rather than overwritten;
6. uninstall cleans DRVC-owned artifacts without overwriting changed DCS files;
7. normal DRVC operations do not require Administrator privileges.

The intended scope does not include enterprise deployment, machine-wide installation or system-application servicing.
