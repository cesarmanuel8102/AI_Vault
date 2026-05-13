"""Transcribe Compra Venta - use pre-extracted WAV directly via numpy."""
import whisper
import numpy as np
import wave
import time
import os

# Whisper internally calls ffmpeg to load audio. Since ffmpeg isn't in PATH,
# we load the WAV manually and pass numpy array directly.

print("Loading WAV file...")
wav_path = "E:/compra_venta_audio.wav"

with wave.open(wav_path, "r") as wf:
    assert wf.getnchannels() == 1, "Expected mono"
    assert wf.getsampwidth() == 2, "Expected 16-bit"
    sr = wf.getframerate()
    n_frames = wf.getnframes()
    raw = wf.readframes(n_frames)

audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
duration = len(audio) / sr
print(f"Audio: {duration:.1f}s ({duration/60:.1f} min), sample rate: {sr} Hz")

# Whisper expects 16kHz - already extracted at 16kHz
assert sr == 16000, f"Expected 16kHz, got {sr}"

print("\nLoading Whisper model (base for speed on CPU)...")
t0 = time.time()
model = whisper.load_model("base")
print(f"Model loaded in {time.time()-t0:.1f}s")

print("\nTranscribing...")
t1 = time.time()
result = model.transcribe(
    audio,
    language="es",
    verbose=False
)
elapsed = time.time() - t1
print(f"Transcription done in {elapsed:.1f}s ({elapsed/60:.1f} min)")

# Save full text
with open("E:/compra_venta_transcripcion.txt", "w", encoding="utf-8") as f:
    f.write(result["text"])

# Save segments with timestamps
with open("E:/compra_venta_segmentos.txt", "w", encoding="utf-8") as f:
    for seg in result["segments"]:
        start = seg["start"]
        end = seg["end"]
        text = seg["text"].strip()
        m1, s1 = divmod(int(start), 60)
        m2, s2 = divmod(int(end), 60)
        f.write(f"[{m1:02d}:{s1:02d} - {m2:02d}:{s2:02d}] {text}\n")

print(f"\nTotal segments: {len(result['segments'])}")
print(f"Language: {result.get('language', '?')}")
print(f"\nSaved: E:/compra_venta_transcripcion.txt")
print(f"Saved: E:/compra_venta_segmentos.txt")
print(f"\n{'='*60}")
print("TRANSCRIPCION COMPLETA:")
print('='*60)
print(result["text"])
