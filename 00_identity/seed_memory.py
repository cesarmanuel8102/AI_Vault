import sqlite3

db_path = r"C:\AI_VAULT\00_identity\brain.db"
con = sqlite3.connect(db_path)
cur = con.cursor()

facts = [
 ("identity","preferred_language","es","user"),
 ("identity","primary_goals","IA local para CEI/FDOT + Trading + Programación","user"),
 ("hardware","ram_current","16GB DDR5 5600 (2x8GB), max 64GB","systeminfo"),
]

cur.executemany("INSERT INTO memory_facts(domain,key,value,source) VALUES(?,?,?,?)", facts)
con.commit()
con.close()

print("OK: facts iniciales insertados")
