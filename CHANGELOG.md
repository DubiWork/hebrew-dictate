# Changelog

## [0.3.0] - 2026-04-15

### Added
- Lightweight hotkey launcher (`hebrew-dictate-hotkey.pyw`) for Windows Startup — ~5MB RAM always-on listener
- Auto-start setup instructions in README
- Auto-detect GPU/CPU — falls back to CPU if CUDA is not available (no crash)
- Tray icon watchdog — re-applies icon every 30s to prevent Windows from hiding it
- Transcription debug logging (transcribed text, typing, filtering)
- Troubleshooting section in README

### Changed
- Paste method switched from `pyautogui` to `keyboard.send` (fixes terminals)
- README rewritten with clear Quick Start, auto-start setup, and troubleshooting
- Post-paste delay increased for reliable clipboard restore

### Fixed
- Text not pasting in terminals (`keyboard.send("ctrl+v")` works at OS level)
- Tray icon disappearing after long idle or sleep/wake

## [0.2.0] - 2026-04-14

### Added
- GPU acceleration with CUDA (23x speedup on NVIDIA GPUs)
- NVIDIA DLL auto-discovery for pip-installed CUDA packages
- Double-tap Right Ctrl hotkey (replaces Ctrl+Alt+H, no admin needed)
- Enter key stops listening (hooks/unhooks dynamically per session)
- Single-instance mutex prevents duplicate launches
- Loading icon (yellow "...") shown during model startup
- `word_timestamps` and Hebrew `initial_prompt` for better transcription accuracy
- Audio queue drain on stop to prevent missing last word
- Model revision support (`revision='2025.05.13'` — 3x faster transcription)
- Multi-sample benchmark with 5 model configurations
- Unit test suite (38 tests)

### Changed
- Default model revision set to `2025.05.13` (0.31s vs 0.93s per chunk)
- Benchmark rewritten: records multiple samples, tests CPU/GPU/revision variants
- VBS launcher fixed to use `C:\Python312\pythonw.exe`

### Fixed
- Tray icon not appearing (removed incompatible `setup=` callback)
- Mutex detection using correct `ctypes.GetLastError()`
- Hebrew console encoding in benchmark (`sys.stdout.reconfigure`)
- Sentences gluing together (added space-after-punctuation post-processing)

## [0.1.0] - 2026-04-13

### Added
- Initial release: Hebrew speech-to-text dictation for Windows
- System tray app with pystray
- Terminal version for debugging
- Whisper model benchmark tool
- Silence-based audio chunking
- Clipboard-based text pasting
- Hallucination filtering (repetition loops, punctuation-only output)
