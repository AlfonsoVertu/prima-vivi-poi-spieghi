import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('roman.db')
conn.row_factory = sqlite3.Row
r = conn.execute('SELECT id, titolo, pov, riassunto, scene_outline FROM capitoli WHERE id = 64').fetchone()
if r:
    for k in r.keys():
        print(f"{k}: {r[k]}")
else:
    print("Capitolo 64 non trovato")
conn.close()
