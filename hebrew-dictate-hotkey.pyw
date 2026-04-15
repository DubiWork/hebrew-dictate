"""
Hebrew Dictation Launcher — lightweight always-on hotkey listener.
Add to Windows Startup folder to enable double-tap Right Ctrl app launch.

- Consumes ~5MB RAM (no model loaded)
- On double-tap Right Ctrl: launches hebrew-dictate.pyw if not already running
- If already running: does nothing (the app handles the hotkey itself)

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
        last_tap_time = 0  # reset to avoid triple-tap
        if not is_app_running():
            launch_app()
    else:
        last_tap_time = now


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    # Single-instance for the launcher itself
    ctypes.windll.kernel32.CreateMutexW.restype = ctypes.c_void_p
    ctypes.windll.kernel32.CreateMutexW(None, False, "HebrewDictateLauncherMutex")
    if ctypes.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return

    keyboard.on_release_key(DOUBLE_TAP_KEY, on_double_tap, suppress=False)
    keyboard.wait()  # blocks forever


if __name__ == "__main__":
    main()
