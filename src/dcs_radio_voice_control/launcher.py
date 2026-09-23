"""Safe launcher and lightweight DCS-aware automatic controller."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Callable, Iterator, Sequence

from .configuration_store import load_document
from .controller_state import get_state, set_state
from .installation_state import load_installation_state, save_installation_state
from .event_log import write_event
from .stt import PROJECT_ROOT


HOOK = PROJECT_ROOT / "dcs" / "DCSRadioVoiceControl.radio_hook.lua"
VOICE_COMMAND = [sys.executable, "-m", "dcs_radio_voice_control.voice_command_test"]
DCS_IMAGE_NAMES = {"dcs.exe", "dcs_server.exe"}
_last_state: tuple[str, str] | None = None


def _installer_api():
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    from tools import install

    return install


def resolve_installation() -> tuple[Path, Path]:
    install = _installer_api()
    try:
        state = load_installation_state()
    except OSError:
        state = {}
    try:
        dcs = Path(state["dcs_install"]).resolve()
        saved = Path(state["saved_games"]).resolve()
    except (KeyError, TypeError, ValueError):
        pass
    else:
        manifest = saved / install.STATE_DIRECTORY / install.MANIFEST_NAME
        if (dcs / install.RELATIVE_PANEL).is_file() and manifest.is_file():
            return dcs, saved

    saved_candidates = [
        Path.home() / "Saved Games" / name for name in ("DCS", "DCS.openbeta")
    ]
    recorded: list[tuple[Path, Path]] = []
    for saved in saved_candidates:
        manifest = saved / install.STATE_DIRECTORY / install.MANIFEST_NAME
        try:
            value = json.loads(manifest.read_text(encoding="utf-8"))
            dcs = Path(value["dcs_install"])
        except (FileNotFoundError, OSError, KeyError, TypeError, json.JSONDecodeError):
            continue
        if (dcs / install.RELATIVE_PANEL).is_file():
            recorded.append((dcs.resolve(), saved.resolve()))
    if len(recorded) == 1:
        dcs, saved = recorded[0]
        save_installation_state(PROJECT_ROOT, dcs, saved)
        return dcs, saved

    saved = install.discover_saved_games(None)
    dcs = install.discover_dcs_install(None)
    return dcs, saved


def preflight(dcs_install: Path, saved_games: Path) -> dict[str, object]:
    return _installer_api().installation_preflight(dcs_install, saved_games, HOOK)


def install_or_update(dcs_install: Path, saved_games: Path) -> int:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "tools" / "install.py"),
        "install",
        "--dcs-install",
        str(dcs_install),
        "--saved-games",
        str(saved_games),
        "--hook",
        str(HOOK),
    ]
    return subprocess.run(command, cwd=PROJECT_ROOT, check=False).returncode


def dcs_is_running() -> bool:
    if os.name != "nt":
        return False
    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return False
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        present = bool(kernel32.Process32FirstW(snapshot, ctypes.byref(entry)))
        while present:
            if entry.szExeFile.casefold() in DCS_IMAGE_NAMES:
                return True
            present = bool(kernel32.Process32NextW(snapshot, ctypes.byref(entry)))
        return False
    finally:
        kernel32.CloseHandle(snapshot)


@contextmanager
def single_instance() -> Iterator[bool]:
    if os.name != "nt":
        yield True
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(None, False, "Local\\DCSRadioVoiceControlController")
    acquired = bool(handle) and ctypes.get_last_error() != 183
    try:
        yield acquired
    finally:
        if handle:
            kernel32.CloseHandle(handle)


def _state(name: str, message: str = "") -> None:
    global _last_state
    if _last_state == (name, message):
        return
    _last_state = (name, message)
    try:
        set_state(name, message)
    except OSError:
        pass
    write_event("controller_state", state=name, message=message)
    if sys.stdout is not None:
        print(f"DCS Radio Voice Control: {name}{': ' + message if message else ''}", flush=True)


def _notify(title: str, message: str) -> None:
    if os.name == "nt":
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x40)


def automatic_enabled() -> bool:
    try:
        return bool(load_document()["startup"]["start_with_windows"])
    except (OSError, ValueError, KeyError):
        return False


def _prepare(dcs_running: bool) -> tuple[bool, bool]:
    """Return (ready, restart_required)."""
    try:
        dcs_install, saved_games = resolve_installation()
        result = preflight(dcs_install, saved_games)
    except (OSError, ValueError, RuntimeError) as exc:
        _state("Repair required", str(exc))
        return False, False
    state = result["state"]
    if state == "current":
        return True, False
    if state == "repair_required":
        _state("Repair required", str(result.get("detail", "Installation cannot be updated safely.")))
        return False, False
    _state("Updating", "Administrator permission is required to install the DCS hook.")
    if install_or_update(dcs_install, saved_games) != 0:
        _state("Repair required", "The DCS hook could not be installed or updated.")
        return False, False
    if dcs_running or dcs_is_running():
        message = "The hook was updated on disk. Close DCS completely and start it again."
        _state("Restart DCS", message)
        return False, True
    return True, False


def _stop_worker(worker: subprocess.Popen[bytes]) -> None:
    if worker.poll() is not None:
        return
    if os.name == "nt":
        # Terminate the exact worker process tree so whisper.cpp and any active
        # Piper child cannot remain resident after DCS exits.
        result = subprocess.run(
            ["taskkill.exe", "/PID", str(worker.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            worker.wait(timeout=5)
            return
    worker.terminate()
    try:
        worker.wait(timeout=5)
    except subprocess.TimeoutExpired:
        worker.kill()
        worker.wait(timeout=2)


def automatic_controller(
    *,
    process_probe: Callable[[], bool] = dcs_is_running,
    enabled_probe: Callable[[], bool] = automatic_enabled,
    poll_seconds: float = 2.0,
    stop_requested: Callable[[], bool] = lambda: False,
) -> int:
    if not enabled_probe():
        return 0
    ready, restart = _prepare(process_probe())
    if not ready and not restart:
        _notify("DCS Radio Voice Control repair required", "DCS Radio Voice Control could not verify its DCS hook. Run install.bat for details.")
        return 2
    if restart:
        _notify("Restart DCS", "DCS Radio Voice Control updated its DCS hook. Close DCS completely and start it again.")
    worker: subprocess.Popen[bytes] | None = None
    try:
        hook_stamp = HOOK.stat().st_mtime_ns
    except OSError:
        hook_stamp = None
    while True:
        if stop_requested():
            if worker is not None:
                _stop_worker(worker)
            _state("Not running", "Exited from the notification area.")
            return 0
        if not enabled_probe():
            if worker is not None:
                _stop_worker(worker)
            _state("Not running", "Automatic startup was disabled.")
            return 0
        running = process_probe()
        if restart:
            if not running:
                restart = False
                ready = True
                _state("Waiting for DCS")
            time.sleep(poll_seconds)
            continue
        if running and worker is None:
            ready, restart = _prepare(True)
            if restart:
                _notify(
                    "Restart DCS",
                    "DCS Radio Voice Control updated its DCS hook. Close DCS completely and start it again.",
                )
                continue
            if not ready:
                _notify(
                    "DCS Radio Voice Control repair required",
                    "DCS Radio Voice Control could not verify its DCS hook. Run install.bat for details.",
                )
                while process_probe():
                    time.sleep(poll_seconds)
                continue
            _state("Loading")
            worker = subprocess.Popen(VOICE_COMMAND, cwd=PROJECT_ROOT)
        elif not running and worker is not None:
            _stop_worker(worker)
            worker = None
            _state("Waiting for DCS")
        elif worker is not None and worker.poll() is not None:
            # Do not restart repeatedly inside one DCS session after a real fault.
            worker = None
            child_state = get_state().get("state")
            if child_state == "Restart DCS":
                restart = True
                _notify("Restart DCS", "DCS loaded an older DCS Radio Voice Control hook. Close DCS completely and start it again.")
                continue
            _state("Repair required", "Voice control stopped unexpectedly; restart DCS after checking the logs.")
            while process_probe():
                time.sleep(poll_seconds)
            _state("Waiting for DCS")
        elif not running:
            try:
                current_stamp = HOOK.stat().st_mtime_ns
            except OSError:
                current_stamp = None
            if current_stamp != hook_stamp:
                hook_stamp = current_stamp
                ready, restart = _prepare(False)
                if not ready and not restart:
                    _notify(
                        "DCS Radio Voice Control repair required",
                        "DCS Radio Voice Control could not verify its DCS hook. Run install.bat for details.",
                    )
            if ready:
                _state("Waiting for DCS")
        time.sleep(poll_seconds)


def manual_launch(voice_arguments: Sequence[str]) -> int:
    ready, restart = _prepare(dcs_is_running())
    if restart:
        print("Close DCS completely, start it again, then run DCS Radio Voice Control.", file=sys.stderr)
        return 3
    if not ready:
        return 2
    try:
        return subprocess.run(
            [*VOICE_COMMAND, *voice_arguments],
            cwd=PROJECT_ROOT,
            check=False,
        ).returncode
    except KeyboardInterrupt:
        # Windows delivers Ctrl+C to both the voice worker and this waiting
        # launcher.  The worker has already stopped cleanly; do not expose a
        # second traceback from the parent process.
        return 130


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--automatic", action="store_true", help="run the DCS watcher at Windows sign-in")
    parser.add_argument("--tray", action="store_true", help="run the DCS watcher in the notification area")
    args, voice_arguments = parser.parse_known_args(argv)
    with single_instance() as acquired:
        if not acquired:
            if sys.stdout is not None:
                print("DCS Radio Voice Control is already running.")
            return 0
        if args.automatic or args.tray:
            from .tray import run_tray

            return run_tray(automatic=args.automatic)
        return manual_launch(voice_arguments)


if __name__ == "__main__":
    raise SystemExit(main())
