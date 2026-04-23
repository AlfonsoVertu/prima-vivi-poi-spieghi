import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('roman.db')
conn.row_factory = sqlite3.Row
r = conn.execute('SELECT id, titolo, pov, riassunto, scene_outline, personaggi_capitolo, oggetti_simbolo FROM capitoli WHERE id = 66').fetchone()
if r:
    for k in r.keys():
        print(f"{k.upper()}: {r[k]}")
else:
    print("Capitolo 66 non trovato")
conn.close()
