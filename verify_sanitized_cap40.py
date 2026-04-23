import os
import re
import json
import logging
from llm_client import generate_chapter_text
from dotenv import load_dotenv

load_dotenv()

# Configurazione
CAPITOLI_FOLDER = r'C:\Users\Raven\react\prima-vivi-poi-spieghi\capitoli'
CANONE_FILE = r'C:\Users\Raven\react\prima-vivi-poi-spieghi\CANONE_DEFINITIVO.md'
REPORT_FILE = r'C:\Users\Raven\react\prima-vivi-poi-spieghi\ai_audit_sanitized_report.md'

LMSTUDIO_URL = os.getenv("LMSTUDIO_URL", "http://192.168.1.51:1234")
MODEL_NAME = os.getenv("ADMIN_CHAT_MODEL", "llm.huihui-gemma-4-26b-a4b-it-abliterated")

def load_canone():
    with open(CANONE_FILE, 'r', encoding='utf-8') as f:
        return f.read()

def get_chapter_goal(canone, cap_id):
    pattern = rf"{cap_id}\.\s+(.*?)\s+—\s+\d+\s+pagine(.*?)(?=\n\d+\.|\Z)"
    match = re.search(pattern, canone, re.DOTALL)
    if match:
        return match.group(0).strip()
    return "Obiettivo non trovato nel canone."

def audit_chapter(cap_id, content, goal):
    system_prompt = (
        "Sei un editor senior esperto in 'Dirty Realism'. "
        "Il tuo compito è analizzare la versione RISCRITTA (sanitizzata) di un capitolo e verificare se i problemi precedenti (aggettivite, loop) sono stati risolti e se la coerenza è mantenuta."
    )
    
    user_prompt = (
        f"CAPITOLO RISCRITTO: {cap_id}\n"
        f"OBIETTIVO CANONICO: {goal}\n\n"
        f"TESTO RISCRITTO:\n---\n{content}\n---\n\n"
        "FORNISCI UN REPORT BREVE:\n"
        "1. INTEGRITÀ STILISTICA: (Punteggio 1-10 + commento su aggettivi/ritmo)\n"
        "2. COERENZA CANONICA: (Punteggio 1-10 + verifica POV e trama)\n"
        "3. ERRORI RESIDUI: (Es. errori di genere, typo, o loop rimasti)\n"
        "4. VERDETTO: (ECCELLENTE / OK / ANCORA DA PULIRE)"
    )
    
    try:
        response = generate_chapter_text(
            prompt=user_prompt,
            provider="lmstudio",
            model=MODEL_NAME,
            api_key="",
            system=system_prompt,
            max_tokens=1000
        )
        return response
    except Exception as e:
        return f"Errore durante l'audit AI: {str(e)}"

def main():
    canone = load_canone()
    targets = [40] # Per ora solo il 40 sanitized
    
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write("# REPORT VERIFICA CAPITOLI SANITIZZATI\n\n")
    
    for cap_id in targets:
        filename = f"cap{cap_id:02d}_sanitized.txt"
        filepath = os.path.join(CAPITOLI_FOLDER, filename)
        
        if not os.path.exists(filepath):
            print(f"File {filename} non trovato.")
            continue
            
        print(f"Inizio verifica AI per {filename}...")
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f_cap:
            content = f_cap.read()
            
        goal = get_chapter_goal(canone, cap_id)
        result = audit_chapter(cap_id, content, goal)
        
        with open(REPORT_FILE, 'a', encoding='utf-8') as f_rep:
            f_rep.write(f"## VERIFICA CAPITOLO {cap_id} (Sanitizzato)\n\n")
            f_rep.write(f"**Risultato:**\n\n{result}\n\n")
            f_rep.write("---\n\n")
        
        print(f"Completato audit per {filename}.")

if __name__ == "__main__":
    main()
