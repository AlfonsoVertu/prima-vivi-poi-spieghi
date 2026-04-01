import sys

def search_file(filename, patterns):
    with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
        for i, line in enumerate(f, 1):
            for p in patterns:
                if p in line:
                    print(f"{i}: {line.strip()}")

if __name__ == "__main__":
    search_file('app.py', ['192.168.1.62', '8123', 'states'])
