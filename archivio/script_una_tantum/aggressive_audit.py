import os
import re
from llm_client import generate_chapter_text
from dotenv import load_dotenv

load_dotenv()

CAPITOLO_SAN = r'C:\Users\Raven\react\prima-vivi-poi-spieghi\capitoli\cap66_solid.txt'
CANONE_FILE = r'C:\Users\Raven\react\prima-vivi-poi-spieghi\CANONE_DEFINITIVO.md'
REPORT_FILE = r'C:\Users\Raven\react\prima-vivi-poi-spieghi\aggressive_audit_report_cap66.md'

MODEL_NAME = os.getenv("ADMIN_CHAT_MODEL", "llm.huihui-gemma-4-26b-a4b-it-abliterated")

def aggressive_audit():
    with open(CAPITOLO_SAN, 'r', encoding='utf-8') as f:
        content = f.read()
    with open(CANONE_FILE, 'r', encoding='utf-8') as f:
        canone = f.read()

    system_prompt = (
        "Sei un CRITICO LETTERARIO SPIETATO e un esperto di CYBER-SECURITY. "
        "Il tuo obiettivo è DISTRUGGERE la coerenza di questo capitolo. "
        "Non fare complimenti. Cerca il pelo nell'uovo.\n\n"
        "PARAMETRI DI ATTACCO:\n"
        "1. INCOERENZA CANONICA: Il testo contraddice il Canone Definitivo?\n"
        "2. FALLIMENTO STILISTICO: Ci sono ancora tracce di lirismo AI o termini 'finti' (es. 'cattedrale')?\n"
        "3. IMPOSSIBILITÀ TECNICA: Quello che Andriy fa con i server ha senso o è magia informatica?\n"
        "4. GENDER/CHARACTER LEAK: Andriy agisce e parla come un uomo di 32 anni sotto pressione o sembra un bot?"
    )

    user_prompt = (
        "ANALISI AVVERSARIALE DEL CAPITOLO 40 SANITIZZATO.\n\n"
        f"CANONE DI RIFERIMENTO:\n{canone[:5000]}\n\n" # Limitiamo al blocco rilevante per contesto
        f"TESTO DA ATTACCARE:\n{content}\n\n"
        "FORNISCI IL REPORT 'BLACK HAT':\n"
        "- ELENCO ERRORI LOGICI:\n"
        "- ELENCO TERMINI NON DIRTY REALISM:\n"
        "- CONTRADDIZIONI COL CANONE:\n"
        "- VERDETTO: (FALLIMENTO / ACCETTABILE CON MODIFICHE / SOLIDO)"
    )

    print("Avvio Audit Aggressivo (Modalità Black Hat)...")
    try:
        response = generate_chapter_text(
            prompt=user_prompt,
            provider="lmstudio",
            model=MODEL_NAME,
            api_key="",
            system=system_prompt,
            max_tokens=1500
        )
        
        with open(REPORT_FILE, 'w', encoding='utf-8') as f_rep:
            f_rep.write("# REPORT AUDIT AGGRESSIVO (MODALITÀ DISTRUTTIVA)\n\n")
            f_rep.write(response)
            
        print(f"Audit completato. Report: {REPORT_FILE}")
        return response
    except Exception as e:
        print(f"Errore: {e}")
        return None

if __name__ == "__main__":
    aggressive_audit()
