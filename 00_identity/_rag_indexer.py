import os, re, hashlib, sqlite3
from pdfminer.high_level import extract_text

BASE = r"C:\AI_VAULT\00_identity"
DB   = os.path.join(BASE, "brain.db")
INBOX = os.path.join(BASE, "docs", "inbox")
INDEXED = os.path.join(BASE, "docs", "indexed")

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda: f.read(1024*1024), b""):
            h.update(b)
    return h.hexdigest()

def chunk_text(text, max_chars=1400, overlap=150):
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()
    if not text:
        return []
    chunks=[]
    i=0
    n=len(text)
    while i<n:
        j=min(n, i+max_chars)
        chunk=text[i:j]
        chunks.append(chunk.strip())
        if j==n: break
        i=max(0, j-overlap)
    return [c for c in chunks if len(c) >= 40]

def main():
    if not os.path.isdir(INBOX):
        print("NO INBOX:", INBOX); return

    files=[f for f in os.listdir(INBOX) if f.lower().endswith(".pdf")]
    if not files:
        print("NO PDFs IN INBOX"); return

    con=sqlite3.connect(DB)
    cur=con.cursor()

    for fn in files:
        path=os.path.join(INBOX, fn)
        digest=sha256_file(path)

        cur.execute("SELECT id FROM doc_store WHERE sha256=?", (digest,))
        row=cur.fetchone()
        if row:
            print("SKIP (already indexed):", fn)
            # mover a indexed igual
            os.replace(path, os.path.join(INDEXED, fn))
            continue

        txt = extract_text(path) or ""
        chunks = chunk_text(txt)

        cur.execute(
            "INSERT INTO doc_store(doc_name, doc_path, doc_type, sha256, notes) VALUES (?,?,?,?,?)",
            (fn, path, "pdf", digest, f"chunks={len(chunks)}")
        )
        doc_id = cur.lastrowid

        for idx, ch in enumerate(chunks):
            cur.execute(
                "INSERT INTO doc_chunks(doc_id, chunk_index, page_start, page_end, chunk_text) VALUES (?,?,?,?,?)",
                (doc_id, idx, None, None, ch)
            )

        con.commit()
        print("INDEXED:", fn, "doc_id=", doc_id, "chunks=", len(chunks))

        os.replace(path, os.path.join(INDEXED, fn))

    con.close()

if __name__=="__main__":
    main()
