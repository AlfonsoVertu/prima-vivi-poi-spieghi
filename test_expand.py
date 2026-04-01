import os
from dotenv import load_dotenv
from llm_client import call_openai

load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")

filepath = r"C:\Users\Raven\react\prima-vivi-poi-spieghi\capitoli\cap34.txt"
with open(filepath, "r", encoding="utf-8") as f:
    text = f.read()

prompt = f"Riscrivi ed espandi questo testo (almeno 1500 parole) in stile Dirty Realism crudo. RESTITUISCI SOLO IL TESTO NARRATIVO.\n\n[TESTO]\n" + text
sys_prompt = "Sei uno scrittore realista crudo."

print("Calling OpenAI...")
res = call_openai(prompt=prompt, api_key=API_KEY, model="gpt-4o", max_tokens=4000, system=sys_prompt)
print("\n--- OUTPUT FROM API ---")
print(res[:500] + "...\n(TRUNCATED)")
print(f"Total words out: {len(res.split())}")
