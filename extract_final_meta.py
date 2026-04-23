import sqlite3
import json

conn = sqlite3.connect('roman.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

ids = [63, 64, 65, 66]
for cid in ids:
    row = cursor.execute("""
        SELECT id, titolo, pov, riassunto, scene_outline, personaggi_capitolo, 
               oggetti_simbolo, tensione_capitolo, hook_finale, rischi_incoerenza, 
               transizione_prossimo_capitolo, descrizione, background, parallelo, 
               obiettivi_personaggi, timeline_capitolo, timeline_opera
        FROM capitoli 
        WHERE id = ?
    """, (cid,)).fetchone()
    
    if row:
        print(f"\n=== METADATI CAPITOLO {row['id']}: {row['titolo']} ===")
        for key in row.keys():
            if key not in ['id', 'titolo']:
                print(f"[{key.upper()}]: {row[key]}")
    else:
        print(f"\n--- Capitolo {cid} non trovato nel DB ---")

conn.close()
