import os

def search_files(directory, patterns):
    for root, dirs, files in os.walk(directory):
        if '.gemini' in root or '__pycache__' in root or '.git' in root:
            continue
        for file in files:
            if file.endswith(('.py', '.json', '.html', '.js', '.md', '.txt')):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        for i, line in enumerate(f, 1):
                            for p in patterns:
                                if p in line:
                                    print(f"{filepath}:{i}: {line.strip()}")
                except:
                    pass

if __name__ == "__main__":
    search_files('.', ['192.168.1.62', '8123', 'states'])
