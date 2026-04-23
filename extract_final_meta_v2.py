import sqlite3
import sys

# Forza l'output in utf-8 per evitare errori di encoding su Windows
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('roman.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

ids = [63, 64, 65, 66]
for cid in ids:
    row = cursor.execute("""
        SELECT id, titolo, pov, scene_outline, personaggi_capitolo, oggetti_simbolo, riassunto
        FROM capitoli 
        WHERE id = ?
    """, (cid,)).fetchone()
    
    if row:
        print(f"\n{'='*20} CAPITOLO {row['id']}: {row['titolo']} {'='*20}")
        print(f"POV: {row['pov']}")
        print(f"PERSONAGGI: {row['personaggi_capitolo']}")
        print(f"OGGETTI SIMBOLO: {row['oggetti_simbolo']}")
        print(f"RIASSUNTO: {row['riassunto']}")
        print(f"OUTLINE SCENE:\n{row['scene_outline']}")
    else:
        print(f"\n--- Capitolo {cid} non trovato ---")

conn.close()
