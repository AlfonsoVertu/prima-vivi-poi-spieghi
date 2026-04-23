import os
import glob
import re
from llm_client import generate_chapter_text
from dotenv import load_dotenv

load_dotenv()

def get_best_chapter_file(base_name, chapters_dir):
    """Cerca la versione migliore del capitolo (solid, sanitized, o originale)."""
    patterns = [
        f"{base_name}_solid.txt",
        f"{base_name}_sanitized.txt",
        f"{base_name}.txt"
    ]
    for p in patterns:
        path = os.path.join(chapters_dir, p)
        if os.path.exists(path):
            return path
    return None

def summarize_chapter(file_path, provider, model, api_key):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return f"ERRORE lettura file: {e}"
    
    # Se il file è troppo lungo, prendiamo una parte significativa per il riassunto
    # ma i capitoli dovrebbero stare nel contesto del modello (18k tokens)
    
    prompt = f"""
RIASSUNTO CAPITOLO:
Leggi il testo del capitolo qui sotto e scrivi un riassunto conciso (3-5 righe) in stile 'Dirty Realism' (crudo, diretto, essenziale).
Focalizzati sugli eventi chiave e sull'impatto sui personaggi. Evita introduzioni o conclusioni di cortesia.

TESTO DEL CAPITOLO:
{content[:15000]}  # Limite precauzionale
"""
    system = "Sei un editor esperto in realismo sporco. Il tuo compito è riassumere i capitoli in modo asciutto e brutale."
    
    try:
        summary = generate_chapter_text(prompt, provider, model, api_key, system=system, max_tokens=1000)
        # Pulizia base se l'AI include tag o chatter
        summary = summary.replace("<prose>", "").replace("</prose>", "").strip()
        return summary
    except Exception as e:
        return f"ERRORE nella generazione del riassunto: {e}"

def main():
    chapters_dir = r"C:\Users\Raven\react\prima-vivi-poi-spieghi\capitoli"
    output_file = r"C:\Users\Raven\react\prima-vivi-poi-spieghi\RIASSUNTO_OPERA.md"
    
    provider = os.getenv("LLM_PROVIDER", "lmstudio")
    model = os.getenv("ADMIN_CHAT_MODEL", "llm.huihui-gemma-4-26b-a4b-it-abliterated")
    api_key = os.getenv("LMSTUDIO_API_KEY", "")
    
    print(f"Provider: {provider}, Modello: {model}")

    with open(output_file, 'w', encoding='utf-8') as out:
        out.write("# RIASSUNTO CAPITOLO PER CAPITOLO - 'PRIMA VIVI POI SPIEGHI'\n\n")
        out.write("> Documento generato per il confronto con il Canone Definitivo.\n\n")
        
        for i in range(1, 67):
            base_name = f"cap{i:02d}"
            file_path = get_best_chapter_file(base_name, chapters_dir)
            
            if not file_path:
                print(f"Capitolo {i} non trovato.")
                continue
                
            print(f"Summarizing {os.path.basename(file_path)}...")
            summary = summarize_chapter(file_path, provider, model, api_key)
            
            out.write(f"## Capitolo {i}: {os.path.basename(file_path)}\n")
            out.write(f"{summary}\n\n")
            out.flush() # Assicura che il file venga scritto progressivamente
    
    print(f"\nOperazione completata. File salvato in: {output_file}")

if __name__ == "__main__":
    main()
