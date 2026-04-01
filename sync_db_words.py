import sqlite3
import os
import re

def sync_db(db_path, folder_path):
    if not os.path.exists(db_path):
        print(f"DB not found: {db_path}")
        return
    if not os.path.exists(folder_path):
        print(f"Folder not found: {folder_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    updates = 0
    for i in range(1, 67):
        filename = f"cap{i:02d}.txt"
        filepath = os.path.join(folder_path, filename)
        
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            words = len(re.findall(r'\w+', content))
            
            # Update word count
            cursor.execute("UPDATE capitoli SET parole = ? WHERE id = ?", (words, i))
            updates += 1
            
    conn.commit()
    conn.close()
    print(f"Updated {updates} chapters in {db_path}")

# Main Instance (Port 5000)
sync_db(r'c:\Users\Raven\react\ha-prima-vivi-poi-spieghi\prima_vivi_poi_spieghi\roman.db', 
        r'c:\Users\Raven\react\ha-prima-vivi-poi-spieghi\prima_vivi_poi_spieghi\capitoli')

# V2 Instance (Port 5001 - check both possible paths reported earlier)
v2_db = r'c:\Users\Raven\react\prima-vivi-poi-spieghi-v2\roman.db'
v2_folder = r'c:\Users\Raven\react\prima-vivi-poi-spieghi-v2\capitoli'
sync_db(v2_db, v2_folder)

v2_alt_db = r'c:\Users\Raven\react\prima-vivi-poi-spieghi\roman.db'
v2_alt_folder = r'c:\Users\Raven\react\prima-vivi-poi-spieghi\capitoli'
sync_db(v2_alt_db, v2_alt_folder)
