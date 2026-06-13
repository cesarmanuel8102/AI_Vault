import faiss
idx=faiss.read_index('memory/semantic/semantic_memory_faiss.index')
print(idx.ntotal)
