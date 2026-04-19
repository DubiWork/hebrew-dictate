"""
Hebrew Dictation Launcher — lightweight always-on hotkey listener.
Add to Windows Startup folder to enable double-tap Right Ctrl app launch.

- Consumes ~5MB RAM (no model loaded)
- On double-tap Right Ctrl: launches hebrew-dictate.pyw if not already running
- On Shift+Right Ctrl: force-kills and restarts the app (recovery from broken state)
- If already running (double-tap): does nothing (the app handles the hotkey itself)

Setup:
    1. Create a shortcut to this file
    2. Press Win+R, type: shell:startup
    3. Move the shortcut into the Startup folder
    Or run: pythonw hebrew-dictate-hotkey.pyw
"""

import sys
import os
import time
import subprocess
import ctypes
import keyboard

# ── Config ──────────────────────────────────────────────────────────────────
DOUBLE_TAP_KEY = "right ctrl"
DOUBLE_TAP_WINDOW = 0.4  # seconds between taps
FORCE_RESTART_HOTKEY = "shift+right ctrl"

# Path to the main app
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_APP = os.path.join(SCRIPT_DIR, "hebrew-dictate.pyw")
PYTHONW = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
if not os.path.exists(PYTHONW):
    # Fallback: try same directory as current python
    PYTHONW = "pythonw.exe"

MUTEX_NAME = "HebrewDictateMutex"

# ── State ───────────────────────────────────────────────────────────────────
last_tap_time = 0


def is_app_running():
    """Check if the main app is running via its mutex."""
    ctypes.windll.kernel32.OpenMutexW.restype = ctypes.c_void_p
    handle = ctypes.windll.kernel32.OpenMutexW(0x00100000, False, MUTEX_NAME)  # SYNCHRONIZE
    if handle:
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(handle))
        return True
    return False


def kill_app():
    """Force-kill any running hebrew-dictate.pyw processes (but not this launcher)."""
    try:
        # Use PowerShell to find pythonw processes running the main app (not the hotkey launcher)
        ps_cmd = (
            "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | "
            "Where-Object { $_.CommandLine -like '*hebrew-dictate.pyw*' -and "
            "$_.CommandLine -notlike '*hebrew-dictate-hotkey*' } | "
            "Select-Object -ExpandProperty ProcessId"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line.isdigit():
                subprocess.run(["taskkill", "/F", "/PID", line],
                               capture_output=True, timeout=5)
    except Exception:
        pass


def launch_app():
    """Launch the main hebrew-dictate app."""
    try:
        subprocess.Popen(
            [PYTHONW, MAIN_APP],
            cwd=SCRIPT_DIR,
            creationflags=0x00000008,  # DETACHED_PROCESS
        )
    except Exception:
        pass


def on_double_tap(event):
    """Called on Right Ctrl key-up — detect double-tap to launch app."""
    global last_tap_time
    now = time.time()
    if now - last_tap_time < DOUBLE_TAP_WINDOW:
        last_tap_time = 0
        if not is_app_running():
            launch_app()
    else:
        last_tap_time = now


def on_force_restart():
    """Shift+Right Ctrl — force-kill and relaunch the app."""
    kill_app()
    time.sleep(0.5)  # wait for mutex to release
    launch_app()


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    # Single-instance for the launcher itself
    ctypes.windll.kernel32.CreateMutexW.restype = ctypes.c_void_p
    ctypes.windll.kernel32.CreateMutexW(None, False, "HebrewDictateLauncherMutex")
    if ctypes.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return

    keyboard.on_release_key(DOUBLE_TAP_KEY, on_double_tap, suppress=False)
    keyboard.add_hotkey(FORCE_RESTART_HOTKEY, on_force_restart, suppress=False)
    keyboard.wait()  # blocks forever


if __name__ == "__main__":
    main()
