"""Remove **bold**, backticks, and middle dots from session.py output strings."""
import re
import sys

filepath = r"C:\AI_VAULT\tmp_agent\brain_v9\core\session.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

original = content

# =============================================
# 1. Remove **bold** markdown: **text** -> text
#    But NOT {**dict} unpacking patterns
# =============================================

count_bold = [0]

def replace_bold(m):
    count_bold[0] += 1
    return m.group(1)

# Match **text** but NOT preceded by { (dict unpacking)
content = re.sub(r'(?<!\{)\*\*([^*\n]+?)\*\*', replace_bold, content)

print(f"Bold ** replacements: {count_bold[0]}")

# =============================================
# 2. Remove backtick markers from output f-strings
# =============================================

BACKTICK = chr(96)  # avoid bash interpretation

lines = content.split("\n")
new_lines = []
bt_removed = 0

for i, line in enumerate(lines):
    if BACKTICK not in line:
        new_lines.append(line)
        continue

    stripped = line.strip()

    # Skip comments and imports
    if stripped.startswith("#") or stripped.startswith("import") or stripped.startswith("from"):
        new_lines.append(line)
        continue

    # Only process lines that are string literals or f-strings
    has_fstring = ('f"' in line or "f'" in line)
    starts_with_string = (stripped.startswith('f"') or stripped.startswith("f'")
                          or stripped.startswith('"') or stripped.startswith("'"))

    if has_fstring or starts_with_string:
        count_before = line.count(BACKTICK)
        line = line.replace(BACKTICK, "")
        bt_removed += count_before
    
    new_lines.append(line)

content = "\n".join(new_lines)

print(f"Backticks removed: {bt_removed}")

# =============================================
# 3. Replace middle dot in fastpath area (lines 1970-2131)
# =============================================

lines = content.split("\n")
MIDDOT = chr(183)  # U+00B7
count_middot = 0

for i in range(1969, min(2131, len(lines))):
    if MIDDOT in lines[i]:
        lines[i] = lines[i].replace(MIDDOT, "|")
        count_middot += 1

content = "\n".join(lines)

print(f"Middle dot replacements: {count_middot}")

# =============================================
# 4. Verification
# =============================================

# Check {**self.data} preserved
if "{**self.data" in original:
    if "{**self.data" in content:
        print("OK: {**self.data} dict unpacking preserved")
    else:
        print("ERROR: {**self.data} dict unpacking was broken!")
        sys.exit(1)

# Check (1024 ** 3) preserved
if "(1024 ** 3)" in original:
    if "(1024 ** 3)" in content:
        print("OK: (1024 ** 3) arithmetic preserved")
    else:
        print("ERROR: (1024 ** 3) arithmetic was broken!")
        sys.exit(1)

# Count remaining issues
remaining_bold = len(re.findall(r'(?<!\{)\*\*([^*\n]+?)\*\*', content))
remaining_bt = content.count(BACKTICK)
print(f"Remaining bold markers: {remaining_bold}")
print(f"Remaining backticks: {remaining_bt}")

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("File written successfully")
