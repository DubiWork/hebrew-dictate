# hebrew-dictate

Local Hebrew speech-to-text dictation for Windows. Runs in the system tray, transcribes your speech, and pastes the Hebrew text into any focused app.

Uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper) with [ivrit-ai](https://huggingface.co/ivrit-ai) — the #1 Hebrew Whisper model (beats Amazon, OpenAI, and Google on Hebrew accuracy). GPU-accelerated with CUDA on NVIDIA GPUs, falls back to CPU automatically. Runs fully offline after first model download.

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/DubiWork/hebrew-dictate.git
cd hebrew-dictate
pip install -r requirements.txt

# 2. (Optional) For NVIDIA GPU acceleration (23x faster):
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 nvidia-cuda-nvrtc-cu12

# 3. Run it
pythonw hebrew-dictate.pyw
```

First run downloads the model (~800MB). After that it works fully offline.

## How to Use

1. **Double-tap Right Ctrl** — starts listening (tray icon turns green)
2. **Speak Hebrew** — text appears after each pause
3. **Press Enter** — stops listening

That's it. The text is pasted wherever your cursor is — VS Code, browser, Word, terminal, anywhere.

### Recovery

If the app gets stuck (no tray icon, not responding):

- **Right Shift + Right Ctrl** — force-kills and restarts the app

### Tray Icon Colors

| Color | Meaning |
|-------|---------|
| Gray | Ready (not listening) |
| Yellow (...) | Loading model |
| Green | Listening |
| Blue (number) | Processing speech chunks |
| Red (!!) | Error |

## Auto-Start on Boot

To have the hotkey available immediately after Windows starts:

```bash
# Run this once — creates a shortcut in Windows Startup
python -c "
import subprocess, sys, os
startup = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
script = os.path.abspath('hebrew-dictate-hotkey.pyw')
pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
ps = f\"\"\"$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('{startup}\\Hebrew Dictate Hotkey.lnk'); $s.TargetPath = '{pythonw}'; $s.Arguments = '{script}'; $s.WorkingDirectory = '{os.path.dirname(script)}'; $s.WindowStyle = 7; $s.Save()\"\"\"
subprocess.run(['powershell', '-Command', ps])
print('Done! Hotkey listener will start on next boot.')
"
```

This installs a lightweight listener (~5MB RAM) that launches the full app on demand when you double-tap Right Ctrl.

## Prerequisites

- Windows 10/11
- Python 3.10+ (tested with 3.12)
- A working microphone
- NVIDIA GPU with CUDA support (optional — auto-falls back to CPU)

## Terminal Mode

For debugging or if you prefer console output:

```bash
python hebrew-dictate.py                       # default model, paste mode
python hebrew-dictate.py --model small         # different model
python hebrew-dictate.py --print-only          # just print, don't type
python hebrew-dictate.py --list-devices        # show available microphones
```

## Benchmark

Compare Whisper models for Hebrew accuracy and speed:

```bash
python hebrew-benchmark.py                     # record 3 samples, test 5 models
python hebrew-benchmark.py --samples 1         # quick 1-sample test
python hebrew-benchmark.py --duration 10       # 10s per sample
python hebrew-benchmark.py --file test.wav     # use existing audio file
python hebrew-benchmark.py --models 0,1        # test specific models only
```

## Configuration

Edit the constants at the top of `hebrew-dictate.pyw`:

| Setting | Default | Description |
|---------|---------|-------------|
| `DOUBLE_TAP_KEY` | `right ctrl` | Key to double-tap to toggle listening |
| `DOUBLE_TAP_WINDOW` | `0.4` | Max seconds between taps |
| `SILENCE_THRESHOLD` | `0.01` | RMS threshold for silence detection |
| `SILENCE_DURATION` | `0.8` | Seconds of silence before a chunk is sent |
| `DEFAULT_MODEL` | `ivrit-ai/whisper-large-v3-turbo-ct2` | Whisper model ID |
| `DEFAULT_REVISION` | `2025.05.13` | Model revision (latest best) |

## Files

| File | Description |
|------|-------------|
| `hebrew-dictate.pyw` | Main tray app (recommended) |
| `hebrew-dictate.py` | Terminal version (for debugging) |
| `hebrew-dictate-hotkey.pyw` | Lightweight hotkey listener for auto-start |
| `hebrew-benchmark.py` | Multi-sample model comparison benchmark |
| `hebrew-dictate-launcher.vbs` | Silent launcher (legacy) |
| `test_hebrew_dictate.py` | Unit tests |

## Troubleshooting

**No tray icon?** Check the `^` overflow area in the system tray. Windows sometimes hides new icons there.

**Slow first transcription?** The model takes ~10s to load on first use. After that, each chunk transcribes in ~0.3s (GPU) or ~7s (CPU).

**Text not appearing?** Make sure you're focused on an app that accepts Ctrl+V paste. The app uses clipboard paste to type text.

**CUDA errors in log?** Install the NVIDIA packages: `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 nvidia-cuda-nvrtc-cu12`. Without them, the app falls back to CPU (slower but works).

## License

MIT
