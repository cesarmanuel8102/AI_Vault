import subprocess, re

# Get ARP table
result = subprocess.run(['arp', '-a'], capture_output=True, text=True)
lines = result.stdout.strip().split('\n')

macs = {}
for line in lines:
    m = re.search(r'(192\.168\.\d+\.\d+)\s+([\w-]+)\s+dynamic', line)
    if m:
        ip = m.group(1)
        mac = m.group(2).replace('-', ':').upper()
        macs[ip] = mac

# MAC vendor lookup via maclookup.app (free, no key needed)
import urllib.request, json

print(f"{'IP':<18} {'MAC':<20} {'Vendor/Fabricante'}")
print("=" * 70)

for ip, mac in sorted(macs.items()):
    vendor = "???"
    try:
        url = f"https://api.maclookup.app/v2/macs/{mac}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())
        vendor = data.get('company', '???') or '???'
    except Exception as e:
        vendor = f"Error: {e}"
    print(f"{ip:<18} {mac:<20} {vendor}")
