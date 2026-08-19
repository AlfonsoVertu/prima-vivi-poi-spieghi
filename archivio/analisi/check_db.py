import sqlite3
import os

def check_db():
    if not os.path.exists('roman.db'):
        print("Database non trovato.")
        return
    
    conn = sqlite3.connect('roman.db')
    cursor = conn.cursor()
    
    # Prendi tutte le tabelle
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cursor.fetchall()]
    
    for table in tables:
        try:
            cursor.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            for row in rows:
                if '192.168.1.62' in str(row):
                    print(f"Trovato in tabella '{table}': {row}")
        except Exception as e:
            print(f"Errore su tabella {table}: {e}")
    
    conn.close()

if __name__ == "__main__":
    check_db()
