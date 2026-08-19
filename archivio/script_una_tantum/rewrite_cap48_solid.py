import os
from llm_client import generate_chapter_text
from dotenv import load_dotenv

load_dotenv()

CAPITOLO_IN = r'C:\Users\Raven\react\prima-vivi-poi-spieghi\capitoli\cap48.txt'
CAPITOLO_OUT = r'C:\Users\Raven\react\prima-vivi-poi-spieghi\capitoli\cap48_solid.txt'
MODEL_NAME = os.getenv("ADMIN_CHAT_MODEL", "llm.huihui-gemma-4-26b-a4b-it-abliterated")

def rewrite_solid_cap48():
    with open(CAPITOLO_IN, 'r', encoding='utf-8', errors='ignore') as f:
        original_content = f.read()
    
    system_prompt = (
        "Sei un autore di Dirty Realism esperto in narrazioni di guerra e deserto. "
        "Il tuo stile è ESSENZIALE, MATERICO, CRUDO. "
        "Elimina categoricamente ogni catena di aggettivi (aggettivite). "
        "Usa frasi brevi. Sostituisci gli aggettivi con AZIONI o DETTAGLI FISICI.\n\n"
        "CONTESTO NARRATIVO:\n"
        "- POV: Liah (ex colona, ora fuggiasca con Omar).\n"
        "- AMBIENTE: Deserto di Giudea, caldo estremo, sete.\n"
        "- EVENTO: Incontro con profughi moribondi (iraniani/afghani) abbandonati.\n"
        "- TEMA: La 'trasformazione' di Liah da colona a essere umano che aiuta il 'nemico'.\n"
        "- RIFERIMENTO: Arkana / Neda (il network di salvataggio).\n\n"
        "REGOLE STILISTICHE:\n"
        "- No lirismo AI.\n"
        "- No ripetizioni di termini come 'fidente', 'sordo', 'asimmetrico', 'asfittico' se usati come riempitivi.\n"
        "- Il deserto deve essere calore che spacca la pelle, non una 'vampa sbiadita'."
    )
    
    user_prompt = (
        "RISCRIVI IL CAPITOLO 48 IN MODALITÀ 'SOLID' (DIRTY REALISM):\n\n"
        f"TESTO ORIGINALE (DA PURIFICARE):\n{original_content}\n\n"
        "REQUISITI:\n"
        "1. Mantieni la trama: Liah e Omar trovano i profughi, Omar vorrebbe ignorarli per sicurezza, Liah decide di aiutarli e dare l'acqua.\n"
        "2. Sfoltisci la massa verbale: il testo originale è di 4000+ parole sature, riducilo all'osso mantenendo l'intensità.\n"
        "3. La scoperta che i profughi sono stati salvati da 'Neda' (Arkana) è il punto di svolta morale.\n"
        "4. Finale: Liah e Omar ripartono verso l'acquedotto, assetati ma 'umani'."
    )
    
    print("Inizio riscrittura SOLID per cap48.txt...")
    try:
        sanitized_content = generate_chapter_text(
            prompt=user_prompt,
            provider="lmstudio",
            model=MODEL_NAME,
            api_key="",
            system=system_prompt,
            max_tokens=4000,
            temperature=0.3
        )
        
        from llm_client import extract_narrative
        final_prose = extract_narrative(sanitized_content)
        
        with open(CAPITOLO_OUT, 'w', encoding='utf-8') as f_out:
            f_out.write(final_prose)
            
        print(f"Capitolo SOLID salvato in: {CAPITOLO_OUT}")
        return final_prose
    except Exception as e:
        print(f"Errore: {e}")
        return None

if __name__ == "__main__":
    rewrite_solid_cap48()
