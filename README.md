# hebrew-dictate

Local Hebrew speech-to-text dictation for Windows. Runs in the system tray, transcribes your speech, and pastes the Hebrew text into any focused app.

Uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper) with [ivrit-ai/whisper-large-v3-turbo-ct2](https://huggingface.co/ivrit-ai/whisper-large-v3-turbo-ct2) — a Hebrew fine-tuned Whisper model. GPU-accelerated with CUDA on NVIDIA GPUs. Runs fully offline after the first model download (~800MB).

## How it works

1. Double-tap **Right Ctrl** to start listening (tray icon turns green)
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
- Python 3.10+ (tested with 3.12)
- A working microphone
- NVIDIA GPU with CUDA support (recommended — 23x speedup over CPU)

## Install

```bash
git clone https://github.com/DubiWork/hebrew-dictate.git
cd hebrew-dictate
pip install -r requirements.txt
```

For GPU acceleration, also install NVIDIA CUDA runtime packages:
```bash
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 nvidia-cuda-nvrtc-cu12
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
python hebrew-benchmark.py                   # record 3 samples, test 5 models
python hebrew-benchmark.py --samples 1       # quick test with 1 sample
python hebrew-benchmark.py --duration 10     # 10s per sample
python hebrew-benchmark.py --file test.wav   # use existing audio file
python hebrew-benchmark.py --models 0,1      # test only specific models
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
| `hebrew-dictate.pyw` | Main tray app |
| `hebrew-dictate.py` | Terminal version (simpler, for debugging) |
| `hebrew-benchmark.py` | Multi-sample model comparison benchmark |
| `hebrew-dictate-launcher.vbs` | Silent launcher (no console window) |
| `test_hebrew_dictate.py` | Unit tests |

## License

MIT
