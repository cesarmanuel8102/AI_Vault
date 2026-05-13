"""Inspect E:\Compra Venta.ts - local copy."""
import os

path = "E:/Compra Venta.ts"
size = os.path.getsize(path)
print(f"Size: {size:,} bytes ({size/1024/1024:.1f} MB)")

fd = os.open(path, os.O_RDONLY | os.O_BINARY)
header = os.read(fd, 1024)
os.close(fd)
print(f"Read {len(header)} header bytes")

# Show hex
print("\nFirst 64 bytes:")
for i in range(0, min(64, len(header)), 16):
    hx = " ".join(f"{b:02X}" for b in header[i:i+16])
    asc = "".join(chr(b) if 32 <= b < 127 else "." for b in header[i:i+16])
    print(f"  {i:04X}: {hx:<48s}  {asc}")

# Identify format
if header[0] == 0x47 and len(header) > 376 and header[188] == 0x47 and header[376] == 0x47:
    print("\n=> MPEG Transport Stream (VIDEO)")
    print(f"=> Est. duration: ~{size/(3*1024*1024):.0f} min")
elif header[:3] == b'\xff\xfb\x90' or header[:2] == b'\xff\xfb':
    print("\n=> MP3 audio")
elif header[:4] == b'\x1a\x45\xdf\xa3':
    print("\n=> Matroska/WebM video")
elif all(b == 0 for b in header[:64]):
    print("\n=> Still all zeros - file not actually downloaded")
else:
    try:
        text = header.decode("utf-8")
        print(f"\n=> TEXT file. First 500 chars:\n{text[:500]}")
    except:
        print(f"\n=> Unknown binary. First byte: 0x{header[0]:02X}")
