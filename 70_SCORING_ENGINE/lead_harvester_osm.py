import os, csv, json, re, time
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ROOT = os.environ.get("BRAINLAB_ROOT", r"C:\AI_VAULT")
LEADS_CSV = os.path.join(ROOT, r"60_METRICS\leads.csv")

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# --- Config (facts-first): location + radius + tags ---
# Miami center (Downtown-ish). You can change later.
CENTER_LAT = 25.7751
CENTER_LON = -80.1947
RADIUS_M   = 15000  # 15 km

# Niches we can pull reliably from OSM tags (objective)
# office=accountant / amenity=dentist / amenity=clinic / craft=construction / shop=computer / office=it / etc.
TAG_QUERIES = [
    ("office", "accountant",   "B2B", "email_or_dm"),
    ("amenity","dentist",      "B2B", "email_or_dm"),
    ("amenity","clinic",       "B2B", "email_or_dm"),
    ("craft",  "construction", "B2B", "email_or_dm"),
    ("office", "it",           "B2B", "email_or_dm"),
    ("shop",   "computer",     "B2B", "email_or_dm"),
    ("office", "company",      "B2B", "email_or_dm"),
]

# --------- helpers ----------
def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip())

def safe_get(d, k):
    v = d.get(k, "")
    return norm(str(v)) if v is not None else ""

def http_head_or_get(url, timeout=4):
    # Returns True if reachable (status < 500)
    try:
        req = Request(url, method="HEAD", headers={"User-Agent":"BrainLabLeadHarvester/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 500
    except Exception:
        try:
            req = Request(url, method="GET", headers={"User-Agent":"BrainLabLeadHarvester/1.0"})
            with urlopen(req, timeout=timeout) as resp:
                return 200 <= resp.status < 500
        except Exception:
            return False

def ensure_leads_schema():
    if not os.path.exists(LEADS_CSV):
        os.makedirs(os.path.dirname(LEADS_CSV), exist_ok=True)
        headers = ["lead_id","segment","channel","name","company","role","email_or_handle","city","notes","status","created_at","validated","source"]
        with open(LEADS_CSV, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(headers)
        return

    # If file exists but missing columns, rewrite with union columns (non-destructive best-effort)
    with open(LEADS_CSV, "r", newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        rows = list(r)
    if not rows:
        headers = ["lead_id","segment","channel","name","company","role","email_or_handle","city","notes","status","created_at","validated","source"]
        with open(LEADS_CSV, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(headers)
        return

    header = rows[0]
    needed = ["validated","source"]
    if all(x in header for x in needed):
        return

    # Build new header
    new_header = list(header)
    for k in needed:
        if k not in new_header:
            new_header.append(k)

    # Rewrite
    out = [new_header]
    idx = {h:i for i,h in enumerate(header)}
    for row in rows[1:]:
        row = row + [""]*(len(header)-len(row))
        new_row = [row[idx[h]] if h in idx else "" for h in new_header]
        out.append(new_row)

    with open(LEADS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerows(out)

def load_existing_keys():
    keys=set()
    with open(LEADS_CSV, "r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            k = norm(row.get("email_or_handle","")).lower()
            if k:
                keys.add(k)
    return keys

def overpass_fetch(tag_key, tag_val, radius_m, lat, lon):
    # Query nodes+ways+relations around point with tag
    q = f"""
[out:json][timeout:25];
(
  node["{tag_key}"="{tag_val}"](around:{radius_m},{lat},{lon});
  way["{tag_key}"="{tag_val}"](around:{radius_m},{lat},{lon});
  relation["{tag_key}"="{tag_val}"](around:{radius_m},{lat},{lon});
);
out center tags;
"""
    data = q.encode("utf-8")
    req = Request(OVERPASS_URL, data=data, headers={"User-Agent":"BrainLabLeadHarvester/1.0","Content-Type":"application/x-www-form-urlencoded"})
    with urlopen(req, timeout=35) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))

def pick_contact(tags):
    # Prefer website, then email, then phone
    website = safe_get(tags, "website") or safe_get(tags, "contact:website")
    email   = safe_get(tags, "email") or safe_get(tags, "contact:email")
    phone   = safe_get(tags, "phone") or safe_get(tags, "contact:phone")
    if website:
        if not website.lower().startswith(("http://","https://")):
            website = "https://" + website
        return ("website", website)
    if email:
        return ("email", email)
    if phone:
        return ("phone", phone)
    return ("", "")

def guess_city(tags):
    # OSM often has addr:city
    city = safe_get(tags, "addr:city")
    if city:
        return city
    return "Miami"

def upsert_leads(collected, segment, channel, source_label):
    ensure_leads_schema()
    existing_keys = load_existing_keys()
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    added = 0
    with open(LEADS_CSV, "a", newline="", encoding="utf-8") as f:
        fieldnames = ["lead_id","segment","channel","name","company","role","email_or_handle","city","notes","status","created_at","validated","source"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        seq = int(time.time())  # unique-ish seed

        for item in collected:
            tags = item.get("tags", {}) or {}
            name = safe_get(tags, "name")
            if not name:
                continue

            ctype, handle = pick_contact(tags)
            handle = norm(handle)
            if not handle:
                continue

            key = handle.lower()
            if key in existing_keys:
                continue

            city = guess_city(tags)
            company = name
            role = "Owner/Manager"
            notes = f"osm:{ctype}"
            status = "new"
            validated = "weak"

            # Validation: if website reachable OR has phone/email -> medium
            if ctype == "website" and http_head_or_get(handle):
                validated = "medium"
            elif ctype in ("email","phone"):
                validated = "medium"

            lead_id = f"L-OSM-{seq}"
            seq += 1

            w.writerow({
                "lead_id": lead_id,
                "segment": segment,
                "channel": channel,
                "name": "",
                "company": company,
                "role": role,
                "email_or_handle": handle,
                "city": city,
                "notes": notes,
                "status": status,
                "created_at": now,
                "validated": validated,
                "source": source_label
            })
            existing_keys.add(key)
            added += 1

    return added

def main():
    print("== Brain Lab Lead Harvester (OSM/Overpass) ==")
    print(f"Center: {CENTER_LAT},{CENTER_LON}  Radius(m): {RADIUS_M}")
    total_added = 0
    total_seen = 0

    for tag_key, tag_val, segment, channel in TAG_QUERIES:
        try:
            js = overpass_fetch(tag_key, tag_val, RADIUS_M, CENTER_LAT, CENTER_LON)
            elems = js.get("elements", []) or []
            total_seen += len(elems)
            added = upsert_leads(elems, segment, channel, f"osm:{tag_key}={tag_val}")
            total_added += added
            print(f"OK {tag_key}={tag_val}: found={len(elems)} added={added}")
            time.sleep(1.2)  # be nice to Overpass
        except HTTPError as e:
            print(f"ERR {tag_key}={tag_val}: HTTPError {e.code}")
        except URLError as e:
            print(f"ERR {tag_key}={tag_val}: URLError {e}")
        except Exception as e:
            print(f"ERR {tag_key}={tag_val}: {e}")

    print("")
    print(f"DONE: total_seen={total_seen} total_added={total_added}")
    print(f"LEADS_CSV: {LEADS_CSV}")

if __name__ == "__main__":
    main()