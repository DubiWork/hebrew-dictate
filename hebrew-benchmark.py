"""
Hebrew Whisper Model Benchmark
Records multiple samples from your microphone, then tests against models.
Compares: accuracy (you judge), transcription speed, and model load time.

Usage:
    python hebrew-benchmark.py                   # record 3 samples, test all models
    python hebrew-benchmark.py --duration 10     # 10s per sample
    python hebrew-benchmark.py --samples 5       # record 5 samples
    python hebrew-benchmark.py --file test.wav   # use existing audio file (1 sample)
    python hebrew-benchmark.py --models 0,2      # test only specific models
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

# Models to benchmark
MODELS = [
    {"id": "ivrit-ai/whisper-large-v3-turbo-ct2", "revision": None,         "label": "turbo (default)",       "device": "cuda", "compute": "int8"},
    {"id": "ivrit-ai/whisper-large-v3-turbo-ct2", "revision": "2025.05.13", "label": "turbo (2025.05.13)",    "device": "cuda", "compute": "int8"},
    {"id": "ivrit-ai/whisper-large-v3-ct2",       "revision": None,         "label": "large-v3 (default)",    "device": "cuda", "compute": "int8"},
    {"id": "ivrit-ai/whisper-large-v3-ct2",       "revision": "2025.05.13", "label": "large-v3 (2025.05.13)", "device": "cuda", "compute": "int8"},
    {"id": "ivrit-ai/faster-whisper-v2-d4",       "revision": None,         "label": "v2-d4 (older)",         "device": "cuda", "compute": "int8"},
]

SAMPLE_TYPES = [
    "Normal conversational Hebrew (natural pace, everyday topic)",
    "Fast speech with technical terms (software, numbers, English words)",
    "Slow, clear dictation (like reading from a document)",
]

parser = argparse.ArgumentParser(description="Benchmark Whisper models for Hebrew")
parser.add_argument("--duration", type=int, default=8, help="Recording duration per sample in seconds (default: 8)")
parser.add_argument("--samples", type=int, default=3, help="Number of samples to record (default: 3)")
parser.add_argument("--file", type=str, default=None, help="Use existing audio file instead of recording")
parser.add_argument("--models", type=str, default=None,
                    help="Comma-separated model indices to test (e.g. '0,1,3')")
parser.add_argument("--no-prompt", action="store_true", help="Don't use initial_prompt")
args = parser.parse_args()


# ── Step 1: Record or load audio samples ──────────────────────────────────
samples = []

if args.file:
    import wave
    print(f"Loading audio from {args.file}...")
    with wave.open(args.file, 'rb') as wf:
        frames = wf.readframes(wf.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        if wf.getframerate() != SAMPLE_RATE:
            print(f"  Warning: file sample rate is {wf.getframerate()}, expected {SAMPLE_RATE}")
    print(f"  Loaded {len(audio)/SAMPLE_RATE:.1f}s of audio\n")
    samples.append({"label": args.file, "audio": audio})
else:
    n = min(args.samples, len(SAMPLE_TYPES))
    print(f"Recording {n} samples of {args.duration}s each.\n")
    for i in range(n):
        print(f"  Sample {i+1}/{n}: {SAMPLE_TYPES[i]}")
        try:
            input("  Press ENTER when ready to record...")
        except EOFError:
            # Non-interactive mode — auto-record with countdown
            print("  Auto-recording in 3...", end="", flush=True)
            time.sleep(1)
            print(" 2...", end="", flush=True)
            time.sleep(1)
            print(" 1...", end="", flush=True)
            time.sleep(1)
            print()
        print(f"  Recording {args.duration}s — SPEAK NOW...")
        audio = sd.rec(int(args.duration * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='float32')
        sd.wait()
        audio = audio.flatten()
        rms = np.sqrt(np.mean(audio ** 2))
        if rms < 0.001:
            print(f"  WARNING: Audio seems silent (RMS={rms:.6f}). Did you speak?")
        else:
            print(f"  Recorded {len(audio)/SAMPLE_RATE:.1f}s (RMS={rms:.4f})")
        samples.append({"label": SAMPLE_TYPES[i], "audio": audio})
        print()

# ── Step 2: Select models ─────────────────────────────────────────────────
if args.models:
    try:
        indices = [int(i) for i in args.models.split(",")]
    except ValueError:
        print(f"Error: --models must be comma-separated integers (e.g. '0,1,3')")
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

print("=" * 80)
print(f"  Testing {len(selected)} models x {len(samples)} samples = {len(selected)*len(samples)} transcriptions")
print(f"  First run downloads each model (one-time).")
print("=" * 80)
print()

# ── Step 3: Benchmark each model ─────────────────────────────────────────
from faster_whisper import WhisperModel

results = []  # list of {label, id, revision, load_time, samples: [{text, time}], error?}

for i, m in enumerate(selected):
    label = m["label"]
    model_id = m["id"]
    revision = m.get("revision")

    rev_str = f" @ {revision}" if revision else ""
    print(f"[{i+1}/{len(selected)}] {label} ({model_id}{rev_str})")
    print(f"  Loading model...", end=" ", flush=True)

    load_start = time.time()
    try:
        load_kwargs = {"device": m["device"], "compute_type": m["compute"]}
        if revision:
            load_kwargs["revision"] = revision
        model = WhisperModel(model_id, **load_kwargs)
        load_time = time.time() - load_start
        print(f"done ({load_time:.1f}s)")
    except Exception as e:
        print(f"FAILED: {e}")
        results.append({"label": label, "id": model_id, "revision": revision, "error": str(e)})
        continue

    sample_results = []
    for si, sample in enumerate(samples):
        print(f"  Sample {si+1}/{len(samples)}: ", end="", flush=True)
        t_start = time.time()
        try:
            transcribe_args = {
                "language": "he",
                "beam_size": 1,
                "vad_filter": False,
                "word_timestamps": True,
            }
            if not args.no_prompt:
                transcribe_args["initial_prompt"] = "שלום, זוהי הקלטה בעברית. אני מדבר בעברית."

            segments, info = model.transcribe(sample["audio"], **transcribe_args)
            text_parts = [seg.text.strip() for seg in segments]
            text = " ".join(text_parts).strip()
            t_elapsed = time.time() - t_start
            print(f"({t_elapsed:.2f}s) {text[:80]}{'...' if len(text) > 80 else ''}")
            sample_results.append({"text": text, "time": t_elapsed})
        except Exception as e:
            print(f"FAILED: {e}")
            sample_results.append({"text": f"ERROR: {e}", "time": 0})

    results.append({
        "label": label,
        "id": model_id,
        "revision": revision,
        "load_time": load_time,
        "samples": sample_results,
    })

    # Free GPU memory before next model
    del model
    print()

# ── Step 4: Summary ──────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("  RESULTS SUMMARY")
print("=" * 80)

# Speed table
avg_header = "Avg Time"
print(f"\n{'Model':<30} {'Load':>6} {avg_header:>9}  {'Fastest':>8}  {'Slowest':>8}")
print("-" * 75)

for r in results:
    if "error" in r:
        print(f"{r['label']:<30} {'ERROR':>6}  {r['error'][:40]}")
    else:
        times = [s["time"] for s in r["samples"]]
        avg_t = sum(times) / len(times) if times else 0
        min_t = min(times) if times else 0
        max_t = max(times) if times else 0
        print(f"{r['label']:<30} {r['load_time']:>5.1f}s {avg_t:>8.2f}s {min_t:>8.2f}s {max_t:>8.2f}s")

print("-" * 75)

# Full transcriptions per sample
for si, sample in enumerate(samples):
    print(f"\n{'='*80}")
    print(f"  SAMPLE {si+1}: {sample['label']}")
    print(f"{'='*80}")
    for r in results:
        if "error" in r:
            print(f"\n  [{r['label']}] ERROR: {r['error']}")
        else:
            s = r["samples"][si]
            print(f"\n  [{r['label']}] ({s['time']:.2f}s)")
            print(f"  {s['text']}")

print(f"\n{'='*80}")
print("  RECOMMENDATIONS")
print(f"{'='*80}")
print("""
Compare the transcriptions above for each sample:
  - Which model captured ALL the words? (no missing words)
  - Which model has correct spacing? (no glued words)
  - Which model handles technical terms best?
  - Is the speed difference noticeable?

To use a specific model in hebrew-dictate.pyw, update DEFAULT_MODEL.
To use a specific revision, add revision='2025.05.13' to WhisperModel().
""")
