import os
from llm_client import generate_chapter_text
from dotenv import load_dotenv

load_dotenv()

CAPITOLO_OUT = r'C:\Users\Raven\react\prima-vivi-poi-spieghi\capitoli\cap66_solid.txt'
MODEL_NAME = os.getenv("ADMIN_CHAT_MODEL", "llm.huihui-gemma-4-26b-a4b-it-abliterated")

def reconstruct_cap66():
    system_prompt = (
        "Sei un autore di Dirty Realism esperto. Il tuo stile è ESSENZIALE, CRUDO, MATERICO. "
        "Descrivi il mondo attraverso oggetti, odori e stanchezza fisica. Odia le astrazioni.\n\n"
        "CONTESTO NARRATIVO (Capitolo 66 - Quello che resta):\n"
        "- POV: Artem (anziano, anno 2050).\n"
        "- LUOGO: Anakara Arkana, una città-rifugio tra Tunisia e Libia.\n"
        "- TEMA: L'epilogo. La rete Arkana è diventata una realtà fisica. Non è un paradiso, è un porto per chi non ha posto nel mondo.\n"
        "- ATMOSFERA: Calore del deserto, polvere, rumore di desalinizzatori, odore di cibo comunitario. Un senso di stanchezza che ha trovato scopo.\n\n"
        "REGOLE:\n"
        "- No 'densità narrativa', no 'snodi rocciosi', no 'techno-lyrism'.\n"
        "- Descrivi Anakara Arkana come un cantiere infinito di lamiera, cemento e tubi, non come una visione futuristica.\n"
        "- La frase 'Prima vivi poi spieghi' deve essere la pietra angolare, ma pronunciata con la semplicità di un comando quotidiano."
    )
    
    user_prompt = (
        "SCRIVI IL CAPITOLO 66 (RICOSTRUZIONE SOLID):\n\n"
        "TRAMA:\n"
        "1. Artem cammina per le strade di Anakara Arkana nel 2050. Descrivi il calore che preme sulle spalle, il rumore costante dei macchinari che filtrano l'acqua.\n"
        "2. La città è un ammasso di moduli prefabbricati e tende permanenti. Mostra la gente: rifugiati che ora hanno una chiave in tasca.\n"
        "3. Artem vede un bambino (magari con un cucchiaio o che mangia del pane) e ricorda Lin, il Donbass, il Sinai.\n"
        "4. Riflessione finale sulla rete: Arkana non ha bandiere, ha solo persone che hanno scelto di restare vive.\n"
        "5. Chiusura: Artem si siede, guarda il tramonto sulla sabbia e pronuncia o pensa l'ultima volta: 'Prima vivi. Poi spieghi.' Il libro finisce qui."
    )
    
    print("Inizio ricostruzione SOLID per cap66.txt...")
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
            
        print(f"Capitolo 66 SOLID salvato in: {CAPITOLO_OUT}")
        return final_prose
    except Exception as e:
        print(f"Errore: {e}")
        return None

if __name__ == "__main__":
    reconstruct_cap66()
