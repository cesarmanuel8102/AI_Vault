"""Inspect .ts file - try different read approaches for OneDrive files."""
import os, ctypes

path = r"E:\Users\cesar\OneDrive\Documentos\MEGA\MEGAsync Uploads\Yoel_Sardiñas\Compra Venta.ts"

size = os.path.getsize(path)
print(f"File size: {size:,} bytes ({size/1024/1024:.1f} MB)")

# Check file attributes
attrs = os.stat(path)
print(f"File mode: {oct(attrs.st_mode)}")

# Try approach: open with os.open low-level
import os as _os
try:
    fd = _os.open(path, _os.O_RDONLY | _os.O_BINARY)
    header = _os.read(fd, 1024)
    _os.close(fd)
    print(f"\nos.open: Read {len(header)} bytes")
except Exception as e:
    print(f"\nos.open failed: {e}")
    # Try mmap
    try:
        import mmap
        with open(path, "rb") as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                header = mm[:1024]
                print(f"mmap: Read {len(header)} bytes")
    except Exception as e2:
        print(f"mmap failed: {e2}")
        # Last resort: subprocess
        import subprocess
        result = subprocess.run(
            ["powershell", "-Command", 
             f"$f = [System.IO.File]::OpenRead('{path}'); $buf = New-Object byte[] 256; $n = $f.Read($buf, 0, 256); $f.Close(); [System.BitConverter]::ToString($buf[0..63])"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print(f"PowerShell read: {result.stdout.strip()}")
            header = bytes.fromhex(result.stdout.strip().replace("-",""))
        else:
            print(f"PowerShell failed: {result.stderr}")
            header = None

if header and len(header) > 0:
    print(f"\nFirst 64 bytes (hex):")
    for i in range(0, min(64, len(header)), 16):
        hex_part = " ".join(f"{b:02X}" for b in header[i:i+16])
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in header[i:i+16])
        print(f"  {i:04X}: {hex_part:<48s}  {ascii_part}")

    if header[0] == 0x47:
        print("\n=> First byte is 0x47 (MPEG-TS sync byte)")
        if len(header) > 376 and header[188] == 0x47 and header[376] == 0x47:
            print("=> CONFIRMED: MPEG Transport Stream VIDEO file")
            dur_lo = size / (4 * 1024 * 1024)
            dur_hi = size / (2 * 1024 * 1024)
            print(f"=> Estimated duration: ~{dur_lo:.0f}-{dur_hi:.0f} minutes")
        else:
            print("=> Sync byte pattern unclear at 188-byte intervals")
    else:
        try:
            text = header[:500].decode("utf-8", errors="strict")
            print(f"\n=> UTF-8 text content:\n{text[:500]}")
        except:
            print(f"\n=> Binary file (first byte: 0x{header[0]:02X})")
