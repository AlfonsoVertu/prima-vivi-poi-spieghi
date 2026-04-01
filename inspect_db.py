import sqlite3

def inspect_db():
    conn = sqlite3.connect('roman.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row['name'] for row in cursor.fetchall()]
    print(f"Tables: {tables}")
    
    for table in tables:
        print(f"\n--- {table} ---")
        try:
            cursor.execute(f"SELECT * FROM {table} LIMIT 5;")
            rows = cursor.fetchall()
            for row in rows:
                print(dict(row))
        except Exception as e:
            print(f"Error reading {table}: {e}")
            
    conn.close()

if __name__ == "__main__":
    inspect_db()
