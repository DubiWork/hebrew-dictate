"""
Hebrew Dictation — speak Hebrew, text gets typed into any focused app.

Run this in a separate terminal. Switch to any app (VS Code, browser, Claude Code, etc.)
and start speaking. After each pause, the Hebrew text is pasted at your cursor.

First run downloads the model (~150MB for 'base', ~500MB for 'small').
After that, works fully offline.

Usage:
    python hebrew-dictate.py                   # base model, paste mode
    python hebrew-dictate.py --model small     # better accuracy
    python hebrew-dictate.py --print-only      # just print, don't type

Controls:
    Speak normally — text appears in the focused app after each pause.
    Ctrl+C to stop.
"""

import argparse
import os
import sys
import time
import queue
import numpy as np
import sounddevice as sd
from pathlib import Path

# Add NVIDIA CUDA DLLs to search path (pip-installed nvidia packages)
for nvidia_dir in Path(sys.prefix, "Lib", "site-packages", "nvidia").glob("*/bin"):
    os.environ["PATH"] = str(nvidia_dir) + os.pathsep + os.environ.get("PATH", "")
import pyperclip
import pyautogui
import ctypes
from faster_whisper import WhisperModel

# ── Config ──────────────────────────────────────────────────────────────────
SAMPLE_RATE = 16000
SILENCE_THRESHOLD = 0.01      # RMS below this = silence
SILENCE_DURATION = 0.8        # seconds of silence before processing chunk
MIN_AUDIO_DURATION = 0.5      # ignore chunks shorter than this

# ── Args ────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Hebrew dictation — speak and type")
parser.add_argument("--model", default="ivrit-ai/whisper-large-v3-turbo-ct2",
                    help="Whisper model ID (default: ivrit-ai/whisper-large-v3-turbo-ct2)")
parser.add_argument("--device-id", type=int, default=None,
                    help="Audio input device ID (see --list-devices)")
parser.add_argument("--list-devices", action="store_true",
                    help="List available audio input devices and exit")
parser.add_argument("--print-only", action="store_true",
                    help="Only print transcription, don't type into apps")
args = parser.parse_args()

if args.list_devices:
    print(sd.query_devices())
    sys.exit(0)

# Disable pyautogui's fail-safe (moving mouse to corner won't crash it)
pyautogui.FAILSAFE = False
# Small pause between pyautogui actions
pyautogui.PAUSE = 0.0

# ── Load model ──────────────────────────────────────────────────────────────
print(f"Loading Whisper model '{args.model}'... (first run downloads it)")
model = WhisperModel(args.model, device="cuda", compute_type="int8")
print("Model loaded!\n")
print("=" * 55)
if args.print_only:
    print("  MODE: Print only (not typing into apps)")
else:
    print("  MODE: Dictation (typing into focused app)")
print("  Speak Hebrew. Text appears after each pause.")
print("  Ctrl+C to stop.")
print("=" * 55)
print()

# ── Audio capture ───────────────────────────────────────────────────────────
audio_queue = queue.Queue()
recording_buffer = []
silence_counter = 0
is_speaking = False


def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"  [audio: {status}]", file=sys.stderr)
    audio_queue.put(indata.copy())


def get_own_console_hwnd():
    """Get the window handle of our own console window."""
    return ctypes.windll.kernel32.GetConsoleWindow()

OWN_HWND = get_own_console_hwnd()


def get_foreground_hwnd():
    """Get the currently focused window handle."""
    return ctypes.windll.user32.GetForegroundWindow()


def type_text(text):
    """Paste text into the currently focused application via clipboard.
    Skips if the script's own terminal is focused — queues for next focus change."""
    fg = get_foreground_hwnd()
    if fg == OWN_HWND:
        # Our own terminal is focused — wait up to 5s for user to switch
        print(f"  [waiting for you to click on target app...]")
        deadline = time.time() + 5.0
        while time.time() < deadline:
            time.sleep(0.2)
            fg = get_foreground_hwnd()
            if fg != OWN_HWND:
                break
        else:
            print(f"  [skipped — still on script terminal. Click another app first.]")
            return

    # Save current clipboard
    try:
        old_clipboard = pyperclip.paste()
    except Exception:
        old_clipboard = ""

    # Copy transcribed text to clipboard and paste it
    try:
        pyperclip.copy(text)
        time.sleep(0.02)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.05)
    finally:
        try:
            pyperclip.copy(old_clipboard)
        except Exception:
            pass


def process_audio(audio_data):
    """Transcribe and type/print the result."""
    audio_np = np.concatenate(audio_data).flatten()
    duration = len(audio_np) / SAMPLE_RATE

    if duration < MIN_AUDIO_DURATION:
        return

    segments, info = model.transcribe(
        audio_np,
        language="he",
        beam_size=1,
        vad_filter=False,
    )

    text_parts = []
    for segment in segments:
        text_parts.append(segment.text.strip())

    text = " ".join(text_parts).strip()
    if not text:
        return

    if args.print_only:
        print(f"  >> {text}")
    else:
        print(f"  [typed] {text}")
        type_text(text + " ")


# ── Main loop ──────────────────────────────────────────────────────────────
try:
    block_duration = 0.1  # 100ms blocks
    block_size = int(SAMPLE_RATE * block_duration)

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        blocksize=block_size,
        device=args.device_id,
        callback=audio_callback,
    ):
        while True:
            data = audio_queue.get()
            rms = np.sqrt(np.mean(data ** 2))

            if rms > SILENCE_THRESHOLD:
                if not is_speaking:
                    is_speaking = True
                recording_buffer.append(data)
                silence_counter = 0
            else:
                if is_speaking:
                    recording_buffer.append(data)
                    silence_counter += block_duration

                    if silence_counter >= SILENCE_DURATION:
                        process_audio(recording_buffer)
                        recording_buffer = []
                        silence_counter = 0
                        is_speaking = False

except KeyboardInterrupt:
    print("\n\nDictation stopped.")
except Exception as e:
    print(f"\nError: {e}", file=sys.stderr)
    sys.exit(1)
