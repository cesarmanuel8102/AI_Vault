import sqlite3
db = r"C:\AI_VAULT\00_identity\brain.db"
con = sqlite3.connect(db)
cur = con.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
tables = [t[0] for t in cur.fetchall()]
print("TABLAS:", tables)

def count(t):
    try:
        cur.execute(f"SELECT COUNT(*) FROM {t};")
        return cur.fetchone()[0]
    except Exception as e:
        return f"ERR({e})"

print("memory_facts:", count("memory_facts"))
print("memory_decisions:", count("memory_decisions"))
print("memory_results:", count("memory_results"))

con.close()
