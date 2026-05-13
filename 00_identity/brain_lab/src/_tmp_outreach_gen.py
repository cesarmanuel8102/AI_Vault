import os

ROOT = os.path.abspath(".")
OUT = os.path.join(ROOT,"memory","outreach")
os.makedirs(OUT, exist_ok=True)

emails = [
("IDEA_10_email_01.txt","SUBJECT: Optimización Windows rápida\n\nHola {name},\n\nTrabajo con oficinas pequeñas optimizando Windows + automatizando tareas repetitivas con PowerShell.\n\nTe interesa una llamada breve de 10 min para ver si aplica?\n\nSi no, dime 'no' y no vuelvo a escribir.\n\n{sender}")
]

for fname, body in emails:
    with open(os.path.join(OUT,fname),"w",encoding="utf-8") as f:
        f.write(body)

print("OK outreach files generated in:", OUT)
