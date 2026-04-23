import os
from llm_client import generate_chapter_text
from dotenv import load_dotenv

load_dotenv()

CAPITOLO_IN = r'C:\Users\Raven\react\prima-vivi-poi-spieghi\capitoli\cap48.txt'
CAPITOLO_OUT = r'C:\Users\Raven\react\prima-vivi-poi-spieghi\capitoli\cap48_solid.txt'
MODEL_NAME = os.getenv("ADMIN_CHAT_MODEL", "llm.huihui-gemma-4-26b-a4b-it-abliterated")

def rewrite_solid_v2_cap48():
    with open(CAPITOLO_IN, 'r', encoding='utf-8', errors='ignore') as f:
        original_content = f.read()
    
    system_prompt = (
        "Sei un autore di Dirty Realism estremo (stile McCarthy/Bukowski). "
        "La tua scrittura deve essere SPORCA, FISICA, SENZA PIETÀ. "
        "Odia le metafore astratte. Se una cosa è brutta, descrivi l'odore e la consistenza, non chiamarla 'brutale' o 'rito'.\n\n"
        "VINCOLI DI RISCRITTURA:\n"
        "- No 'ossidazioni', no 'riti', no 'chirurgia' figurata.\n"
        "- L'acqua sa di plastica e metallo.\n"
        "- Il deserto è calcare che riflette il sole e brucia la retina.\n"
        "- Lo zaino è una zavorra di tela sporca, non un concetto pesante.\n"
        "- Il network di Arkana/Neda è un fatto tecnico: un segno sulla pelle, un foglio di identità falso."
    )
    
    user_prompt = (
        "RISCRIVI IL CAPITOLO 48 (VERSIONE SOLID 2.0):\n\n"
        f"TESTO DA PULIRE:\n{original_content[:10000]}\n\n" # Prendiamo i primi 10k caratteri per contesto
        "OBIETTIVI:\n"
        "1. Liah e Omar nel deserto. Il caldo è un peso fisico.\n"
        "2. Trovano i profughi: descrivi la loro agonia con dettagli biologici (occhi incrostati, fiato corto, puzza di sudore vecchio).\n"
        "3. Omar vuole scappare per salvarsi. Liah si impone.\n"
        "4. La connessione con Neda: un dettaglio fisico (es. un braccialetto o un documento Arkana).\n"
        "5. Dai loro l'acqua: deve essere un gesto di sopravvivenza, non una cerimonia."
    )
    
    print("Inizio riscrittura SOLID v2 per cap48.txt...")
    try:
        sanitized_content = generate_chapter_text(
            prompt=user_prompt,
            provider="lmstudio",
            model=MODEL_NAME,
            api_key="",
            system=system_prompt,
            max_tokens=3000,
            temperature=0.4
        )
        
        from llm_client import extract_narrative
        final_prose = extract_narrative(sanitized_content)
        
        with open(CAPITOLO_OUT, 'w', encoding='utf-8') as f_out:
            f_out.write(final_prose)
            
        print(f"Capitolo SOLID v2 salvato in: {CAPITOLO_OUT}")
        return final_prose
    except Exception as e:
        print(f"Errore: {e}")
        return None

if __name__ == "__main__":
    rewrite_solid_v2_cap48()
