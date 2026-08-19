import os
import re

folder = r'C:\Users\Raven\react\prima-vivi-poi-spieghi\capitoli'
corrupted_marker = "La densità narrativa di questo snodo"
markers_2 = ["infingardo", "asfissiante", "asettico", "marziale"]

report = []

for i in range(1, 67):
    filename = f"cap{i:02d}.txt"
    filepath = os.path.join(folder, filename)
    
    if not os.path.exists(filepath):
        report.append({"id": i, "status": "MISSING", "words": 0, "corrupted": False})
        continue
        
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        
    words = len(re.findall(r'\w+', content))
    is_corrupted = corrupted_marker in content
    
    # Check for excessive repetition of markers in long files
    marker_count = sum(content.lower().count(m) for m in markers_2)
    
    status = "OK"
    if words < 100:
        status = "EMPTY/PLACEHOLDER"
    elif is_corrupted:
        status = "CORRUPTED (LOOP)"
    elif words > 5000 and marker_count > 50:
         status = "CORRUPTED (STYLIZED)"
         
    report.append({"id": i, "status": status, "words": words, "filename": filename})

print(f"{'ID':<4} | {'Status':<25} | {'Words':<8} | {'Filename':<12}")
print("-" * 60)
for r in report:
    print(f"{r['id']:<4} | {r['status']:<25} | {r['words']:<8} | {r['filename']:<12}")
