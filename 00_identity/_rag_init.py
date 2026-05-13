import sqlite3
db=r"C:\AI_VAULT\00_identity\brain.db"
con=sqlite3.connect(db)
cur=con.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS doc_store (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts DATETIME DEFAULT CURRENT_TIMESTAMP,
  doc_name TEXT NOT NULL,
  doc_path TEXT NOT NULL,
  doc_type TEXT NOT NULL,
  sha256 TEXT,
  notes TEXT
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS doc_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts DATETIME DEFAULT CURRENT_TIMESTAMP,
  doc_id INTEGER NOT NULL,
  chunk_index INTEGER NOT NULL,
  page_start INTEGER,
  page_end INTEGER,
  chunk_text TEXT NOT NULL,
  FOREIGN KEY(doc_id) REFERENCES doc_store(id)
);
""")

con.commit()
con.close()
print("OK: tablas doc_store/doc_chunks creadas")
