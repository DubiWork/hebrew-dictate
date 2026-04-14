"""
Hebrew Whisper Model Benchmark
Records a sample from your microphone, then tests it against multiple models.
Compares: accuracy (you judge), transcription speed, and model load time.

Usage:
    python hebrew-benchmark.py                # record 10s, test all models
    python hebrew-benchmark.py --duration 15  # record 15s
    python hebrew-benchmark.py --file test.wav  # use existing audio file
"""

import argparse
import os
import sys
import time
import numpy as np
import sounddevice as sd

# Fix Hebrew output on Windows console
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

# Add NVIDIA CUDA DLLs to search path (pip-installed nvidia packages)
for nvidia_dir in Path(sys.prefix, "Lib", "site-packages", "nvidia").glob("*/bin"):
    os.environ["PATH"] = str(nvidia_dir) + os.pathsep + os.environ.get("PATH", "")

SAMPLE_RATE = 16000

# Models to benchmark — order: fastest/smallest first
MODELS = [
    {"id": "ivrit-ai/whisper-large-v3-turbo-ct2",     "label": "turbo CPU",         "type": "hebrew", "device": "cpu",  "compute": "int8"},
    {"id": "ivrit-ai/whisper-large-v3-turbo-ct2",     "label": "turbo GPU fp16",    "type": "hebrew", "device": "cuda", "compute": "float16"},
    {"id": "ivrit-ai/whisper-large-v3-turbo-ct2",     "label": "turbo GPU int8",    "type": "hebrew", "device": "cuda", "compute": "int8"},
    {"id": "ivrit-ai/whisper-large-v3-ct2",           "label": "large-v3 CPU",      "type": "hebrew", "device": "cpu",  "compute": "int8"},
    {"id": "ivrit-ai/whisper-large-v3-ct2",           "label": "large-v3 GPU fp16", "type": "hebrew", "device": "cuda", "compute": "float16"},
    {"id": "ivrit-ai/whisper-large-v3-ct2",           "label": "large-v3 GPU int8", "type": "hebrew", "device": "cuda", "compute": "int8"},
]

parser = argparse.ArgumentParser(description="Benchmark Whisper models for Hebrew")
parser.add_argument("--duration", type=int, default=10, help="Recording duration in seconds (default: 10)")
parser.add_argument("--file", type=str, default=None, help="Use existing audio file instead of recording")
parser.add_argument("--models", type=str, default=None,
                    help="Comma-separated model indices to test (e.g. '0,3,4' to skip small/medium)")
args = parser.parse_args()


# ── Step 1: Get audio ──────────────────────────────────────────────────────
if args.file:
    import wave
    print(f"Loading audio from {args.file}...")
    with wave.open(args.file, 'rb') as wf:
        frames = wf.readframes(wf.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        if wf.getframerate() != SAMPLE_RATE:
            print(f"  Warning: file sample rate is {wf.getframerate()}, expected {SAMPLE_RATE}")
    print(f"  Loaded {len(audio)/SAMPLE_RATE:.1f}s of audio\n")
else:
    print(f"Recording {args.duration}s of Hebrew speech from your microphone...")
    print("  Speak a clear Hebrew sentence NOW:\n")
    audio = sd.rec(int(args.duration * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='float32')
    sd.wait()
    audio = audio.flatten()
    print(f"  Recorded {len(audio)/SAMPLE_RATE:.1f}s of audio\n")

# Check if there's actual audio content
rms = np.sqrt(np.mean(audio ** 2))
if rms < 0.001:
    print("WARNING: Audio seems silent (RMS={:.6f}). Did you speak?".format(rms))
    print("Try again or check your microphone.\n")

# ── Step 2: Select models ──────────────────────────────────────────────────
if args.models:
    try:
        indices = [int(i) for i in args.models.split(",")]
    except ValueError:
        print(f"Error: --models must be comma-separated integers (e.g. '0,3,4')")
        sys.exit(1)
    for idx in indices:
        if idx < 0 or idx >= len(MODELS):
            print(f"Error: model index {idx} out of range (0-{len(MODELS)-1})")
            print("Available models:")
            for j, m in enumerate(MODELS):
                print(f"  {j}: {m['label']} ({m['id']})")
            sys.exit(1)
    selected = [MODELS[i] for i in indices]
else:
    selected = MODELS

print("=" * 75)
print(f"  Testing {len(selected)} models. First run downloads each model (one-time).")
print(f"  This may take a while for larger models...")
print("=" * 75)
print()

# ── Step 3: Benchmark each model ──────────────────────────────────────────
results = []

for i, m in enumerate(selected):
    label = m["label"]
    model_id = m["id"]

    print(f"[{i+1}/{len(selected)}] {label} ({model_id})")
    print(f"  Loading model...", end=" ", flush=True)

    load_start = time.time()
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(model_id, device=m.get("device", "cpu"), compute_type=m.get("compute", "int8"))
        load_time = time.time() - load_start
        print(f"done ({load_time:.1f}s)")
    except Exception as e:
        print(f"FAILED: {e}")
        results.append({"label": label, "id": model_id, "error": str(e)})
        continue

    print(f"  Transcribing...", end=" ", flush=True)
    transcribe_start = time.time()
    try:
        segments, info = model.transcribe(
            audio,
            language="he",
            beam_size=1,
            vad_filter=False,
        )
        text_parts = [seg.text.strip() for seg in segments]
        text = " ".join(text_parts).strip()
        transcribe_time = time.time() - transcribe_start
        print(f"done ({transcribe_time:.1f}s)")
    except Exception as e:
        print(f"FAILED: {e}")
        results.append({"label": label, "id": model_id, "error": str(e)})
        continue

    print(f"  Result: {text}\n")
    results.append({
        "label": label,
        "id": model_id,
        "text": text,
        "load_time": load_time,
        "transcribe_time": transcribe_time,
    })

    # Free memory before loading next model
    del model

# ── Step 4: Summary table ─────────────────────────────────────────────────
print("\n" + "=" * 75)
print("  RESULTS SUMMARY")
print("=" * 75)
print(f"{'Model':<28} {'Load':>6} {'Transcr':>8} {'Total':>7}  Text")
print("-" * 75)

for r in results:
    if "error" in r:
        print(f"{r['label']:<28} {'ERROR':>6}  {r['error'][:40]}")
    else:
        total = r["load_time"] + r["transcribe_time"]
        text_preview = r["text"][:35] + "..." if len(r["text"]) > 35 else r["text"]
        print(f"{r['label']:<28} {r['load_time']:>5.1f}s {r['transcribe_time']:>7.1f}s {total:>6.1f}s  {text_preview}")

print("-" * 75)
print("\nFull transcriptions:")
for r in results:
    if "text" in r:
        print(f"\n  [{r['label']}]")
        print(f"  {r['text']}")

print("\n\nPick the model with the best Hebrew accuracy and acceptable speed.")
print("Use it in hebrew-dictate with: python hebrew-dictate.py --model <model-id>")
