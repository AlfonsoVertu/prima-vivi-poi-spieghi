import os
from llm_client import generate_chapter_text
from dotenv import load_dotenv

load_dotenv()

CAPITOLO_OUT = r'C:\Users\Raven\react\prima-vivi-poi-spieghi\capitoli\cap63_solid.txt'
MODEL_NAME = os.getenv("ADMIN_CHAT_MODEL", "llm.huihui-gemma-4-26b-a4b-it-abliterated")

def reconstruct_cap63():
    system_prompt = (
        "Sei un autore di Dirty Realism esperto. Il tuo stile è ESSENZIALE, CRUDO, FISICO. "
        "Odia le astrazioni. Descrivi oggetti, odori, freddo, stanchezza.\n\n"
        "CONTESTO NARRATIVO (Capitolo 63 - Finale):\n"
        "- POV: Artem.\n"
        "- LUOGO: Maryland, USA. La casa di Lin.\n"
        "- TEMPO: Dopo gli eventi del Sinai.\n"
        "- TEMA: Il ritorno. Artem incontra la vedova di Lin (Elena). Le consegna ciò che resta (il cucchiaio, i dati, il debito pagato).\n"
        "- ATMOSFERA: Silenzio, ordine americano che stride con la violenza del deserto, senso di chiusura di un cerchio.\n\n"
        "REGOLE:\n"
        "- No 'densità narrativa', no 'snodi rocciosi' (termini vietati del loop).\n"
        "- La frase 'Prima vivi poi spieghi' deve apparire nel finale come un respiro pesante, non come un proclama."
    )
    
    user_prompt = (
        "SCRIVI IL CAPITOLO 63 (RICOSTRUZIONE SOLID):\n\n"
        "TRAMA:\n"
        "1. Artem arriva alla casa di Lin nel Maryland. Descrivi il quartiere troppo pulito, l'erba tagliata, il silenzio suburbano.\n"
        "2. Incontro con Elena (la moglie di Lin). Lei sa già tutto, ma il silenzio tra loro è pesante.\n"
        "3. Artem le consegna un oggetto fisico di Lin (il cucchiaio o un altro ricordo del Sinai).\n"
        "4. Artem realizza che la sua vita è ormai legata alla rete Arkana: non può restare nel Maryland.\n"
        "5. Finale: Artem guarda la casa e capisce che Lin è morto perché lui potesse essere lì, ma ora lui deve andare dove le persone stanno ancora cercando di restare vive."
    )
    
    print("Inizio ricostruzione SOLID per cap63.txt...")
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
            
        print(f"Capitolo 63 SOLID salvato in: {CAPITOLO_OUT}")
        return final_prose
    except Exception as e:
        print(f"Errore: {e}")
        return None

if __name__ == "__main__":
    reconstruct_cap63()
