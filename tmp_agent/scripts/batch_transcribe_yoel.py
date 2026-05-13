"""Batch transcribe ALL Yoel videos with incremental save + resume support.
Run detached: powershell Start-Process python -ArgumentList 'this_script.py' -WindowStyle Normal
"""
import os, glob, wave, time, sys, json
import numpy as np

# ---- CONFIG ----
FOLDER = "E:/Yoel"
FFMPEG = r"C:\Users\cesar\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe"
OUTPUT_FILE = os.path.join(FOLDER, "Yoel_Sardinas_Transcripcion_Completa.txt")
TEMP_WAV = os.path.join(FOLDER, "_temp_audio.wav")
TRANSCRIPTS_DIR = os.path.join(FOLDER, "transcripts")
PROGRESS_FILE = os.path.join(FOLDER, "transcripts", "_progress.json")
LOG_FILE = os.path.join(FOLDER, "transcripts", "_log.txt")
MODEL_NAME = "base"

os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ---- Collect .ts files in logical order ----
ts_files = sorted(glob.glob(os.path.join(FOLDER, "*.ts")))
log(f"Found {len(ts_files)} .ts files")

import re
def sort_key(path):
    name = os.path.basename(path).lower()
    if "tutorial" in name: return (0, name)
    if "graficos" in name: return (1, name)
    if "soportes" in name: return (2, name)
    if "lineas" in name: return (3, name)
    if "compra venta" in name: return (4, name)
    if "rango de precios" in name: return (5, name)
    if "tc 2000" in name: return (6, name)
    if "desde cero" in name: return (7, name)
    if "primer master" in name: return (8, name)
    if "segundo master" in name: return (9, name)
    if "tercer master" in name: return (10, name)
    if "comunidad sai" in name or "sai" in name:
        m = re.search(r'(\d+)', name)
        num = int(m.group(1)) if m else 0
        return (11, num)
    return (12, name)

ts_files.sort(key=sort_key)

# ---- Helper: safe filename from title ----
def safe_name(title):
    return re.sub(r'[<>:"/\\|?*]', '_', title)

# ---- Load Whisper model once ----
log(f"Loading Whisper model '{MODEL_NAME}'...")
t0 = time.time()
import whisper
model = whisper.load_model(MODEL_NAME)
log(f"Model loaded in {time.time()-t0:.1f}s")

# ---- Process each file ----
total_start = time.time()
completed = 0
skipped = 0
errors = 0

for idx, ts_path in enumerate(ts_files, 1):
    name = os.path.basename(ts_path)
    title = os.path.splitext(name)[0]
    safe = safe_name(title)
    transcript_file = os.path.join(TRANSCRIPTS_DIR, f"{safe}.txt")
    size_mb = os.path.getsize(ts_path) / (1024*1024)

    # Skip if already transcribed
    if os.path.exists(transcript_file) and os.path.getsize(transcript_file) > 50:
        skipped += 1
        log(f"[{idx}/{len(ts_files)}] SKIP (already done): {title}")
        continue

    log(f"[{idx}/{len(ts_files)}] Processing: {title} ({size_mb:.1f} MB)")

    # Step 1: Extract audio with ffmpeg
    if os.path.exists(TEMP_WAV):
        os.remove(TEMP_WAV)

    import subprocess
    cmd = [
        FFMPEG, "-y", "-i", ts_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        TEMP_WAV
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0 or not os.path.exists(TEMP_WAV):
            log(f"  ERROR extracting audio: {result.stderr[-200:]}")
            with open(transcript_file, "w", encoding="utf-8") as f:
                f.write(f"[ERROR: No se pudo extraer audio]\n")
            errors += 1
            continue
    except subprocess.TimeoutExpired:
        log(f"  ERROR: ffmpeg timeout (>300s)")
        errors += 1
        continue

    # Step 2: Load WAV
    try:
        with wave.open(TEMP_WAV, "r") as wf:
            sr = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        duration = len(audio) / sr
        log(f"  Audio: {duration:.0f}s ({duration/60:.1f} min)")
        if duration < 2.0:
            log(f"  SKIPPING: too short")
            with open(transcript_file, "w", encoding="utf-8") as f:
                f.write(f"[Audio muy corto: {duration:.1f}s]\n")
            continue
    except Exception as e:
        log(f"  ERROR loading WAV: {e}")
        errors += 1
        continue

    # Step 3: Transcribe
    t2 = time.time()
    try:
        result = model.transcribe(audio, language="es", verbose=False)
        transcribe_time = time.time() - t2
        text = result["text"].strip()
        segments = result.get("segments", [])
        log(f"  Done: {transcribe_time:.1f}s, {len(segments)} segments, {len(text)} chars")

        # Save individual transcript immediately
        with open(transcript_file, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        completed += 1

    except Exception as e:
        log(f"  ERROR transcribing: {e}")
        with open(transcript_file, "w", encoding="utf-8") as f:
            f.write(f"[ERROR transcribiendo: {e}]\n")
        errors += 1
        continue

    # Save progress
    elapsed = time.time() - total_start
    pct = idx / len(ts_files)
    eta = elapsed / max(pct, 0.01) * (1 - pct)
    progress = {
        "completed": completed, "skipped": skipped, "errors": errors,
        "total": len(ts_files), "current_idx": idx,
        "elapsed_min": round(elapsed/60, 1), "eta_min": round(eta/60, 1),
        "last_file": title
    }
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)
    log(f"  Progress: {idx}/{len(ts_files)} ({pct*100:.0f}%) | Elapsed: {elapsed/60:.1f}m | ETA: {eta/60:.1f}m")

# ---- Cleanup temp ----
if os.path.exists(TEMP_WAV):
    os.remove(TEMP_WAV)

# ---- Concatenate all individual transcripts into final document ----
log(f"\nConcatenating all transcripts into {OUTPUT_FILE}")

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("=" * 80 + "\n")
    f.write("TRANSCRIPCION COMPLETA - CURSO YOEL SARDINAS\n")
    f.write("Seminario Aprendiendo a Invertir (SAI)\n")
    f.write(f"Transcrito automaticamente con OpenAI Whisper ({MODEL_NAME})\n")
    f.write(f"Fecha: {time.strftime('%Y-%m-%d %H:%M')}\n")
    f.write(f"Total videos: {len(ts_files)}\n")
    f.write("=" * 80 + "\n\n")

    for i, ts_path in enumerate(ts_files, 1):
        title = os.path.splitext(os.path.basename(ts_path))[0]
        safe = safe_name(title)
        transcript_file = os.path.join(TRANSCRIPTS_DIR, f"{safe}.txt")
        f.write(f"\n{'='*80}\n")
        f.write(f"VIDEO {i}/{len(ts_files)}: {title}\n")
        f.write(f"{'='*80}\n\n")
        if os.path.exists(transcript_file):
            with open(transcript_file, "r", encoding="utf-8") as tf:
                f.write(tf.read())
        else:
            f.write("[NO TRANSCRITO]\n")
        f.write("\n")

total_elapsed = time.time() - total_start
log(f"\nDONE! Total time: {total_elapsed/60:.1f} min ({total_elapsed/3600:.1f} hours)")
log(f"Output: {OUTPUT_FILE}")
log(f"Completed: {completed}, Skipped: {skipped}, Errors: {errors}, Total: {len(ts_files)}")
