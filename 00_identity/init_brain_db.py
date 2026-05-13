import sqlite3, os

db_path = r"C:\AI_VAULT\00_identity\brain.db"
os.makedirs(os.path.dirname(db_path), exist_ok=True)

con = sqlite3.connect(db_path)
cur = con.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS memory_facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts DATETIME DEFAULT CURRENT_TIMESTAMP,
  domain TEXT NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  source TEXT,
  confidence REAL DEFAULT 0.7
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS memory_decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts DATETIME DEFAULT CURRENT_TIMESTAMP,
  domain TEXT NOT NULL,
  decision TEXT NOT NULL,
  rationale TEXT,
  risks TEXT,
  alternatives TEXT,
  status TEXT DEFAULT 'proposed'
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS memory_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts DATETIME DEFAULT CURRENT_TIMESTAMP,
  domain TEXT NOT NULL,
  related_decision_id INTEGER,
  outcome TEXT NOT NULL,
  metrics TEXT,
  notes TEXT,
  FOREIGN KEY(related_decision_id) REFERENCES memory_decisions(id)
);
""")

con.commit()
con.close()

print("OK: brain.db creado en", db_path)
