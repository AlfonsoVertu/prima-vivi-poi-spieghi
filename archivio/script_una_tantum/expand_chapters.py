"""
Script di espansione capitoli fino a 200.000 parole totali.
Usa direttamente call_openai con max_tokens=4096 e senza extract_narrative
(che scartava testo valido).
"""
import os
import glob
from dotenv import load_dotenv
from llm_client import call_openai
import concurrent.futures

load_dotenv()

TARGET_WORDS = 200000
API_KEY = os.getenv("OPENAI_API_KEY")

SYSTEM = (
    "Sei un romanziere italiano specializzato nel 'Dirty Realism': stile crudo, logistico, sensoriale. "
    "Zero abbellimenti retorici. Zero metafisica. Solo azioni fisiche, odori acri, dolore freddo, burocrazia spietata."
)


def count_words(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return len(f.read().split())


def expand_file(filepath):
    fname = os.path.basename(filepath)
    with open(filepath, "r", encoding="utf-8") as f:
        original = f.read()

    orig_wc = len(original.split())
    
    prompt = (
        f"[TESTO ORIGINALE DEL CAPITOLO - {orig_wc} PAROLE]\n{original}\n\n"
        "[ISTRUZIONE]\n"
        "Riscrivi ed espandi questo capitolo portandolo ad almeno 2000 parole in italiano. "
        "Mantieni l'intestazione esatta. "
        "NON aggiungere colpi di scena nuovi, espandi invece: "
        "descrizioni di attese, rumori (metallo, nafta, vento), dialoghi spezzati, procedure fisiche dettagliate, "
        "dolore corpo, fatica muscolare, odori specifici. "
        "Rispondi SOLO con il testo del capitolo espanso, senza note o commenti."
    )

    try:
        result = call_openai(
            prompt=prompt,
            api_key=API_KEY,
            model="gpt-4o",
            max_tokens=4096,
            system=SYSTEM
        )
        new_wc = len(result.split())
        if new_wc < orig_wc:
            print(f"  [-] {fname}: risposta troppo corta ({new_wc} < {orig_wc}), salto.")
            return False
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(result)
        
        print(f"  [+] {fname}: {orig_wc} → {new_wc} parole (+{new_wc - orig_wc})")
        return True
    except Exception as e:
        print(f"  [!] {fname}: errore — {e}")
        return False


def main():
    cap_dir = r"C:\Users\Raven\react\prima-vivi-poi-spieghi\capitoli"
    all_files = sorted(glob.glob(os.path.join(cap_dir, "cap*.txt")))
    
    total = sum(count_words(f) for f in all_files)
    print(f"\n=== INIZIO === {total} / {TARGET_WORDS} parole")
    
    # Ordina per parole crescenti: i più corti vengono espansi per primi
    all_files_sorted = sorted(all_files, key=count_words)
    
    iteration = 0
    while total < TARGET_WORDS:
        iteration += 1
        remaining = TARGET_WORDS - total
        print(f"\n--- Iterazione {iteration} (mancano {remaining} parole) ---")
        
        # Prendi i 10 capitoli più brevi
        to_expand = all_files_sorted[:10]
        all_files_sorted = all_files_sorted[10:]  # li rimuove per non riprocessare ciclicamente
        
        if not to_expand:
            print("Nessun capitolo rimasto da espandere.")
            break
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(expand_file, f) for f in to_expand]
            concurrent.futures.wait(futures)
        
        total = sum(count_words(f) for f in all_files)
        print(f"  Totale aggiornato: {total} / {TARGET_WORDS}")
        
        # Ri-ordina per la prossima iterazione se necessario
        all_files_sorted = sorted(all_files, key=count_words)
        
        if iteration > 20:
            print("Limite iterazioni raggiunto.")
            break
    
    total = sum(count_words(f) for f in all_files)
    print(f"\n=== FINE === {total} / {TARGET_WORDS} parole.")
    if total >= TARGET_WORDS:
        print("✅ Target 200.000 parole RAGGIUNTO!")
    else:
        print(f"  Mancano ancora {TARGET_WORDS - total} parole.")


if __name__ == "__main__":
    main()
