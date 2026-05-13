#!/usr/bin/env python3
"""
Búsqueda Semántica - Embeddings
Permite búsqueda por significado, no solo por texto
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import sys

sys.path.insert(0, str(Path(__file__).parent))


class SemanticSearcher:
    """Búsqueda semántica usando embeddings locales"""
    
    def __init__(self, cache_dir: str = None):
        if cache_dir is None:
            cache_dir = "C:/AI_VAULT/tmp_agent/cache/embeddings"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.documents: Dict[str, str] = {}
    
    def _simple_embedding(self, text: str) -> List[float]:
        """Genera embedding simple basado en frecuencia de palabras"""
        # Simplificación: usar hash como "embedding"
        words = text.lower().split()
        
        # Características simples
        features = [
            len(words),  # Longitud
            len(set(words)),  # Vocabulario único
            sum(len(w) for w in words) / len(words) if words else 0,  # Longitud promedio
            text.count('def '),  # Funciones
            text.count('class '),  # Clases
            text.count('import'),  # Imports
        ]
        
        return features
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calcula similitud coseno"""
        dot = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot / (norm1 * norm2)
    
    def index_document(self, doc_id: str, content: str):
        """Indexa un documento"""
        self.documents[doc_id] = content
        
        # Calcular y guardar embedding
        embedding = self._simple_embedding(content)
        cache_file = self.cache_dir / f"{doc_id}.json"
        
        with open(cache_file, 'w') as f:
            json.dump({"embedding": embedding, "content_preview": content[:200]}, f)
    
    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """Busca documentos similares"""
        query_embedding = self._simple_embedding(query)
        
        results = []
        for doc_id, content in self.documents.items():
            doc_embedding = self._simple_embedding(content)
            similarity = self._cosine_similarity(query_embedding, doc_embedding)
            results.append((doc_id, similarity))
        
        # Ordenar por similitud
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results[:top_k]


if __name__ == "__main__":
    # Test
    searcher = SemanticSearcher()
    
    # Indexar documentos
    searcher.index_document("doc1", "def test(): pass")
    searcher.index_document("doc2", "class MyClass: pass")
    searcher.index_document("doc3", "import os")
    
    # Buscar
    results = searcher.search("función python")
    print(f"Resultados: {results}")
