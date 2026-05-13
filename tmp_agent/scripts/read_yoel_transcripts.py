"""
Read Yoel Sardiñas transcripts and extract sections around key strategy keywords.
Transcripts are single long lines (Whisper auto-transcription).
This script:
1. Reads each transcript fully
2. Splits into ~sentence chunks (by periods)
3. Searches for keywords and extracts surrounding context (N sentences before/after)
4. Outputs structured results
"""
import os
import sys
import re
import json
from pathlib import Path

TRANSCRIPTS_DIR = Path("E:/Yoel/transcripts")

# Strategy-related keywords to search for
STRATEGY_KEYWORDS = [
    # Bollinger
    "bollinger", "banda", "bandas", "punto medio", "media de bollinger",
    "banda superior", "banda inferior", "squeeze", "compresión",
    "salida de bollinger", "rebote",
    # Strategy names
    "cambio de tendencia", "refuerzo", "máximo histórico", "mínimo histórico",
    "salto", "gap", "post earnings", "después de earnings",
    "rebote en punto medio", "pullback",
    # Entry/Exit rules
    "entrada", "salida", "stop loss", "stop", "límite", "target",
    "tomar ganancia", "profit", "35%", "10%",
    # Indicators
    "estocástico", "stochastic", "volumen", "media móvil", "moving average",
    "sma", "ema", "20,", "40,", "100,", "200,",
    # Timeframes
    "temporalidad", "diario", "hora", "15 minutos", "semanal",
    # Risk/Position
    "riesgo", "posición", "capital", "cuenta",
    # Options
    "call", "put", "opción", "opciones", "contrato", "contratos",
    "strike", "expiración", "vencimiento",
    # Candles
    "vela", "velas", "martillo", "doji", "envolvente",
    # Checklist
    "checklist", "lista", "antes de operar", "fed", "earnings", "noticias",
    # Requisites
    "requisito", "condición", "regla", "criterio",
]

def read_transcript(filepath):
    """Read a transcript file and return its full content."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()

def split_into_sentences(text, chunk_size=150):
    """Split text into chunks of ~chunk_size words, breaking at periods."""
    # First try splitting by periods
    raw_sentences = re.split(r'(?<=[.!?])\s+', text)
    
    # Group into chunks of roughly chunk_size words
    chunks = []
    current_chunk = []
    current_words = 0
    
    for sent in raw_sentences:
        words = len(sent.split())
        if current_words + words > chunk_size and current_chunk:
            chunks.append(' '.join(current_chunk))
            current_chunk = [sent]
            current_words = words
        else:
            current_chunk.append(sent)
            current_words += words
    
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    return chunks

def search_keywords_in_chunks(chunks, keywords, context=1):
    """Search for keywords in chunks and return matches with context."""
    matches = []
    seen_indices = set()
    
    for keyword in keywords:
        kw_lower = keyword.lower()
        for i, chunk in enumerate(chunks):
            if kw_lower in chunk.lower() and i not in seen_indices:
                # Get context chunks
                start = max(0, i - context)
                end = min(len(chunks), i + context + 1)
                context_text = ' '.join(chunks[start:end])
                matches.append({
                    'keyword': keyword,
                    'chunk_index': i,
                    'text': context_text[:3000],  # Limit size
                })
                seen_indices.add(i)
    
    # Sort by chunk index for narrative order
    matches.sort(key=lambda x: x['chunk_index'])
    return matches

def analyze_transcript(filepath, keywords, context=1):
    """Analyze a single transcript file."""
    text = read_transcript(filepath)
    word_count = len(text.split())
    chunks = split_into_sentences(text)
    matches = search_keywords_in_chunks(chunks, keywords, context)
    return {
        'file': filepath.name,
        'word_count': word_count,
        'num_chunks': len(chunks),
        'num_matches': len(matches),
        'matches': matches
    }

def full_transcript_dump(filepath, output_dir):
    """Dump full transcript split into readable chunks."""
    text = read_transcript(filepath)
    chunks = split_into_sentences(text, chunk_size=100)
    
    output_file = output_dir / f"{filepath.stem}_chunked.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"=== {filepath.name} ===\n")
        f.write(f"Total words: {len(text.split())}\n")
        f.write(f"Total chunks: {len(chunks)}\n\n")
        for i, chunk in enumerate(chunks):
            f.write(f"\n--- Chunk {i+1}/{len(chunks)} ---\n")
            f.write(chunk)
            f.write("\n")
    
    return output_file

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "search"
    
    output_dir = Path("C:/AI_VAULT/tmp_agent/yoel_analysis")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if mode == "search":
        # Search all transcripts for strategy keywords
        print("=== Searching all transcripts for strategy keywords ===\n")
        
        all_results = []
        for filepath in sorted(TRANSCRIPTS_DIR.glob("*.txt")):
            result = analyze_transcript(filepath, STRATEGY_KEYWORDS)
            all_results.append(result)
            print(f"{result['file']}: {result['word_count']} words, {result['num_matches']} keyword matches")
        
        # Save results
        with open(output_dir / "keyword_search_results.json", 'w', encoding='utf-8') as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        
        print(f"\nResults saved to {output_dir / 'keyword_search_results.json'}")
        
        # Print top files by match count
        print("\n=== TOP FILES BY KEYWORD MATCHES ===")
        sorted_results = sorted(all_results, key=lambda x: x['num_matches'], reverse=True)
        for r in sorted_results[:15]:
            print(f"  {r['num_matches']:3d} matches | {r['word_count']:6d} words | {r['file']}")
    
    elif mode == "dump":
        # Dump specific transcript(s) into readable chunked format
        target_files = sys.argv[2:] if len(sys.argv) > 2 else [
            "Comunidad SAI_31.txt",
            "Comunidad SAI_33.txt",
            "Comunidad SAI_19.txt",
            "Comunidad SAI_30.txt",
            "Comunidad SAI_18.txt",
            "Comunidad SAI_20.txt",
            "Comunidad SAI_25.txt",
            "Desde cero,. saltos y metodologias.txt",
            "Tercer Master Class.txt",
            "Segundo Master Class.txt",
        ]
        
        for fname in target_files:
            filepath = TRANSCRIPTS_DIR / fname
            if filepath.exists():
                outfile = full_transcript_dump(filepath, output_dir)
                print(f"Dumped: {fname} -> {outfile}")
            else:
                print(f"NOT FOUND: {fname}")
    
    elif mode == "read":
        # Read a specific file fully and print it
        target = sys.argv[2] if len(sys.argv) > 2 else "Comunidad SAI_31.txt"
        filepath = TRANSCRIPTS_DIR / target
        if filepath.exists():
            text = read_transcript(filepath)
            chunks = split_into_sentences(text, chunk_size=100)
            for i, chunk in enumerate(chunks):
                print(f"\n--- [{i+1}/{len(chunks)}] ---")
                print(chunk)
        else:
            print(f"NOT FOUND: {target}")

if __name__ == "__main__":
    main()
