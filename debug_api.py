"""Debug: mostra risposta raw dell'API per cap36.txt"""
import os
from dotenv import load_dotenv
import requests
import json

load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")

filepath = r"C:\Users\Raven\react\prima-vivi-poi-spieghi\capitoli\cap36.txt"
with open(filepath, "r", encoding="utf-8") as f:
    text = f.read()

print(f"Testo da espandere ({len(text.split())} parole):\n{text[:300]}\n---")

url = "https://api.openai.com/v1/chat/completions"
headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

payload = {
    "model": "gpt-4o",
    "max_tokens": 4096,
    "messages": [
        {"role": "system", "content": "Sei un romanziere italiano. Scrivi in prosa realista."},
        {"role": "user", "content": f"Espandi questo testo narrativo di un romanzo italiano a 2000 parole. Testo originale:\n\n{text}\n\nRispondi SOLO con il testo arricchito."}
    ],
    "temperature": 0.7
}

resp = requests.post(url, headers=headers, json=payload, timeout=120)
print(f"HTTP Status: {resp.status_code}")
data = resp.json()
print("FULL RESPONSE:")
print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
