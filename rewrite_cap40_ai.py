import os
from llm_client import generate_chapter_text
from dotenv import load_dotenv

load_dotenv()

# Configurazione
CAPITOLO_IN = r'C:\Users\Raven\react\prima-vivi-poi-spieghi\capitoli\cap40.txt'
CAPITOLO_OUT = r'C:\Users\Raven\react\prima-vivi-poi-spieghi\capitoli\cap40_sanitized.txt'
MODEL_NAME = os.getenv("ADMIN_CHAT_MODEL", "llm.huihui-gemma-4-26b-a4b-it-abliterated")

def sanitize_chapter():
    with open(CAPITOLO_IN, 'r', encoding='utf-8', errors='ignore') as f:
        original_content = f.read()
    
    system_prompt = (
        "Sei un premiato autore di 'Dirty Realism' (Realismo Sporco). "
        "Il tuo stile è asciutto, crudo, privo di aggettivi superflui. "
        "Usi frasi brevi, verbi forti e ti concentri sulla realtà fisica: odori, freddo, stanchezza, fame.\n\n"
        "COMPITO:\n"
        "Riscrivi il capitolo fornito eliminando OGNI catena di aggettivi (massimo 1-2 per sostantivo). "
        "Elimina le ripetizioni di parole come 'roccioso', 'sordo', 'asfittico', 'asimmetrico' se usate come riempitivi.\n"
        "Mantieni la trama: Andriy, programmatore nel bunker a Kyiv nel 2022, resiste a un DDoS russo e scopre una frode interna, salvando i dati su una USB."
    )
    
    user_prompt = (
        "RISCRIVI IL SEGUENTE CAPITOLO IN STILE DIRTY REALISM:\n\n"
        f"{original_content}\n\n"
        "REGOLE RIGIDE:\n"
        "1. No liste di aggettivi.\n"
        "2. Frasi brevi.\n"
        "3. Focus sulle sensazioni fisiche di Andriy (Modafinil, occhi bruciati, freddo del server room).\n"
        "4. Lingua: Italiano."
    )
    
    print(f"Inizio riscrittura AI per cap40.txt...")
    try:
        sanitized_content = generate_chapter_text(
            prompt=user_prompt,
            provider="lmstudio",
            model=MODEL_NAME,
            api_key="",
            system=system_prompt,
            max_tokens=4000,
            temperature=0.5 # Più basso per maggiore coerenza
        )
        
        # Pulizia base (rimozione di tag AI se presenti)
        from llm_client import extract_narrative
        final_prose = extract_narrative(sanitized_content)
        
        with open(CAPITOLO_OUT, 'w', encoding='utf-8') as f_out:
            f_out.write(final_prose)
            
        print(f"Capitolo sanitizzato salvato in: {CAPITOLO_OUT}")
        return final_prose
    except Exception as e:
        print(f"Errore durante la riscrittura AI: {str(e)}")
        return None

if __name__ == "__main__":
    sanitize_chapter()
