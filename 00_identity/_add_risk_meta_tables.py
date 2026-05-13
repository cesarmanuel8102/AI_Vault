import sqlite3
db = r"C:\AI_VAULT\00_identity\brain.db"
con = sqlite3.connect(db)
cur = con.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS risk_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts DATETIME DEFAULT CURRENT_TIMESTAMP,
  domain TEXT NOT NULL,
  mode TEXT NOT NULL,
  query TEXT NOT NULL,
  risk_technical TEXT,
  risk_normative TEXT,
  risk_financial TEXT,
  risk_operational TEXT,
  risk_bias TEXT,
  risk_overfit TEXT,
  risk_data_insufficient TEXT,
  overall_risk TEXT,
  confidence REAL DEFAULT 0.6
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS meta_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts DATETIME DEFAULT CURRENT_TIMESTAMP,
  domain TEXT NOT NULL,
  query TEXT NOT NULL,
  draft TEXT NOT NULL,
  critique TEXT NOT NULL,
  final TEXT NOT NULL
);
""")

con.commit()
con.close()
print("OK: tablas risk_logs y meta_reviews creadas")
