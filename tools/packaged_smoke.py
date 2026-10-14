"""Verify the one-file Windows app from an empty working directory."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def main():
    if sys.platform != "win32":
        raise SystemExit("This smoke test requires Windows")
    exe = Path(sys.argv[1]).resolve(strict=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    def find_window():
        found = []
        @callback_type
        def visit(hwnd, _):
            title = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title, len(title))
            if not (title.value.startswith("AD-HOST ") and "采集与波形" in title.value):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            handle = kernel32.OpenProcess(0x1000, False, pid.value)
            if handle:
                try:
                    path = ctypes.create_unicode_buffer(32768)
                    size = wintypes.DWORD(len(path))
                    if kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)) and Path(path.value).resolve() == exe:
                        found.append(hwnd)
                finally:
                    kernel32.CloseHandle(handle)
            return True
        user32.EnumWindows(visit, 0)
        return found[0] if found else None

    with tempfile.TemporaryDirectory(prefix="ad-host-startup-") as directory:
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        process = subprocess.Popen([str(exe)], cwd=directory, startupinfo=startup)
        try:
            deadline = time.monotonic() + 90
            hwnd = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Packaged app exited during startup: {process.returncode}")
                hwnd = find_window()
                if hwnd:
                    break
                time.sleep(.1)
            if not hwnd:
                raise RuntimeError("Main window did not appear")
            if not any(user32.SendMessageW(hwnd, 0x007F, size, 0) for size in (2, 0, 1)):
                raise RuntimeError("Main window has no icon")
            user32.PostMessageW(hwnd, 0x0010, 0, 0)
            if process.wait(timeout=30) != 0:
                raise RuntimeError(f"Packaged app failed on exit: {process.returncode}")
            print("PASS: single EXE starts from empty cwd, creates main window with icon, and exits cleanly")
        finally:
            if process.poll() is None:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
                process.wait(timeout=15)


if __name__ == "__main__":
    main()
