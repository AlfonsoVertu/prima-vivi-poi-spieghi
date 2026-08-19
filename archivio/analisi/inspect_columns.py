import sqlite3

conn = sqlite3.connect('roman.db')
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(capitoli)")
columns = cursor.fetchall()
for col in columns:
    print(col)
conn.close()
