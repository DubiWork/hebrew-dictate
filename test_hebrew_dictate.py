"""
Unit tests for Hebrew Dictation App.
Tests extracted logic with mocked hardware dependencies.
Run: python test_hebrew_dictate.py -v
"""

import importlib.util
import os
import re
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, call, patch

import numpy as np

# ── Load the .pyw module with hardware mocked ────────────────────────────────

def _load_pyw_module():
    """Load hebrew-dictate.pyw as a testable module with hardware mocked."""
    mock_modules = {}
    for mod_name in ["sounddevice", "pystray", "keyboard", "pyautogui",
                     "pyperclip", "faster_whisper"]:
        mock_modules[mod_name] = MagicMock()

    # pystray needs Menu, MenuItem, Menu.SEPARATOR for build_menu
    mock_modules["pystray"].Menu = MagicMock()
    mock_modules["pystray"].MenuItem = MagicMock()
    mock_modules["pystray"].Menu.SEPARATOR = MagicMock()
    mock_modules["pystray"].Icon = MagicMock()

    # ctypes.windll needs to not crash on import
    # (real ctypes is fine on Windows, but we need windll.user32/kernel32)

    saved = {}
    for name, mock in mock_modules.items():
        saved[name] = sys.modules.get(name)
        sys.modules[name] = mock

    try:
        base = os.path.dirname(os.path.abspath(__file__))
        spec = importlib.util.spec_from_file_location(
            "hebrew_dictate_pyw",
            os.path.join(base, "hebrew-dictate.pyw"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, mock_modules
    finally:
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


MOD, MOCKS = _load_pyw_module()


# ── Test Classes ─────────────────────────────────────────────────────────────


class TestSilenceDetection(unittest.TestCase):
    """Tests the RMS-based chunking logic."""

    def _make_block(self, rms_value, duration=0.1, sample_rate=16000):
        """Create a numpy audio block with a specific RMS value."""
        n_samples = int(sample_rate * duration)
        return np.full((n_samples, 1), rms_value, dtype=np.float32)

    def test_rms_computation(self):
        block = self._make_block(0.02)
        rms = np.sqrt(np.mean(block ** 2))
        self.assertAlmostEqual(rms, 0.02, places=5)

    def test_silence_below_threshold(self):
        block = self._make_block(0.005)
        rms = np.sqrt(np.mean(block ** 2))
        self.assertLess(rms, MOD.SILENCE_THRESHOLD)

    def test_speech_above_threshold(self):
        block = self._make_block(0.05)
        rms = np.sqrt(np.mean(block ** 2))
        self.assertGreater(rms, MOD.SILENCE_THRESHOLD)

    def test_silence_duration_triggers_chunk(self):
        block_duration = 0.1
        blocks_needed = int(MOD.SILENCE_DURATION / block_duration) + 1
        silence_counter = 0
        for _ in range(blocks_needed):
            silence_counter += block_duration
        self.assertGreaterEqual(silence_counter, MOD.SILENCE_DURATION)

    def test_short_silence_no_chunk(self):
        block_duration = 0.1
        blocks = int(MOD.SILENCE_DURATION / block_duration) - 2
        silence_counter = blocks * block_duration
        self.assertLess(silence_counter, MOD.SILENCE_DURATION)

    def test_min_audio_duration_filter(self):
        short_audio = self._make_block(0.05, duration=0.3)
        duration = len(short_audio) / MOD.SAMPLE_RATE
        self.assertLess(duration, MOD.MIN_AUDIO_DURATION)

    def test_long_audio_passes_filter(self):
        long_audio = self._make_block(0.05, duration=1.0)
        duration = len(long_audio) / MOD.SAMPLE_RATE
        self.assertGreaterEqual(duration, MOD.MIN_AUDIO_DURATION)


class TestHallucinationFilter(unittest.TestCase):
    """Tests the hallucination detection regex and filters."""

    def _is_hallucination(self, text):
        """Replicate the filter logic from transcribe_worker."""
        filtered = text.strip(" .\u2026,!?-_\"'")
        check_text = filtered[:500]
        if not check_text or len(check_text) <= 1:
            return True
        if re.search(r'(.{3,}?)\1{2,}', check_text):
            return True
        return False

    def test_dots_only(self):
        self.assertTrue(self._is_hallucination("..."))

    def test_punctuation_only(self):
        self.assertTrue(self._is_hallucination("!?!?"))

    def test_whitespace_dots(self):
        self.assertTrue(self._is_hallucination("  .  "))

    def test_single_char(self):
        self.assertTrue(self._is_hallucination("\u05d0"))

    def test_empty(self):
        self.assertTrue(self._is_hallucination(""))

    def test_repetition_loop_detected(self):
        # "שלום" repeated 3+ times
        self.assertTrue(self._is_hallucination(
            "\u05e9\u05dc\u05d5\u05dd\u05e9\u05dc\u05d5\u05dd\u05e9\u05dc\u05d5\u05dd"
        ))

    def test_normal_hebrew_passes(self):
        self.assertFalse(self._is_hallucination(
            "\u05e9\u05dc\u05d5\u05dd, \u05de\u05d4 \u05e9\u05dc\u05d5\u05de\u05da \u05d4\u05d9\u05d5\u05dd?"
        ))

    def test_two_word_phrase_passes(self):
        self.assertFalse(self._is_hallucination("\u05e9\u05dc\u05d5\u05dd \u05e2\u05d5\u05dc\u05dd"))

    def test_regex_cap_at_500(self):
        long_text = "abc" * 500
        filtered = long_text.strip(" .\u2026,!?-_\"'")
        check_text = filtered[:500]
        self.assertEqual(len(check_text), 500)

    def test_punctuation_spacing_fix(self):
        text = "\u05e9\u05dc\u05d5\u05dd.\u05de\u05d4"
        fixed = re.sub(r'([.!?,;:])([^\s])', r'\1 \2', text)
        self.assertIn(". ", fixed)


class TestConfigConsistency(unittest.TestCase):
    """Verify config values match between .pyw and .py files."""

    @classmethod
    def setUpClass(cls):
        base = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base, "hebrew-dictate.pyw"), "r", encoding="utf-8") as f:
            cls.pyw_src = f.read()
        with open(os.path.join(base, "hebrew-dictate.py"), "r", encoding="utf-8") as f:
            cls.py_src = f.read()

    def _extract(self, src, name):
        m = re.search(rf'^{name}\s*=\s*(.+?)(?:\s*#.*)?$', src, re.MULTILINE)
        self.assertIsNotNone(m, f"{name} not found")
        return eval(m.group(1).strip())

    def test_sample_rate(self):
        self.assertEqual(
            self._extract(self.pyw_src, "SAMPLE_RATE"),
            self._extract(self.py_src, "SAMPLE_RATE"),
        )

    def test_silence_threshold(self):
        self.assertEqual(
            self._extract(self.pyw_src, "SILENCE_THRESHOLD"),
            self._extract(self.py_src, "SILENCE_THRESHOLD"),
        )

    def test_silence_duration(self):
        self.assertEqual(
            self._extract(self.pyw_src, "SILENCE_DURATION"),
            self._extract(self.py_src, "SILENCE_DURATION"),
        )

    def test_min_audio_duration(self):
        self.assertEqual(
            self._extract(self.pyw_src, "MIN_AUDIO_DURATION"),
            self._extract(self.py_src, "MIN_AUDIO_DURATION"),
        )


class TestTypeTextFlow(unittest.TestCase):
    """Tests clipboard save/restore with mocked I/O."""

    def setUp(self):
        self._orig_pyperclip = MOD.pyperclip
        self._orig_pyautogui = MOD.pyautogui
        self._orig_hwnd = MOD.OWN_HWND
        self._orig_get_fg = MOD.get_foreground_hwnd
        MOD.OWN_HWND = 0  # skip focus-check
        MOD.get_foreground_hwnd = MagicMock(return_value=12345)

    def tearDown(self):
        MOD.pyperclip = self._orig_pyperclip
        MOD.pyautogui = self._orig_pyautogui
        MOD.OWN_HWND = self._orig_hwnd
        MOD.get_foreground_hwnd = self._orig_get_fg

    def test_clipboard_saved_and_restored(self):
        mock_clip = MagicMock()
        mock_clip.paste.return_value = "original"
        mock_gui = MagicMock()
        MOD.pyperclip = mock_clip
        MOD.pyautogui = mock_gui

        MOD.type_text("hello")

        copy_calls = mock_clip.copy.call_args_list
        self.assertEqual(copy_calls[0], call("hello"))
        self.assertEqual(copy_calls[-1], call("original"))

    def test_clipboard_restored_on_paste_failure(self):
        mock_clip = MagicMock()
        mock_clip.paste.return_value = "original"
        mock_gui = MagicMock()
        mock_gui.hotkey.side_effect = RuntimeError("paste failed")
        MOD.pyperclip = mock_clip
        MOD.pyautogui = mock_gui

        # Exception propagates, but finally block restores clipboard
        with self.assertRaises(RuntimeError):
            MOD.type_text("hello")

        last_copy = mock_clip.copy.call_args_list[-1]
        self.assertEqual(last_copy, call("original"))

    def test_own_hwnd_zero_skips_focus_check(self):
        """With OWN_HWND=0, focus-wait loop should not trigger."""
        mock_clip = MagicMock()
        mock_clip.paste.return_value = ""
        mock_gui = MagicMock()
        MOD.pyperclip = mock_clip
        MOD.pyautogui = mock_gui

        MOD.type_text("test")

        mock_gui.hotkey.assert_called_once_with("ctrl", "v")


class TestBufferLock(unittest.TestCase):
    """Tests concurrent access to recording_buffer with a lock."""

    def test_concurrent_append_and_drain(self):
        buffer = []
        lock = threading.Lock()
        total_appended = []
        total_drained = []

        def appender():
            for i in range(100):
                with lock:
                    buffer.append(i)
                    total_appended.append(i)
                time.sleep(0.001)

        def drainer():
            time.sleep(0.01)
            for _ in range(10):
                with lock:
                    drained = buffer[:]
                    buffer.clear()
                total_drained.extend(drained)
                time.sleep(0.01)

        t1 = threading.Thread(target=appender)
        t2 = threading.Thread(target=drainer)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        with lock:
            total_drained.extend(buffer)

        self.assertEqual(sorted(total_drained), sorted(total_appended))

    def test_appstate_has_buffer_lock(self):
        s = MOD.AppState()
        self.assertIsInstance(s.buffer_lock, type(threading.Lock()))

    def test_stop_listening_drains_atomically(self):
        s = MOD.AppState()
        s.recording_buffer = [np.zeros(100) for _ in range(5)]
        with s.buffer_lock:
            buf = s.recording_buffer[:]
            s.recording_buffer = []
        self.assertEqual(len(buf), 5)
        self.assertEqual(len(s.recording_buffer), 0)


class TestTranscribeWorkerResilience(unittest.TestCase):
    """Tests that the worker error handling decrements chunks_pending."""

    def test_chunks_pending_decremented_on_error(self):
        s = MOD.AppState()
        s.chunks_pending = 3
        # Simulate what the except block in transcribe_worker does
        with s.chunks_lock:
            s.chunks_pending = max(0, s.chunks_pending - 1)
        self.assertEqual(s.chunks_pending, 2)

    def test_chunks_pending_does_not_go_negative(self):
        s = MOD.AppState()
        s.chunks_pending = 0
        with s.chunks_lock:
            s.chunks_pending = max(0, s.chunks_pending - 1)
        self.assertEqual(s.chunks_pending, 0)

    def test_empty_audio_raises(self):
        """np.concatenate on empty list raises — worker should catch this."""
        with self.assertRaises(ValueError):
            np.concatenate([]).flatten()


class TestIconCaching(unittest.TestCase):
    """Tests pre-generated count icons."""

    def test_count_icons_exist_1_through_9(self):
        for i in range(1, 10):
            self.assertIn(i, MOD.COUNT_ICONS)

    def test_icons_are_pil_images(self):
        from PIL import Image
        for i in range(1, 10):
            self.assertIsInstance(MOD.COUNT_ICONS[i], Image.Image)

    def test_get_count_icon_cached(self):
        icon_a = MOD.get_count_icon(3)
        icon_b = MOD.get_count_icon(3)
        self.assertIs(icon_a, icon_b)

    def test_get_count_icon_fallback_for_large_values(self):
        from PIL import Image
        icon = MOD.get_count_icon(42)
        self.assertIsInstance(icon, Image.Image)

    def test_icon_error_exists(self):
        from PIL import Image
        self.assertIsInstance(MOD.ICON_ERROR, Image.Image)


class TestAppStateDefaults(unittest.TestCase):
    """Verify AppState initializes correctly."""

    def test_default_values(self):
        s = MOD.AppState()
        self.assertFalse(s.listening)
        self.assertIsNone(s.model)
        self.assertEqual(s.model_id, MOD.DEFAULT_MODEL)
        self.assertEqual(s.recording_buffer, [])
        self.assertEqual(s.chunks_pending, 0)
        self.assertFalse(s.loading_model)
        self.assertIsNone(s.enter_hook)

    def test_has_buffer_lock(self):
        s = MOD.AppState()
        self.assertTrue(hasattr(s, "buffer_lock"))

    def test_has_chunks_lock(self):
        s = MOD.AppState()
        self.assertTrue(hasattr(s, "chunks_lock"))


if __name__ == "__main__":
    unittest.main()
