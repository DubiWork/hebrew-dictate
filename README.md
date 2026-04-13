# hebrew-dictate

Local Hebrew speech-to-text dictation for Windows. Runs in the system tray, transcribes your speech, and pastes the Hebrew text into any focused app.

Uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper) with [ivrit-ai/whisper-large-v3-turbo-ct2](https://huggingface.co/ivrit-ai/whisper-large-v3-turbo-ct2) — a Hebrew fine-tuned Whisper model. Runs fully offline after the first model download (~800MB).

## How it works

1. Press **Ctrl+Alt+H** to start listening (tray icon turns green)
2. Speak in Hebrew — audio is chunked by silence detection
3. Press **Enter** to stop listening
4. Transcribed text is pasted at your cursor via clipboard

### Tray icon states

| Color | Meaning |
|-------|---------|
| Gray | Idle |
| Yellow | Loading model |
| Green | Listening |
| Blue + number | Processing chunks |
| Red | Error |

## Prerequisites

- Windows 10/11
- Python 3.10+
- A working microphone

## Install

```bash
git clone https://github.com/DubiWork/hebrew-dictate.git
cd hebrew-dictate
pip install -r requirements.txt
```

## Run

**Tray app (recommended)** — no terminal window:
```bash
pythonw hebrew-dictate.pyw
```

Or double-click `hebrew-dictate-launcher.vbs`.

**Terminal version** — for debugging, shows output in console:
```bash
python hebrew-dictate.py
```

The model downloads automatically on first run (~800MB). After that it works offline.

## Benchmark

Compare different Whisper models for Hebrew accuracy and speed:

```bash
python hebrew-benchmark.py                # record 10s, test all models
python hebrew-benchmark.py --duration 15  # record 15s
python hebrew-benchmark.py --file test.wav  # use existing audio file
```

## Configuration

Edit the constants at the top of `hebrew-dictate.pyw`:

| Setting | Default | Description |
|---------|---------|-------------|
| `HOTKEY` | `ctrl+alt+h` | Global hotkey to start listening |
| `SILENCE_THRESHOLD` | `0.01` | RMS threshold for silence detection |
| `SILENCE_DURATION` | `0.8` | Seconds of silence before a chunk is sent |
| `DEFAULT_MODEL` | `ivrit-ai/whisper-large-v3-turbo-ct2` | Whisper model ID |

## Files

| File | Description |
|------|-------------|
| `hebrew-dictate.pyw` | Main tray app |
| `hebrew-dictate.py` | Terminal version (simpler, for debugging) |
| `hebrew-benchmark.py` | Model comparison benchmark |
| `hebrew-dictate-launcher.vbs` | Silent launcher (no console window) |

## License

MIT
