import os
from llm_client import generate_chapter_text
from dotenv import load_dotenv

load_dotenv()

CAPITOLO_IN = r'C:\Users\Raven\react\prima-vivi-poi-spieghi\capitoli\cap40.txt'
CAPITOLO_OUT = r'C:\Users\Raven\react\prima-vivi-poi-spieghi\capitoli\cap40_solid.txt'
MODEL_NAME = os.getenv("ADMIN_CHAT_MODEL", "llm.huihui-gemma-4-26b-a4b-it-abliterated")

def rewrite_solid():
    with open(CAPITOLO_IN, 'r', encoding='utf-8', errors='ignore') as f:
        original_content = f.read()
    
    system_prompt = (
        "Sei un autore di Dirty Realism e un esperto di sistemi. "
        "Il tuo stile è CHIRURGICO. Niente metafore religiose (no cattedrali, no sacerdoti). "
        "Ti concentri sulla PERCEZIONE LIMITATA: Andriy è in un bunker, vede solo schermi. "
        "La guerra fuori è un dato che corrompe la rete, non una visione epica.\n\n"
        "DETTAGLI TECNICI DA RISPETTARE:\n"
        "- L'attacco DDoS è saturazione di pacchetti, non un 'impatto fisico'.\n"
        "- La scoperta della truffa deve essere un'ANOMALIA LOGICA (es. un reindirizzamento di pacchetti verso un gateway offshore con firma ministeriale durante il blackout).\n"
        "- No 'verde mela' o 'rosso scarlatto'. Usa termini da console (latency, dropping packets, unauthorized mirroring).\n"
        "- POV: Solo Andriy, 32 anni, imbottito di Modafinil."
    )
    
    user_prompt = (
        "RISCRIVI IL CAPITOLO 40 IN MODALITÀ 'SOLID' (DIRTY REALISM PURO):\n\n"
        f"{original_content}\n\n"
        "REGOLE:\n"
        "1. Elimina 'cattedrale', 'sacerdote', 'sordo', 'asimmetrico' (se usati a sproposito).\n"
        "2. Descrivi la scoperta della truffa come un'osservazione di un log tecnico specifico.\n"
        "3. Mantieni la tensione fisica: occhi secchi, dita che tremano, sapore di caffè bruciato.\n"
        "4. Lunghezza: Concentrata, asciutta."
    )
    
    print("Inizio riscrittura SOLID per cap40.txt...")
    try:
        sanitized_content = generate_chapter_text(
            prompt=user_prompt,
            provider="lmstudio",
            model=MODEL_NAME,
            api_key="",
            system=system_prompt,
            max_tokens=3000,
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
    rewrite_solid()
