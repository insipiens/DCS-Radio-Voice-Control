"""Windows notification-area controller for DCS Radio Voice Control."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import threading
import webbrowser

from .configuration_store import load_document
from .controller_state import get_state
from .event_log import log_directory, recent_events, write_event
from .stt import PROJECT_ROOT

WM_APP = 0x8000
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
NIM_ADD = 0
NIM_DELETE = 2
NIF_MESSAGE = 1
NIF_ICON = 2
NIF_TIP = 4
IDI_APPLICATION = 32512
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
MF_STRING = 0
MF_SEPARATOR = 0x0800
SW_HIDE = 0
COMMAND_LOG = 1001
COMMAND_CONFIGURE = 1002
COMMAND_REPAIR = 1003
COMMAND_UPDATE = 1004
COMMAND_EXIT = 1005

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HANDLE),
        ("szTip", wintypes.WCHAR * 128),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HANDLE),
        ("hIcon", wintypes.HANDLE),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HANDLE),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class TrayApplication:
    def __init__(self, automatic: bool) -> None:
        self.automatic = automatic
        self.stop_event = threading.Event()
        self.hwnd: int | None = None
        self._window_proc = WNDPROC(self._wndproc)

    def run(self) -> int:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        user32.RegisterClassW.restype = wintypes.ATOM
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HANDLE, wintypes.LPVOID]
        user32.CreateWindowExW.restype = wintypes.HWND
        kernel32.GetModuleHandleW.restype = wintypes.HANDLE
        klass = WNDCLASSW()
        klass.hInstance = kernel32.GetModuleHandleW(None)
        klass.lpszClassName = "DCSRadioVoiceControlTray"
        klass.lpfnWndProc = self._window_proc
        user32.RegisterClassW(ctypes.byref(klass))
        self.hwnd = user32.CreateWindowExW(0, klass.lpszClassName, "DCS Radio Voice Control", 0, 0, 0, 0, 0, None, None, klass.hInstance, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self._add_icon()
        threading.Thread(target=self._controller, name="DCS watcher", daemon=True).start()
        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        return 0

    def _controller(self) -> None:
        from .launcher import automatic_controller, automatic_enabled

        result = automatic_controller(
            enabled_probe=automatic_enabled if self.automatic else lambda: True,
            stop_requested=self.stop_event.is_set,
        )
        if result and self.hwnd:
            ctypes.WinDLL("user32").PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    def _add_icon(self) -> None:
        user32 = ctypes.WinDLL("user32")
        shell32 = ctypes.WinDLL("shell32")
        user32.LoadIconW.restype = wintypes.HANDLE
        icon = user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(data)
        data.hWnd = self.hwnd
        data.uID = 1
        data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        data.uCallbackMessage = WM_APP + 1
        data.hIcon = icon
        data.szTip = "DCS Radio Voice Control"
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data))

    def _remove_icon(self) -> None:
        if not self.hwnd:
            return
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(data)
        data.hWnd = self.hwnd
        data.uID = 1
        ctypes.WinDLL("shell32").Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))

    def _show_status(self) -> None:
        state = get_state()
        try:
            ptt = load_document()["ptt"]
            binding = ptt.get("name") or ptt.get("button") or "Not configured"
        except (OSError, KeyError, TypeError, ValueError):
            binding = "Not configured"
        events = recent_events(1)
        latest = events[-1].get("summary", "No activity recorded.") if events else "No activity recorded."
        message = "{0}\n{1}\n\nPush to talk: {2}\nLatest activity: {3}".format(
            state.get("state", "Starting"), state.get("message", ""), binding, latest
        )
        ctypes.WinDLL("user32").MessageBoxW(self.hwnd, message, "DCS Radio Voice Control", 0x40)

    def _show_menu(self) -> None:
        user32 = ctypes.WinDLL("user32")
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING, COMMAND_LOG, "Open runtime log")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, COMMAND_CONFIGURE, "Configure")
        user32.AppendMenuW(menu, MF_STRING, COMMAND_REPAIR, "Repair")
        user32.AppendMenuW(menu, MF_STRING, COMMAND_UPDATE, "Download update")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, COMMAND_EXIT, "Exit")
        point = POINT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.SetForegroundWindow(self.hwnd)
        command = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD, point.x, point.y, 0, self.hwnd, None)
        user32.DestroyMenu(menu)
        if command:
            self._command(command)

    def _command(self, command: int) -> None:
        if command == COMMAND_LOG:
            write_event("runtime_log_opened")
            subprocess.Popen(["notepad.exe", str(log_directory() / "dcs_radio_voice_control.log")])
        elif command == COMMAND_CONFIGURE:
            subprocess.Popen(["cmd.exe", "/c", str(PROJECT_ROOT / "configuration.bat")], cwd=PROJECT_ROOT)
        elif command == COMMAND_REPAIR:
            self.stop_event.set()
            subprocess.Popen(["cmd.exe", "/c", str(PROJECT_ROOT / "repair.bat")], cwd=PROJECT_ROOT)
            ctypes.WinDLL("user32").DestroyWindow(self.hwnd)
        elif command == COMMAND_UPDATE:
            self.stop_event.set()
            webbrowser.open("https://github.com/insipiens/DCS-Radio-Voice-Control/releases")
            ctypes.WinDLL("user32").DestroyWindow(self.hwnd)
        elif command == COMMAND_EXIT:
            self.stop_event.set()
            ctypes.WinDLL("user32").DestroyWindow(self.hwnd)

    def _wndproc(self, hwnd: int, message: int, wparam: int, lparam: int) -> int:
        if message == WM_APP + 1:
            if lparam == WM_LBUTTONUP:
                self._show_status()
            elif lparam in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._show_menu()
            return 0
        if message == WM_COMMAND:
            self._command(wparam & 0xFFFF)
            return 0
        if message == WM_DESTROY:
            self.stop_event.set()
            self._remove_icon()
            ctypes.WinDLL("user32").PostQuitMessage(0)
            return 0
        return ctypes.WinDLL("user32").DefWindowProcW(hwnd, message, wparam, lparam)


def run_tray(*, automatic: bool) -> int:
    if __import__("os").name != "nt":
        return 0
    return TrayApplication(automatic).run()
