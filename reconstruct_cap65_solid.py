import os
from llm_client import generate_chapter_text
from dotenv import load_dotenv

load_dotenv()

CAPITOLO_OUT = r'C:\Users\Raven\react\prima-vivi-poi-spieghi\capitoli\cap65_solid.txt'
MODEL_NAME = os.getenv("ADMIN_CHAT_MODEL", "llm.huihui-gemma-4-26b-a4b-it-abliterated")

def reconstruct_cap65():
    system_prompt = (
        "Sei un autore di Dirty Realism esperto. Il tuo stile è ESSENZIALE, CRUDO, LOGISTICO. "
        "Descrivi il mondo attraverso cavi, schermi, rumore di ventole e codici binari che diventano carne.\n\n"
        "CONTESTO NARRATIVO (Capitolo 65 - Primo corridoio):\n"
        "- POV: Artem.\n"
        "- LUOGO: Ginevra / Uffici ONU (notte).\n"
        "- TEMA: La nascita di Arkana come sistema. Artem sta 'rubando' risorse e dati per creare il primo corridoio di salvataggio.\n"
        "- ATMOSFERA: Tensione tecnica. Il tradimento morale verso le istituzioni ufficiali a favore di una verità umana più profonda.\n\n"
        "REGOLE:\n"
        "- No 'densità narrativa', no 'snodi rocciosi'.\n"
        "- Arkana non è una ONG; è un'operazione di intelligence civile deviata."
    )
    
    user_prompt = (
        "SCRIVI IL CAPITOLO 65 (RICOSTRUZIONE SOLID):\n\n"
        "TRAMA:\n"
        "1. Artem è in una stanza server o un ufficio buio a Ginevra. Descrivi il ronzio delle macchine, l'odore di ozono, la luce blu dei monitor.\n"
        "2. Sta eseguendo un trasferimento di fondi o la creazione di identità digitali 'fantasma'. Spiega come i soldi della NATO o dell'ONU finiscono per pagare il pane e l'acqua nel deserto.\n"
        "3. Riflessione su Lin: Lin è morto per salvare lui, ora lui usa la sua posizione per salvare migliaia di 'Artem' anonimi.\n"
        "4. Nasce il 'Primo Corridoio': un volo illegale, un camion in transito, una porta che si apre nel Sinai.\n"
        "5. Finale: Artem preme 'Enter' e capisce che ha appena iniziato una guerra invisibile contro i confini del mondo."
    )
    
    print("Inizio ricostruzione SOLID per cap65.txt...")
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
            
        print(f"Capitolo 65 SOLID salvato in: {CAPITOLO_OUT}")
        return final_prose
    except Exception as e:
        print(f"Errore: {e}")
        return None

if __name__ == "__main__":
    reconstruct_cap65()
