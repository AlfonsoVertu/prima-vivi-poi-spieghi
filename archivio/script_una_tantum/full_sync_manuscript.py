import sqlite3
import os
import re
import json
from vector_index_local import rebuild_index

DB_PATH = 'roman.db'
CAPITOLI_DIR = 'capitoli'
SUMMARY_FILE = 'RIASSUNTO_OPERA.md'

def read_txt(cap_id):
    path = os.path.join(CAPITOLI_DIR, f"cap{cap_id:02d}.txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def parse_summaries(file_path):
    summaries = {}
    if not os.path.exists(file_path):
        return summaries
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Cerca pattern: ## Capitolo X: capXX.txt\n[Riassunto]
    pattern = r"## Capitolo (\d+):.*?\n(.*?)(?=\n##|$)"
    matches = re.finditer(pattern, content, re.DOTALL)
    for m in matches:
        cap_id = int(m.group(1))
        summary = m.group(2).strip()
        summaries[cap_id] = summary
    return summaries

def full_sync():
    print("Avvio sincronizzazione completa...")
    if not os.path.exists(DB_PATH):
        print("Errore: Database non trovato.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Recupera tutti i capitoli dal DB
    chapters = cursor.execute("SELECT id, titolo, pov, linea_narrativa FROM capitoli ORDER BY id").fetchall()
    chapters_list = [dict(c) for c in chapters]
    
    # 2. Carica i nuovi riassunti
    new_summaries = parse_summaries(SUMMARY_FILE)
    
    # 3. Aggiorna Parole e Riassunti nel DB
    print("Aggiornamento conteggi parole e riassunti nel database...")
    updates_count = 0
    for i in range(1, 67):
        content = read_txt(i)
        if content:
            words = len(re.findall(r'\w+', content))
            summary = new_summaries.get(i, "")
            
            cursor.execute("""
                UPDATE capitoli 
                SET parole = ?, parole_file = ?, riassunto = ? 
                WHERE id = ?
            """, (words, words, summary, i))
            updates_count += 1
    
    conn.commit()
    print(f"Aggiornati {updates_count} capitoli nel DB.")
    
    # 4. Ricostruisci l'indice vettoriale
    print("Ricostruzione indice vettoriale (ricerca)...")
    try:
        result = rebuild_index(
            conn, 
            chapters_list, 
            read_txt,
            embedding_provider="hash_local" # Usiamo hash_local per velocità e indipendenza API
        )
        print(f"Indice ricostruito: {result['chunks_inserted']} chunk inseriti.")
    except Exception as e:
        print(f"Errore durante la ricostruzione dell'indice: {e}")

    conn.close()
    print("Sincronizzazione completata con successo!")

if __name__ == "__main__":
    full_sync()
