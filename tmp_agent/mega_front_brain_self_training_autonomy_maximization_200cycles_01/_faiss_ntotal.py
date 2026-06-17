import json
from pathlib import Path
p=Path('memory/semantic/semantic_memory_faiss.index')
try:
    import faiss
    idx=faiss.read_index(str(p))
    print(idx.ntotal)
except Exception:
    print('null')
