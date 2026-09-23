# Windows Installer Architecture

This document defines the minimum installation and maintenance contract for DCS Radio Voice Control (DRVC).

The installer is deliberately a **per-user installer**. DRVC is not a system component and must not behave like one.

## Safety objective

A DRVC failure must fail locally.

The worst credible installation, update, repair, or uninstall failure should leave **DRVC requiring repair**, not leave DCS or Windows requiring repair.

DRVC must not modify a file, setting, or application outside its defined ownership boundary merely because doing so would make installation or repair easier.

## 1. Application identity

DRVC has one stable Windows application identity across releases.

- The installer AppId must remain unchanged between versions.
- A newer installer upgrades the existing installation in place.
- DRVC appears normally in Windows Installed Apps.
- Installing a newer version must not create a second independent DRVC installation.

Version changes do not change application identity.

## 2. Per-user installation

Normal installation, update, configuration, repair, operation, and removal run with the user's normal privileges.

Program files belong under:

```text
%LOCALAPPDATA%\Programs\DCS Radio Voice Control\
```

Persistent user data belongs under:

```text
%LOCALAPPDATA%\DCSRadioVoiceControl\
```

The application must not require machine-wide installation.

DRVC must not install or modify Windows system DLLs, services, drivers, scheduled tasks, file associations, machine-wide environment variables, or the system PATH.

## 3. Privilege boundary

Installing DRVC does not grant continuing administrative authority.

DRVC may manage its own per-user files and user-level Windows integration without elevation.

Any operation requiring privileges beyond the user/DRVC boundary requires explicit user authorisation at the time of that operation.

The expected exception is the protected DCS integration file when DCS is installed in a location requiring elevation.

Elevation must therefore be:

- requested only when a protected DCS integration change is actually required;
- initiated by an explicit user-authorised operation;
- temporary;
- limited to the DCS integration operation;
- safely cancellable.

Cancelling or refusing elevation must leave DCS unchanged and DRVC in a recoverable state.

The main DRVC application and normal installer must not run generally as Administrator.

## 4. Ownership

Persistent artifacts are divided into three ownership classes.

### DRVC-managed

Examples:

- application files;
- bundled/private Python runtime;
- Whisper worker and models;
- Piper and supplied voice files;
- canonical Start Menu and Desktop shortcuts;
- DRVC user-level startup registration;
- DRVC temporary files and caches.

DRVC may create, validate, update, repair, and remove these canonical artifacts.

If a user copies, renames, moves, or independently modifies an artifact outside the canonical location managed by DRVC, that copy is no longer DRVC's responsibility.

### User-owned

Examples:

- `config.json`;
- HOTAS/PTT assignments;
- microphone and audio choices;
- recognition settings;
- `aliases.json`, including learned and custom aliases.

Updates and repair must preserve user-owned data. Schema migration may transform it when required, but must not silently replace it with defaults.

Normal uninstall should preserve user-owned data unless the user explicitly chooses to remove it.

### External integration

DCS belongs to DCS, not DRVC.

DRVC may modify only the specifically defined DCS radio-menu integration target and its own Saved Games integration state.

No general-purpose maintenance operation may use the DCS integration mechanism to write arbitrary files elsewhere in DCS, Windows, or another application.

## 5. DCS file safety

The DCS integration is the highest-risk installation operation.

Before first modification DRVC must:

1. identify the expected DCS installation and exact permitted target;
2. inspect the current target state;
3. preserve a verified original;
4. stage the proposed replacement separately;
5. validate the staged result;
6. replace the target only after those checks succeed;
7. verify the resulting installed state.

Updates may replace a DCS file without another confirmation only when DRVC can prove that the current file is the known DRVC-managed state and the preserved original is still valid.

If the current DCS file is unexpected, DRVC must stop safely. The normal user interface must not offer **Force**, **Replace anyway**, or an equivalent bypass of the safety check.

Uninstall must not restore an old backup over a DCS file that has subsequently changed. If safe restoration cannot be proven, DRVC leaves the external file alone and reports the condition.

A DCS update, another mod, a missing manifest, or an unknown hash is a reason to re-evaluate the integration state, not permission to overwrite it.

## 6. Updates and repair

Running a newer DRVC installer performs an in-place update.

An update must:

- replace only DRVC-managed program components that require replacement;
- preserve user-owned configuration and aliases;
- leave verified current dependencies untouched;
- update the DCS integration only when required and safe;
- clean temporary staging files.

Repair reconciles the desired DRVC state with the actual state. It repairs DRVC-owned components and the validated DRVC integration; it does not attempt to repair Windows or DCS generally.

Component maintenance follows:

```text
inspect -> stage -> verify -> replace -> verify
```

A failed download, validation, replacement, or cancelled privilege request must not leave a partially installed live component.

## 7. Component verification

Downloaded executable components must be obtained over HTTPS and cryptographically verified before they are installed or executed.

Where practical, installed components should also have a version/hash check or a narrowly scoped self-test.

The component manifest records what DRVC believes is installed. Repair must verify reality rather than trusting the manifest alone.

A component already at the required verified version is not downloaded or reinstalled merely because Setup or Repair was run.

## 8. Shortcuts and startup

The installer/maintenance system owns the canonical DRVC shortcuts.

Configuration records whether optional integration such as a Desktop shortcut or Start with Windows is desired. Maintenance reconciles the canonical artifact with that setting.

DRVC does not search for or delete user-created copies, renamed shortcuts, taskbar pins, or other derivatives.

User-level startup registration must have one defined owner and must not require elevation.

## 9. Uninstall

Uninstall removes canonical DRVC-managed artifacts and safely removes or restores DRVC's DCS integration where the recorded state proves that this is safe.

Normal uninstall:

- removes DRVC program files;
- removes canonical shortcuts and DRVC startup registration;
- removes disposable DRVC files;
- attempts only a verified-safe DCS integration removal/restoration;
- preserves user configuration and aliases by default.

Removing persistent user data requires a separate explicit user choice.

Uninstall must not search the machine for files that merely resemble DRVC artifacts.

## 10. Confirmation model

The user authorises operations, not individual routine file replacements.

No additional prompt is required to replace verified DRVC-owned program files during an authorised Install, Update, or Repair operation.

Explicit authorisation is required for:

- the initial external DCS modification;
- any later operation requiring privilege beyond the user/DRVC boundary;
- deletion of persistent user-owned configuration.

A confirmation prompt must never be used as a way to bypass a failed safety check.

## 11. Minimum release checks

Before an installer build is considered suitable for release, verify at least:

1. clean per-user installation;
2. in-place application update;
3. unchanged Python/Whisper/Piper components are not unnecessarily downloaded or reinstalled;
4. HOTAS/PTT settings and a distinctive custom alias survive the update unchanged;
5. DRVC can be repaired without resetting user data;
6. cancelling any requested DCS elevation leaves DCS unchanged;
7. an unexpected/changed DCS integration target is refused rather than overwritten;
8. uninstall removes canonical DRVC artifacts and does not overwrite an unexpectedly changed DCS file;
9. normal installation, update, repair, configuration, operation, and application-only uninstall do not require Administrator privileges.

These are application-level installation checks. DRVC does not need enterprise deployment, machine-wide installation, Windows service management, or other system-application servicing features unless the product scope changes.
