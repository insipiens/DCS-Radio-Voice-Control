#!/usr/bin/env python3
"""Install, inspect, or remove the experimental DCS Radio Voice Control DCS radio hook."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any
from uuid import uuid4

if not __package__:
    # The embeddable runtime uses an explicit _pth file and therefore does not add
    # this script's directory automatically. Establish the repository paths before
    # importing the application and tools packages.
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))
    sys.path.insert(0, str(project_root / "src"))

from dcs_radio_voice_control.installation_state import (
    load_installation_state,
    save_installation_state,
)
from tools.build_radio_overlay import BEGIN_MARKER, LEGACY_BEGIN_MARKER, build_overlay

RELATIVE_PANEL = Path("Scripts/UI/RadioCommandDialogPanel/RadioCommandDialogsPanel.lua")
STATE_DIRECTORY = Path("Scripts/DCSRadioVoiceControl")
MANIFEST_NAME = "install.json"


class InstallError(RuntimeError):
    """A safe installation or removal could not be completed."""


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def install_hook(dcs_install: Path, saved_games: Path, hook: Path) -> dict[str, Any]:
    """Append DCS Radio Voice Control to the radio panel DCS actually loads from its installation."""

    dcs_install = dcs_install.resolve()
    saved_games = saved_games.resolve()
    hook = hook.resolve()
    core_panel = dcs_install / RELATIVE_PANEL
    state_directory = saved_games / STATE_DIRECTORY
    manifest_path = state_directory / MANIFEST_NAME

    if not core_panel.is_file():
        raise InstallError(f"DCS radio-panel file was not found: {core_panel}")
    if not hook.is_file() or BEGIN_MARKER not in hook.read_bytes():
        raise InstallError(f"DCS Radio Voice Control hook is missing or invalid: {hook}")
    if LEGACY_BEGIN_MARKER in core_panel.read_bytes():
        raise InstallError(
            "The former CombatAI hook is still installed. Use that installation's "
            "uninstall.bat before installing DCS Radio Voice Control."
        )

    migrated: dict[str, Any] | None = None
    if manifest_path.exists():
        existing = _read_manifest(manifest_path)
        if _is_legacy_saved_games_install(existing, saved_games):
            migrated = _remove_legacy_saved_games_install(saved_games, existing)
        else:
            return _update_active_installation(
                core_panel,
                state_directory,
                manifest_path,
                hook,
                existing,
            )

    if BEGIN_MARKER in core_panel.read_bytes():
        raise InstallError(
            "The active radio-panel file already contains DCS Radio Voice Control but has no usable manifest; "
            "manual inspection is required"
        )

    state_directory.mkdir(parents=True, exist_ok=True)
    backup_directory = state_directory / "backups"
    backup_directory.mkdir(parents=True, exist_ok=True)
    backup_path = backup_directory / f"RadioCommandDialogsPanel.{uuid4().hex}.lua"
    shutil.copy2(core_panel, backup_path)

    staged_path = core_panel.with_name(core_panel.name + f".{uuid4().hex}.dcs_radio_voice_control-new")
    installed = False
    try:
        base_sha256 = build_overlay(core_panel, hook, staged_path)
        installed_sha256 = file_hash(staged_path)
        os.replace(staged_path, core_panel)
        installed = True

        manifest: dict[str, Any] = {
            "schema": 2,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "dcs_install": str(dcs_install),
            "saved_games": str(saved_games),
            "target": str(core_panel),
            "base_kind": "active_dcs_panel",
            "base_sha256": base_sha256,
            "installed_sha256": installed_sha256,
            "backup": str(backup_path),
        }
        if migrated is not None:
            manifest["migrated_legacy_install"] = migrated["manifest_archive"]
        _write_json_atomic(manifest_path, manifest)
        return manifest
    except BaseException:
        if staged_path.exists():
            staged_path.unlink()
        if installed:
            _copy_atomic(backup_path, core_panel)
        raise


def _update_active_installation(
    core_panel: Path,
    state_directory: Path,
    manifest_path: Path,
    hook: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Replace only a verified DCS Radio Voice Control overlay while preserving its original backup."""

    target = Path(manifest["target"])
    backup = Path(manifest["backup"])
    if manifest.get("schema") != 2 or manifest.get("base_kind") != "active_dcs_panel":
        raise InstallError("The active DCS Radio Voice Control manifest cannot be updated safely")
    if target.resolve() != core_panel.resolve():
        raise InstallError("Manifest target does not belong to the selected DCS installation")
    _validate_backup_location(backup, state_directory)
    if not target.is_file() or file_hash(target) != manifest["installed_sha256"]:
        raise InstallError(
            "The installed radio-panel file has changed since DCS Radio Voice Control was installed; "
            "refusing to overwrite changes made by DCS, VAICOM, or another mod"
        )
    if not backup.is_file() or file_hash(backup) != manifest["base_sha256"]:
        raise InstallError(f"The recorded backup is missing or altered: {backup}")

    staged_path = core_panel.with_name(core_panel.name + f".{uuid4().hex}.dcs_radio_voice_control-new")
    previous_path = core_panel.with_name(core_panel.name + f".{uuid4().hex}.dcs_radio_voice_control-old")
    replaced = False
    try:
        base_sha256 = build_overlay(backup, hook, staged_path)
        if base_sha256 != manifest["base_sha256"]:
            raise InstallError("The verified installation backup no longer matches its manifest")
        installed_sha256 = file_hash(staged_path)
        if installed_sha256 == manifest["installed_sha256"]:
            result = dict(manifest)
            result["outcome"] = "already_current"
            return result

        shutil.copy2(core_panel, previous_path)
        os.replace(staged_path, core_panel)
        replaced = True
        updated = dict(manifest)
        updated["installed_sha256"] = installed_sha256
        updated["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_json_atomic(manifest_path, updated)
        result = dict(updated)
        result["outcome"] = "updated_active_dcs_panel"
        return result
    except BaseException:
        if replaced and previous_path.is_file():
            _copy_atomic(previous_path, core_panel)
        raise
    finally:
        for temporary in (staged_path, previous_path):
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def uninstall_hook(dcs_install: Path, saved_games: Path) -> dict[str, Any]:
    dcs_install = dcs_install.resolve()
    saved_games = saved_games.resolve()
    state_directory = saved_games / STATE_DIRECTORY
    manifest_path = state_directory / MANIFEST_NAME
    if not manifest_path.is_file():
        raise InstallError(f"No active DCS Radio Voice Control installation manifest was found: {manifest_path}")

    manifest = _read_manifest(manifest_path)
    if _is_legacy_saved_games_install(manifest, saved_games):
        return _remove_legacy_saved_games_install(saved_games, manifest)

    target = Path(manifest["target"])
    backup = Path(manifest["backup"])
    expected_target = dcs_install / RELATIVE_PANEL
    if target.resolve() != expected_target.resolve():
        raise InstallError("Manifest target does not belong to the selected DCS installation")
    _validate_backup_location(backup, state_directory)
    if not target.is_file():
        raise InstallError(f"Installed radio-panel file is missing: {target}")
    if file_hash(target) != manifest["installed_sha256"]:
        raise InstallError(
            "The installed radio-panel file has changed since DCS Radio Voice Control was installed; "
            "refusing to overwrite changes made by DCS, VAICOM, or another mod"
        )
    if not backup.is_file() or file_hash(backup) != manifest["base_sha256"]:
        raise InstallError(f"The recorded backup is missing or altered: {backup}")
    if manifest["base_kind"] != "active_dcs_panel":
        raise InstallError(f"Unknown base kind in manifest: {manifest['base_kind']!r}")

    _copy_atomic(backup, target)
    archive = _archive_manifest(manifest_path, state_directory, "removed")
    return {
        "outcome": "restored_active_dcs_panel",
        "manifest_archive": str(archive),
        "backup": str(backup),
    }


def purge_installation(
    dcs_install: Path, saved_games: Path, local_app_data: Path | None
) -> dict[str, Any]:
    """Remove the verified DCS hook plus every machine-level DCS Radio Voice Control artifact."""

    dcs_install = dcs_install.resolve()
    saved_games = saved_games.resolve()
    state_directory = saved_games / STATE_DIRECTORY
    manifest_path = state_directory / MANIFEST_NAME
    active_target = dcs_install / RELATIVE_PANEL

    if manifest_path.is_file():
        result = uninstall_hook(dcs_install, saved_games)
    else:
        if active_target.is_file() and BEGIN_MARKER in active_target.read_bytes():
            raise InstallError(
                "The active radio-panel file still contains DCS Radio Voice Control but no usable manifest "
                "exists; refusing an unverifiable removal"
            )
        result = {"outcome": "dcs_hook_already_absent"}

    cleanup_targets = [("Saved Games state", state_directory)]
    cleanup_errors: list[str] = []
    if local_app_data is None:
        cleanup_errors.append(
            "Windows LOCALAPPDATA is unavailable; user settings cannot be located"
        )
    else:
        cleanup_targets.append(("local settings and logs", local_app_data / "DCSRadioVoiceControl"))

    removed: list[str] = []
    for label, target in cleanup_targets:
        try:
            if target.exists():
                shutil.rmtree(target)
            if target.exists():
                cleanup_errors.append(f"{label} remains at {target}")
            else:
                removed.append(str(target))
        except OSError as exc:
            cleanup_errors.append(f"could not remove {label} at {target}: {exc}")

    if active_target.is_file() and BEGIN_MARKER in active_target.read_bytes():
        cleanup_errors.append(f"the DCS Radio Voice Control hook remains in {active_target}")
    if os.name == "nt":
        try:
            import winreg

            run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, run_key) as key:
                try:
                    winreg.DeleteValue(key, "DCS Radio Voice Control")
                except FileNotFoundError:
                    pass
        except OSError as exc:
            cleanup_errors.append(f"could not remove Start with Windows registration: {exc}")
    if cleanup_errors:
        raise InstallError("cleanup incomplete:\n  " + "\n  ".join(cleanup_errors))

    result["purged"] = removed
    return result


def installation_status(dcs_install: Path, saved_games: Path) -> dict[str, Any]:
    dcs_install = dcs_install.resolve()
    saved_games = saved_games.resolve()
    manifest_path = saved_games / STATE_DIRECTORY / MANIFEST_NAME
    active_target = dcs_install / RELATIVE_PANEL
    if not manifest_path.is_file():
        return {
            "installed": False,
            "target_exists": active_target.is_file(),
            "target": str(active_target),
        }

    manifest = _read_manifest(manifest_path)
    recorded_target = Path(manifest["target"])
    legacy_install = _is_legacy_saved_games_install(manifest, saved_games)
    target_matches = recorded_target.resolve() == active_target.resolve()
    actual_hash = file_hash(recorded_target) if recorded_target.is_file() else None
    recorded_file_intact = actual_hash == manifest["installed_sha256"]
    return {
        "installed": True,
        "healthy": not legacy_install and target_matches and recorded_file_intact,
        "legacy_install": legacy_install,
        "recorded_file_intact": recorded_file_intact,
        "target_matches_selected_install": target_matches,
        "target": str(recorded_target),
        "active_target": str(active_target),
        "base_kind": manifest["base_kind"],
        "installed_at": manifest["installed_at"],
        "expected_sha256": manifest["installed_sha256"],
        "actual_sha256": actual_hash,
    }


def installation_preflight(
    dcs_install: Path, saved_games: Path, hook: Path
) -> dict[str, Any]:
    """Classify installation health without modifying DCS or requiring elevation."""

    dcs_install = dcs_install.resolve()
    saved_games = saved_games.resolve()
    hook = hook.resolve()
    target = dcs_install / RELATIVE_PANEL
    manifest_path = saved_games / STATE_DIRECTORY / MANIFEST_NAME
    if not target.is_file():
        return {"state": "repair_required", "detail": f"DCS radio-panel file is missing: {target}"}
    if not hook.is_file() or BEGIN_MARKER not in hook.read_bytes():
        return {"state": "repair_required", "detail": f"DCS Radio Voice Control hook is missing or invalid: {hook}"}
    if LEGACY_BEGIN_MARKER in target.read_bytes():
        return {
            "state": "repair_required",
            "detail": (
                "The former CombatAI hook is still installed. Use that installation's "
                "uninstall.bat before installing DCS Radio Voice Control."
            ),
        }
    if not manifest_path.is_file():
        if BEGIN_MARKER in target.read_bytes():
            return {
                "state": "repair_required",
                "detail": "The DCS panel contains DCS Radio Voice Control but its installation record is missing.",
            }
        return {"state": "install_required", "target": str(target)}

    try:
        manifest = _read_manifest(manifest_path)
        status = installation_status(dcs_install, saved_games)
        if not status.get("healthy"):
            return {
                "state": "repair_required",
                "detail": "The installed DCS hook or its installation record has changed.",
                "status": status,
            }
        backup = Path(manifest["backup"])
        _validate_backup_location(backup, saved_games / STATE_DIRECTORY)
        if not backup.is_file() or file_hash(backup) != manifest["base_sha256"]:
            return {
                "state": "repair_required",
                "detail": f"The verified DCS panel backup is missing or altered: {backup}",
            }
        with tempfile.TemporaryDirectory(prefix="DCSRadioVoiceControl-preflight-") as directory:
            candidate = Path(directory) / "RadioCommandDialogsPanel.lua"
            base_sha256 = build_overlay(backup, hook, candidate)
            if base_sha256 != manifest["base_sha256"]:
                return {
                    "state": "repair_required",
                    "detail": "The DCS panel backup no longer matches its installation record.",
                }
            expected_sha256 = file_hash(candidate)
    except (InstallError, OSError, ValueError) as exc:
        return {"state": "repair_required", "detail": str(exc)}

    return {
        "state": "current" if expected_sha256 == manifest["installed_sha256"] else "update_required",
        "target": str(target),
        "installed_sha256": manifest["installed_sha256"],
        "expected_sha256": expected_sha256,
    }


def discover_saved_games(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    recorded = _recorded_path("saved_games")
    if recorded is not None and recorded.is_dir():
        return recorded
    candidates = [
        Path.home() / "Saved Games" / name
        for name in ("DCS", "DCS.openbeta")
        if (Path.home() / "Saved Games" / name).is_dir()
    ]
    return _require_one(candidates, "Saved Games DCS directory", "--saved-games")


def discover_dcs_install(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    recorded = _recorded_path("dcs_install")
    if recorded is not None and (recorded / RELATIVE_PANEL).is_file():
        return recorded
    candidates: list[Path] = []
    configured = os.environ.get("DCS_INSTALL_DIR")
    if configured:
        candidates.append(Path(configured))
    for environment_name, suffix in (
        ("ProgramFiles", Path("Eagle Dynamics/DCS World")),
        ("ProgramFiles", Path("Eagle Dynamics/DCS World OpenBeta")),
        ("ProgramFiles(x86)", Path("Steam/steamapps/common/DCSWorld")),
    ):
        root = os.environ.get(environment_name)
        if root:
            candidates.append(Path(root) / suffix)
    valid = []
    seen = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen and (resolved / RELATIVE_PANEL).is_file():
            valid.append(resolved)
            seen.add(resolved)
    return _require_one(valid, "DCS installation", "--dcs-install")


def _recorded_path(name: str) -> Path | None:
    try:
        state = load_installation_state()
    except OSError:
        return None
    value = state.get(name)
    return Path(value).resolve() if isinstance(value, str) and value else None


def _require_one(candidates: list[Path], description: str, option: str) -> Path:
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise InstallError(f"Could not locate the {description}; specify it with {option}")
    choices = "\n  ".join(str(candidate) for candidate in candidates)
    raise InstallError(f"More than one {description} was found; use {option}:\n  {choices}")


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"Cannot read installation manifest {path}: {exc}") from exc
    required = {
        "schema",
        "installed_at",
        "target",
        "base_kind",
        "base_sha256",
        "installed_sha256",
        "backup",
    }
    if (
        not isinstance(value, dict)
        or value.get("schema") not in (1, 2)
        or not required <= value.keys()
    ):
        raise InstallError(f"Installation manifest is invalid: {path}")
    for field in ("target", "base_kind", "backup", "installed_at"):
        if not isinstance(value[field], str) or not value[field]:
            raise InstallError(f"Installation manifest field {field!r} is invalid: {path}")
    for field in ("base_sha256", "installed_sha256"):
        digest = value[field]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise InstallError(f"Installation manifest field {field!r} is invalid: {path}")
    return value


def _is_legacy_saved_games_install(manifest: dict[str, Any], saved_games: Path) -> bool:
    if manifest.get("schema") != 1:
        return False
    return Path(manifest["target"]).resolve() == (saved_games.resolve() / RELATIVE_PANEL).resolve()


def _remove_legacy_saved_games_install(
    saved_games: Path, manifest: dict[str, Any]
) -> dict[str, Any]:
    """Safely remove the inactive Saved Games overlay produced by early DCS Radio Voice Control builds."""

    saved_games = saved_games.resolve()
    state_directory = saved_games / STATE_DIRECTORY
    manifest_path = state_directory / MANIFEST_NAME
    target = saved_games / RELATIVE_PANEL
    backup = Path(manifest["backup"])

    if Path(manifest["target"]).resolve() != target.resolve():
        raise InstallError("Legacy manifest target is not the expected Saved Games panel")
    _validate_backup_location(backup, state_directory)
    if not backup.is_file() or file_hash(backup) != manifest["base_sha256"]:
        raise InstallError(f"The recorded backup is missing or altered: {backup}")

    actual_sha256 = file_hash(target) if target.is_file() else None
    if actual_sha256 == manifest["installed_sha256"]:
        if manifest["base_kind"] == "saved_games_override":
            _copy_atomic(backup, target)
            outcome = "restored_legacy_saved_games_override"
        elif manifest["base_kind"] == "dcs_core":
            target.unlink()
            outcome = "removed_legacy_generated_override"
        else:
            raise InstallError(f"Unknown legacy base kind: {manifest['base_kind']!r}")
    elif (
        manifest["base_kind"] == "saved_games_override"
        and actual_sha256 == manifest["base_sha256"]
    ):
        outcome = "legacy_saved_games_override_already_restored"
    elif manifest["base_kind"] == "dcs_core" and actual_sha256 is None:
        outcome = "legacy_generated_override_already_removed"
    else:
        raise InstallError(
            "The legacy Saved Games radio-panel file has changed to an unrecognised state; "
            "refusing automatic migration"
        )

    archive = _archive_manifest(manifest_path, state_directory, "migrated")
    return {"outcome": outcome, "manifest_archive": str(archive), "backup": str(backup)}


def _validate_backup_location(backup: Path, state_directory: Path) -> None:
    expected = (state_directory / "backups").resolve()
    if backup.resolve().parent != expected:
        raise InstallError("Manifest backup does not belong to the DCS Radio Voice Control backup directory")


def _archive_manifest(manifest_path: Path, state_directory: Path, action: str) -> Path:
    archive = state_directory / (
        f"install.{action}."
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "."
        + uuid4().hex
        + ".json"
    )
    os.replace(manifest_path, archive)
    return archive


def _write_json_atomic(destination: Path, value: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=destination.name + ".",
        suffix=".tmp",
        dir=destination.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            json.dump(value, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, destination)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _copy_atomic(source: Path, destination: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=destination.name + ".",
        suffix=".restore",
        dir=destination.parent,
    )
    os.close(descriptor)
    try:
        shutil.copy2(source, temporary_name)
        os.replace(temporary_name, destination)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _windows_command_line(arguments: list[str]) -> str:
    """Quote arguments according to the Windows CommandLineToArgvW convention."""

    return subprocess.list2cmdline(arguments)


def _is_windows_administrator() -> bool:
    if os.name != "nt":
        return False
    import ctypes

    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def _installation_requires_elevation(dcs_install: Path) -> bool:
    """Return whether the target DCS panel directory is not writable by this user."""
    target_directory = dcs_install / RELATIVE_PANEL.parent
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix="DCSRadioVoiceControl-permission-",
            suffix=".tmp",
            dir=target_directory,
        )
    except OSError:
        return True
    else:
        os.close(descriptor)
        Path(temporary_name).unlink(missing_ok=True)
        return False


def _run_elevated(arguments: list[str]) -> int:
    """Relaunch this installer through UAC and return the child exit code."""

    if os.name != "nt":
        raise InstallError("Administrator elevation is available only on Windows")

    import ctypes
    from ctypes import wintypes

    class ShellExecuteInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", wintypes.ULONG),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", wintypes.LPVOID),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIconOrMonitor", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(ShellExecuteInfo)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    result_descriptor, result_name = tempfile.mkstemp(
        prefix="DCSRadioVoiceControl-elevated-", suffix=".txt"
    )
    os.close(result_descriptor)
    result_path = Path(result_name)
    parameters = _windows_command_line(
        [
            str(Path(__file__).resolve()),
            *arguments,
            "--elevated",
            "--result-file",
            str(result_path),
        ]
    )
    info = ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x00000040  # SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = sys.executable
    info.lpParameters = parameters
    info.lpDirectory = str(Path(__file__).resolve().parents[1])
    info.nShow = 1  # SW_SHOWNORMAL

    try:
        if not shell32.ShellExecuteExW(ctypes.byref(info)):
            error = ctypes.get_last_error()
            if error == 1223:
                raise InstallError("Administrator permission was cancelled")
            raise InstallError(
                f"Could not request administrator permission (Windows error {error})"
            )

        wait_result = kernel32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
        if wait_result == 0xFFFFFFFF:
            error = ctypes.get_last_error()
            raise InstallError(f"Could not wait for elevated installer (Windows error {error})")
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(exit_code)):
            error = ctypes.get_last_error()
            raise InstallError(f"Could not read elevated installer result (Windows error {error})")
        code = int(exit_code.value)
        output = result_path.read_text(encoding="utf-8") if result_path.stat().st_size else ""
        if output:
            print(output, end="", file=sys.stderr if code else sys.stdout)
        return code
    finally:
        if info.hProcess:
            kernel32.CloseHandle(info.hProcess)
        try:
            result_path.unlink()
        except FileNotFoundError:
            pass


def _emit_result(text: str, result_file: Path | None, *, error: bool = False) -> None:
    if result_file is None:
        print(text, file=sys.stderr if error else sys.stdout)
        return
    result_file.write_text(text + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    install_parser = commands.add_parser("install", help="safely append and install the hook")
    install_parser.add_argument("--dcs-install", type=Path)
    install_parser.add_argument("--saved-games", type=Path)
    install_parser.add_argument(
        "--hook",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "dcs" / "DCSRadioVoiceControl.radio_hook.lua",
    )
    install_parser.add_argument("--elevated", action="store_true", help=argparse.SUPPRESS)
    install_parser.add_argument("--result-file", type=Path, help=argparse.SUPPRESS)

    for name in ("preflight", "status", "uninstall"):
        command_parser = commands.add_parser(name)
        command_parser.add_argument("--dcs-install", type=Path)
        command_parser.add_argument("--saved-games", type=Path)
        if name == "preflight":
            command_parser.add_argument(
                "--hook",
                type=Path,
                default=Path(__file__).resolve().parents[1] / "dcs" / "DCSRadioVoiceControl.radio_hook.lua",
            )
        if name == "uninstall":
            command_parser.add_argument(
                "--purge",
                action="store_true",
                help="remove Saved Games state, local settings, logs, and backups",
            )
            command_parser.add_argument(
                "--remove-state",
                action="store_true",
                help="remove verified Saved Games integration state but preserve user settings",
            )
            command_parser.add_argument("--elevated", action="store_true", help=argparse.SUPPRESS)
            command_parser.add_argument("--result-file", type=Path, help=argparse.SUPPRESS)

    args = parser.parse_args()
    try:
        saved_games = discover_saved_games(args.saved_games)
        dcs_install = discover_dcs_install(args.dcs_install)
        if args.command == "install" and not args.elevated:
            preflight = installation_preflight(dcs_install, saved_games, args.hook)
            if preflight.get("state") == "current":
                save_installation_state(
                    Path(__file__).resolve().parents[1],
                    dcs_install,
                    saved_games,
                )
                result = dict(preflight)
                result["outcome"] = "already_current"
                _emit_result(json.dumps(result, indent=2, sort_keys=True), None)
                return 0
            if preflight.get("state") == "repair_required":
                raise InstallError(preflight.get("detail", "DCS integration requires repair"))
        if args.command in ("install", "uninstall") and os.name == "nt":
            if args.elevated and not _is_windows_administrator():
                raise InstallError("The elevated installer did not receive administrator rights")
            if (
                not args.elevated
                and not _is_windows_administrator()
                and _installation_requires_elevation(dcs_install)
            ):
                code = _run_elevated(sys.argv[1:])
                if code == 0 and args.command == "install":
                    save_installation_state(
                        Path(__file__).resolve().parents[1],
                        dcs_install,
                        saved_games,
                    )
                return code
        if args.command == "install":
            result = install_hook(dcs_install, saved_games, args.hook)
            if not args.elevated:
                save_installation_state(
                    Path(__file__).resolve().parents[1],
                    dcs_install,
                    saved_games,
                )
        elif args.command == "preflight":
            result = installation_preflight(dcs_install, saved_games, args.hook)
        elif args.command == "uninstall":
            if args.purge:
                local_root = os.environ.get("LOCALAPPDATA")
                result = purge_installation(
                    dcs_install,
                    saved_games,
                    Path(local_root) if local_root else None,
                )
            else:
                result = uninstall_hook(dcs_install, saved_games)
                if args.remove_state:
                    state_directory = saved_games.resolve() / STATE_DIRECTORY
                    active_target = dcs_install.resolve() / RELATIVE_PANEL
                    if active_target.is_file() and BEGIN_MARKER in active_target.read_bytes():
                        raise InstallError(
                            "DCS Radio Voice Control remains in the active DCS panel; "
                            "refusing to remove its integration state"
                        )
                    if state_directory.exists():
                        shutil.rmtree(state_directory)
                    result["removed_state"] = str(state_directory)
        else:
            result = installation_status(dcs_install, saved_games)
    except (InstallError, FileNotFoundError, PermissionError, ValueError) as exc:
        _emit_result(
            f"DCS Radio Voice Control: {exc}", getattr(args, "result_file", None), error=True
        )
        return 1
    _emit_result(
        json.dumps(result, indent=2, sort_keys=True),
        getattr(args, "result_file", None),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
