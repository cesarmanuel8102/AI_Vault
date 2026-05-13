"""List all .ts files with sizes and estimate total transcription time."""
import os, glob

folder = "E:/Yoel"
files = sorted(glob.glob(os.path.join(folder, "*.ts")))

total_bytes = 0
print(f"{'#':>3} {'File':<45} {'Size MB':>8}")
print("-" * 60)
for i, f in enumerate(files, 1):
    sz = os.path.getsize(f)
    total_bytes += sz
    name = os.path.basename(f)
    print(f"{i:3d} {name:<45} {sz/1024/1024:8.1f}")

print("-" * 60)
print(f"    {'TOTAL':<45} {total_bytes/1024/1024:8.1f} MB")
print(f"    Files: {len(files)}")

# Compra Venta was 116.7MB = 14.1 min audio = 41.7s transcription (base model CPU)
# Rate: ~14.1 min audio in 41.7s = ~20x realtime
# Audio extraction: ~0.6s for 14 min = negligible
# Estimate: total_mb / 116.7 * 14.1 min of audio / 20x = transcription seconds
ratio_mb_to_min = 14.1 / 116.7  # min audio per MB of .ts
total_audio_min = total_bytes / (1024*1024) * ratio_mb_to_min
total_transcribe_sec = total_audio_min * 60 / 20  # 20x realtime
print(f"\n    Estimated total audio: ~{total_audio_min:.0f} min ({total_audio_min/60:.1f} hours)")
print(f"    Estimated transcription time: ~{total_transcribe_sec/60:.0f} min ({total_transcribe_sec/3600:.1f} hours)")
print(f"    Estimated extraction time: ~{len(files)*2:.0f} sec")
