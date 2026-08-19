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
REPORT_FILE = r'C:\Users\Raven\react\prima-vivi-poi-spieghi\ai_audit_report.md'

LMSTUDIO_URL = os.getenv("LMSTUDIO_URL", "http://192.168.1.51:1234")
MODEL_NAME = os.getenv("ADMIN_CHAT_MODEL", "llm.huihui-gemma-4-26b-a4b-it-abliterated")

def load_canone():
    with open(CANONE_FILE, 'r', encoding='utf-8') as f:
        return f.read()

def get_chapter_goal(canone, cap_id):
    # Cerca nel canone la riga corrispondente al capitolo
    pattern = rf"{cap_id}\.\s+(.*?)\s+—\s+\d+\s+pagine(.*?)(?=\n\d+\.|\Z)"
    match = re.search(pattern, canone, re.DOTALL)
    if match:
        return match.group(0).strip()
    return "Obiettivo non trovato nel canone."

def audit_chapter(cap_id, content, goal):
    system_prompt = (
        "Sei un editor senior esperto in 'Dirty Realism' (realismo sporco). "
        "Il tuo compito è analizzare un capitolo di un romanzo e verificare se rispetta i canoni stilistici e narrativi stabiliti.\n\n"
        "REGOLE STILISTICHE:\n"
        "1. Realismo Sporco: Prosa asciutta, cruda, diretta. Niente fronzoli, niente catene infinite di aggettivi.\n"
        "2. No Aggettivite: Se vedi frasi con più di 3-4 aggettivi consecutivi (es. 'roccioso sordo asfittico sterrato'), è un errore grave di AI collapse.\n"
        "3. POV Coerente: Il romanzo è in prima persona. Verifica che non ci siano infiltrazioni di un narratore onnisciente o POV collettivi ('Noi').\n"
        "4. Coerenza Canonica: Verifica che il contenuto rispetti l'obiettivo del capitolo definito nel canone."
    )
    
    user_prompt = (
        f"CAPITOLO DA ANALIZZARE: {cap_id}\n"
        f"OBIETTIVO CANONICO: {goal}\n\n"
        f"TESTO DEL CAPITOLO:\n---\n{content[:8000]}\n---\n\n"
        "FORNISCI UN REPORT BREVE E STRUTTURATO:\n"
        "1. INTEGRITÀ STILISTICA: (Voto 1-10 + commento su aggettivi/ripetizioni)\n"
        "2. COERENZA CANONICA: (Voto 1-10 + commento su trama/POV)\n"
        "3. PROBLEMI CRITICI: (Elenca eventuali loop o anacronismi)\n"
        "4. VERDETTO: (OK / DA RISCRIVERE / DA PULIRE)"
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
    
    # Seleziona un subset di capitoli critici per iniziare, o tutti se preferito.
    # Il cliente ha chiesto di verificare i capitoli, iniziamo con quelli segnalati come critici
    # e poi procediamo. Per ora, facciamo una scansione di test su 40, 48, 63, 65, 66.
    targets = [40, 48, 63, 65, 66] 
    
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write("# REPORT AUDIT AI LOCALE (Gemma-4)\n\n")
    
    for cap_id in targets:
        filename = f"cap{cap_id:02d}.txt"
        filepath = os.path.join(CAPITOLI_FOLDER, filename)
        
        if not os.path.exists(filepath):
            print(f"Capitolo {cap_id} non trovato.")
            continue
            
        print(f"Inizio audit AI per {filename}...")
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f_cap:
            content = f_cap.read()
            
        goal = get_chapter_goal(canone, cap_id)
        result = audit_chapter(cap_id, content, goal)
        
        with open(REPORT_FILE, 'a', encoding='utf-8') as f_rep:
            f_rep.write(f"## CAPITOLO {cap_id}: {filename}\n\n")
            f_rep.write(f"**Obiettivo Canonico:** {goal}\n\n")
            f_rep.write(f"**Risultato Audit AI:**\n\n{result}\n\n")
            f_rep.write("---\n\n")
        
        print(f"Completato audit per {filename}.")

if __name__ == "__main__":
    main()
