"""
Hebrew Dictation Tray App
Runs in the system tray. Speak Hebrew, text gets typed into any focused app.
No console window needed — run with pythonw.exe or double-click the .pyw file.

Hotkey: Double-tap Right Ctrl — toggle listening on/off
Right-click tray icon for menu: Start/Stop listening, Quit.
"""

import sys
import os
import re
import time
import queue
import threading
import logging
import ctypes
from pathlib import Path
import numpy as np
import sounddevice as sd

# Add NVIDIA CUDA DLLs to search path (pip-installed nvidia packages)
for nvidia_dir in Path(sys.prefix, "Lib", "site-packages", "nvidia").glob("*/bin"):
    os.environ["PATH"] = str(nvidia_dir) + os.pathsep + os.environ.get("PATH", "")
import pyperclip
import pyautogui
from PIL import Image, ImageDraw, ImageFont
import pystray
import keyboard
from faster_whisper import WhisperModel

# ── Logging (essential — pythonw.exe has no console) ─────────────────────────
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hebrew-dictate.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
)
log = logging.getLogger("hebrew-dictate")

# ── Config ──────────────────────────────────────────────────────────────────
SAMPLE_RATE = 16000
SILENCE_THRESHOLD = 0.01
SILENCE_DURATION = 0.8
MIN_AUDIO_DURATION = 0.5

# Default model — benchmarked 2025-04-14, turbo@2025.05.13 is fastest+accurate
DEFAULT_MODEL = "ivrit-ai/whisper-large-v3-turbo-ct2"
DEFAULT_REVISION = "2025.05.13"

# Global hotkey — double-tap Right Ctrl to toggle listening on/off
DOUBLE_TAP_KEY = "right ctrl"
DOUBLE_TAP_WINDOW = 0.4  # seconds between taps

# ── State ───────────────────────────────────────────────────────────────────
class AppState:
    def __init__(self):
        self.listening = False
        self.model = None
        self.model_id = DEFAULT_MODEL
        self.model_revision = DEFAULT_REVISION
        self.tray_icon = None
        self.audio_queue = queue.Queue()
        self.transcribe_queue = queue.Queue()  # chunks waiting to be transcribed
        self.recording_buffer = []
        self.silence_counter = 0
        self.is_speaking = False
        self.stream = None
        self.listen_thread = None
        self.should_stop = threading.Event()
        self.loading_model = False
        self.transcription_count = 0
        self.chunks_pending = 0
        self.chunks_lock = threading.Lock()
        self.buffer_lock = threading.Lock()
        self.last_tap_time = 0
        self.enter_hook = None

state = AppState()

# ── Tray Icon Images ────────────────────────────────────────────────────────
def create_icon(color, text="He"):
    """Create a simple icon with text."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Circle background
    draw.ellipse([4, 4, 60, 60], fill=color, outline=(255, 255, 255, 200), width=2)
    # Text
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((64 - tw) / 2, (64 - th) / 2 - 2), text, fill=(255, 255, 255, 255), font=font)
    return img

ICON_IDLE = create_icon((100, 100, 100, 255))       # Gray — not listening
ICON_LISTENING = create_icon((0, 150, 0, 255))       # Green — listening
ICON_PROCESSING = create_icon((0, 100, 200, 255))    # Blue — transcribing
ICON_LOADING = create_icon((200, 150, 0, 255), "...")  # Yellow — loading model
ICON_ERROR = create_icon((200, 50, 50, 255), "!!")     # Red — error state

# Pre-generated count icons for pending chunk display (1-9)
COUNT_ICONS = {i: create_icon((0, 100, 200, 255), str(i)) for i in range(1, 10)}

def get_count_icon(n):
    """Return a cached count icon, or generate one for unexpected values."""
    return COUNT_ICONS.get(n, create_icon((0, 100, 200, 255), str(n)))

# ── Windows helpers ─────────────────────────────────────────────────────────
def get_foreground_hwnd():
    return ctypes.windll.user32.GetForegroundWindow()

OWN_HWND = 0  # .pyw has no console; focus-check in type_text is a no-op

# ── Audio & Transcription ──────────────────────────────────────────────────
def type_text(text):
    """Paste text into the currently focused application via clipboard."""
    fg = get_foreground_hwnd()
    if fg == OWN_HWND and OWN_HWND != 0:
        # Wait up to 3s for user to switch apps
        deadline = time.time() + 3.0
        while time.time() < deadline:
            time.sleep(0.2)
            fg = get_foreground_hwnd()
            if fg != OWN_HWND:
                break
        else:
            return

    try:
        old_clipboard = pyperclip.paste()
    except Exception:
        old_clipboard = ""
        log.debug("Could not read clipboard")

    try:
        pyperclip.copy(text)
        time.sleep(0.05)
        keyboard.send("ctrl+v")
        time.sleep(0.15)
    finally:
        try:
            pyperclip.copy(old_clipboard)
        except Exception:
            log.debug("Could not restore clipboard")


def transcribe_worker():
    """Single worker thread that processes chunks one at a time from the queue."""
    while True:
        audio_data = state.transcribe_queue.get()  # blocks until a chunk is available

        try:
            if state.model is None:
                with state.chunks_lock:
                    state.chunks_pending = max(0, state.chunks_pending - 1)
                    if state.chunks_pending == 0 and not state.listening:
                        update_icon(ICON_IDLE)
                continue

            audio_np = np.concatenate(audio_data).flatten()
            duration = len(audio_np) / SAMPLE_RATE
            if duration < MIN_AUDIO_DURATION:
                with state.chunks_lock:
                    state.chunks_pending = max(0, state.chunks_pending - 1)
                    if state.chunks_pending == 0 and not state.listening:
                        update_icon(ICON_IDLE)
                continue

            # Show remaining chunks count
            with state.chunks_lock:
                n = state.chunks_pending
            update_icon(get_count_icon(n))

            segments, info = state.model.transcribe(
                audio_np,
                language="he",
                beam_size=1,
                vad_filter=False,
                word_timestamps=True,
                initial_prompt="שלום, זוהי הקלטה בעברית. אני מדבר בעברית.",
            )

            text_parts = [seg.text.strip() for seg in segments]
            text = " ".join(text_parts).strip()

            log.info("Transcribed (%0.1fs audio): %s", duration, text[:100])

            # Add space after punctuation where missing (e.g. "שלום.מה" → "שלום. מה")
            text = re.sub(r'([.!?,;:])([^\s])', r'\1 \2', text)

            with state.chunks_lock:
                state.chunks_pending = max(0, state.chunks_pending - 1)
                remaining = state.chunks_pending

            # Filter out Whisper hallucinations (dots, punctuation-only, very short noise)
            # Also detect repetition loops (same phrase 3+ times)
            filtered = text.strip(" .…,!?-_\"'")
            check_text = filtered[:500]  # cap regex input to prevent ReDoS
            if not check_text or len(check_text) <= 1:
                log.info("Filtered (too short): '%s'", text[:50])
                pass  # skip entirely
            elif re.search(r'(.{3,}?)\1{2,}', check_text):
                log.info("Filtered (repetition): '%s'", text[:50])
                pass  # repetition loop hallucination
            else:
                state.transcription_count += 1
                log.info("Typing: %s", text[:100])
                type_text(text + " ")

            # Update icon
            if remaining > 0:
                update_icon(get_count_icon(remaining))
            elif state.listening:
                update_icon(ICON_LISTENING)
            else:
                update_icon(ICON_IDLE)

        except Exception as e:
            log.error("transcribe_worker error (continuing): %s", e, exc_info=True)
            with state.chunks_lock:
                state.chunks_pending = max(0, state.chunks_pending - 1)
                remaining = state.chunks_pending
            if remaining > 0:
                update_icon(get_count_icon(remaining))
            elif state.listening:
                update_icon(ICON_LISTENING)
            else:
                update_icon(ICON_IDLE)


def enqueue_chunk(audio_data):
    """Add a chunk to the transcription queue."""
    with state.chunks_lock:
        state.chunks_pending += 1
    state.transcribe_queue.put(audio_data)


def audio_callback(indata, frames, time_info, status):
    if state.listening:
        state.audio_queue.put(indata.copy())


def listen_loop():
    """Main listening loop — runs in a background thread."""
    block_duration = 0.1
    block_size = int(SAMPLE_RATE * block_duration)

    try:
        state.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=block_size,
            callback=audio_callback,
        )
        state.stream.start()

        while not state.should_stop.is_set():
            try:
                data = state.audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if not state.listening:
                continue

            rms = np.sqrt(np.mean(data ** 2))

            if rms > SILENCE_THRESHOLD:
                if not state.is_speaking:
                    state.is_speaking = True
                with state.buffer_lock:
                    state.recording_buffer.append(data)
                state.silence_counter = 0
            else:
                if state.is_speaking:
                    with state.buffer_lock:
                        state.recording_buffer.append(data)
                    state.silence_counter += block_duration

                    if state.silence_counter >= SILENCE_DURATION:
                        with state.buffer_lock:
                            buf = state.recording_buffer[:]
                            state.recording_buffer = []
                        state.silence_counter = 0
                        state.is_speaking = False
                        enqueue_chunk(buf)

    except Exception as e:
        log.error("listen_loop crashed: %s", e, exc_info=True)
        update_icon(ICON_ERROR)
        state.listening = False
    finally:
        if state.stream:
            state.stream.stop()
            state.stream.close()


# ── Model loading ──────────────────────────────────────────────────────────
def load_model():
    """Load the Whisper model in a background thread."""
    state.loading_model = True
    update_icon(ICON_LOADING)
    update_menu()
    log.info("Loading model: %s (revision=%s)", state.model_id, state.model_revision)

    try:
        state.model = WhisperModel(state.model_id, device="cuda", compute_type="int8",
                                   revision=state.model_revision)
        log.info("Model loaded successfully")
    except Exception as e:
        log.error("Failed to load model: %s", e, exc_info=True)
        state.model = None
        update_icon(ICON_ERROR)

    state.loading_model = False
    update_menu()


# ── Tray menu actions ──────────────────────────────────────────────────────
def update_icon(icon_img):
    if state.tray_icon:
        state.tray_icon.icon = icon_img

def update_menu():
    if state.tray_icon:
        state.tray_icon.menu = build_menu()

def start_listening():
    """Start listening — called from double-tap Right Ctrl."""
    if state.loading_model or state.listening:
        return

    # Start listen thread if not running (so it is ready when model finishes)
    if state.listen_thread is None or not state.listen_thread.is_alive():
        state.should_stop.clear()
        state.listen_thread = threading.Thread(target=listen_loop, daemon=True)
        state.listen_thread.start()

    if state.model is None:
        # Model not loaded yet — load it, then enable listening
        def load_and_enable():
            load_model()
            if state.model is not None:
                state.listening = True
                if state.enter_hook is None:
                    state.enter_hook = keyboard.on_press_key("enter", lambda e: stop_listening(), suppress=False)
                update_icon(ICON_LISTENING)
                log.info("Listening started (after model load)")
            else:
                log.warning("Model failed to load — cannot start listening")
            update_menu()
        threading.Thread(target=load_and_enable, daemon=True).start()
    else:
        # Model already loaded — enable immediately
        state.listening = True
        if state.enter_hook is None:
            state.enter_hook = keyboard.on_press_key("enter", lambda e: stop_listening(), suppress=False)
        update_icon(ICON_LISTENING)
        log.info("Listening started")
    update_menu()


def stop_listening():
    """Stop listening and transcribe — called from double-tap Right Ctrl."""
    if not state.listening:
        return

    state.listening = False
    log.info("Listening stopped")
    state.silence_counter = 0
    state.is_speaking = False

    # Unhook Enter key
    if state.enter_hook is not None:
        keyboard.unhook(state.enter_hook)
        state.enter_hook = None

    # Drain any remaining audio from the queue into the buffer
    while not state.audio_queue.empty():
        try:
            data = state.audio_queue.get_nowait()
            state.recording_buffer.append(data)
        except queue.Empty:
            break

    # Transcribe whatever we have buffered
    with state.buffer_lock:
        buf = state.recording_buffer[:]
        state.recording_buffer = []
    if buf:
        enqueue_chunk(buf)
    elif state.chunks_pending == 0:
        update_icon(ICON_IDLE)

    update_menu()


def toggle_listening():
    """Toggle listening on/off — called from tray menu."""
    if state.loading_model:
        return

    if state.listening:
        stop_listening()
    else:
        start_listening()


def on_toggle_listening(icon, item):
    toggle_listening()


def on_double_tap(event):
    """Called on Right Ctrl key-up — detect double-tap to toggle listening."""
    now = time.time()
    if now - state.last_tap_time < DOUBLE_TAP_WINDOW:
        state.last_tap_time = 0  # reset to avoid triple-tap re-trigger
        toggle_listening()
    else:
        state.last_tap_time = now


def on_quit(icon, item):
    log.info("Quit requested — shutting down")
    state.listening = False
    state.should_stop.set()
    icon.stop()


def build_menu():
    if state.loading_model:
        toggle_label = "Loading model..."
    elif state.listening:
        toggle_label = "Stop Listening"
    else:
        toggle_label = "Start Listening"

    status = f"Model: {state.model_id.split('/')[-1]}"
    count = f"Transcriptions: {state.transcription_count}"

    return pystray.Menu(
        pystray.MenuItem(toggle_label, on_toggle_listening, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Toggle: double-tap Right Ctrl", None, enabled=False),
        pystray.MenuItem(status, None, enabled=False),
        pystray.MenuItem(count, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    # Single-instance lock via Windows mutex
    ctypes.windll.kernel32.CreateMutexW.restype = ctypes.c_void_p
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "HebrewDictateMutex")
    if ctypes.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        log.info("Another instance is already running — exiting")
        return

    log.info("Hebrew Dictation starting up")
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.0

    # Register double-tap Right Ctrl to toggle listening
    keyboard.on_release_key(DOUBLE_TAP_KEY, on_double_tap, suppress=False)

    state.tray_icon = pystray.Icon(
        name="hebrew-dictate",
        icon=ICON_LOADING,
        title="Hebrew Dictation — loading model...",
        menu=build_menu(),
    )

    # Start background threads before icon.run() — they'll update the icon once it's visible
    def auto_load():
        load_model()
        if state.model is not None and not state.listening:
            update_icon(ICON_IDLE)
            state.tray_icon.title = "Hebrew Dictation (double-tap Right Ctrl)"
    threading.Thread(target=auto_load, daemon=True).start()
    threading.Thread(target=transcribe_worker, daemon=True).start()

    state.tray_icon.run()

    # Cleanup hotkey on exit
    keyboard.unhook_all()


if __name__ == "__main__":
    main()
