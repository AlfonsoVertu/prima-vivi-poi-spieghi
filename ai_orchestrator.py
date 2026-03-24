import json
import re
import concurrent.futures
from llm_client import generate_chapter_text

MAX_ITERATIONS = 3  # Massimo numero di cicli di ricerca prima di rispondere

# Pool di messaggi provvisori narrativi mentre gli agenti continuano a cercare
_PROVISIONAL_READER = [
    "L'Archivio è vasto... ho trovato alcune tracce ma ne cerco conferma. Un momento ancora.",
    "I ricordi si sovrappongono. Sto scavando più in profondità per essere certa.",
    "Qualcosa sfugge alla prima lettura. L'Archivio rivela i suoi segreti con cautela.",
]
_PROVISIONAL_ADMIN = [
    "Ho dati parziali. Sto approfondendo prima di rispondere con precisione.",
    "Alcune informazioni sono ancora da verificare. Riprendo la ricerca.",
    "Il Canone è ampio — sto incrociando le fonti per una risposta coerente.",
]
def _extract_json_dati(text):
    """Estrae stabilmente la chiave 'dati' da una stringa presunta JSON generata da un LLM chiacchierone."""
    clean = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
    match = re.search(r'\{.*\}', clean, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            return str(data.get("dati", clean))
        except:
            pass
    return clean

def _provisional_msg(admin_mode, idx):
    pool = _PROVISIONAL_ADMIN if admin_mode else _PROVISIONAL_READER
    return pool[idx % len(pool)]


def _run_agents_parallel(provider, model_name, api_key, sys_instr, prompts,
                         meta_table, summaries_text, deep_text, user_msg, extra_query=""):
    """Esegue i 3 sub-agent in parallelo e restituisce i risultati."""

    def call_architetto():
        prompt = prompts.get("chat_step1_metadata_prompt", "Analizza metadati.")
        content = prompt.replace("{{metadata_table}}", meta_table).replace("{{user_msg}}", user_msg)
        if extra_query:
            content += f"\n\n[APPROFONDIMENTO RICHIESTO]\n{extra_query}"
        hist = [{"role": "system", "content": sys_instr}, {"role": "user", "content": content}]
        return ("architetto", _extract_json_dati(generate_chapter_text("", provider, model_name, api_key, max_tokens=600, messages=hist)))

    def call_storico():
        prompt = prompts.get("chat_step2_summaries_prompt", "Analizza riassunti.")
        content = prompt.replace("{{summaries_text}}", summaries_text).replace("{{user_msg}}", user_msg)
        if extra_query:
            content += f"\n\n[APPROFONDIMENTO RICHIESTO]\n{extra_query}"
        hist = [{"role": "system", "content": sys_instr}, {"role": "user", "content": content}]
        return ("storico", _extract_json_dati(generate_chapter_text("", provider, model_name, api_key, max_tokens=800, messages=hist)))

    def call_lettore():
        prompt = prompts.get("chat_step3_deep_text_prompt", "Analizza testo profondo.")
        content = prompt.replace("{{deep_text}}", deep_text).replace("{{user_msg}}", user_msg)
        if extra_query:
            content += f"\n\n[APPROFONDIMENTO RICHIESTO]\n{extra_query}"
        hist = [{"role": "system", "content": sys_instr}, {"role": "user", "content": content}]
        return ("lettore", _extract_json_dati(generate_chapter_text("", provider, model_name, api_key, max_tokens=800, messages=hist)))

    AGENT_ICONS = {"architetto": "🗺️", "storico": "📜", "lettore": "📖"}
    results = {}
    sse_updates = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(call_architetto): "architetto",
            executor.submit(call_storico): "storico",
            executor.submit(call_lettore): "lettore",
        }
        for fut in concurrent.futures.as_completed(futures):
            name, result = fut.result()
            results[name] = result
            label = f"{AGENT_ICONS[name]} {name.capitalize()}: completato."
            sse_updates.append(label)

    return results, sse_updates


EVAL_PROMPT_TEMPLATE = """Sei l'Orchestratore. Hai ricevuto i rapporti dai sub-agenti.

[DOMANDA UTENTE]
{user_msg}

[DOSSIER AGENTI]
{dossier}

[ITERAZIONE CORRENTE]
{iteration} di {max_iter}

Valuta:
1. Hai abbastanza informazioni verificate e coerenti per rispondere alla domanda?
2. Se no, dì esattamente cosa manca.

Rispondi OBBLIGATORIAMENTE in questo formato (solo una delle due opzioni):

SUFFICIENTE: <breve risposta provvisoria da mostrare all'utente mentre viene formulata la risposta>

oppure:

APPROFONDIRE: <messaggio provvisorio breve per l'utente> | <query specifica da dare agli agenti per la prossima ricerca>
"""


def run_orchestrator_stream(
    cap_id, provider, model_name, api_key, user_msg, admin_mode, prompts,
    f_get_all, f_get_full_canon, f_get_conn, f_read_txt, f_get_character_context
):
    """
    Orchestratore iterativo con loop di valutazione e feedback continuo all'utente.
    """

    # ── FASE 0: AVVIO ─────────────────────────────────────────────────
    yield f"data: {json.dumps({'stage': 'context', 'content': '🌀 Orchestratore attivo — avvio ricerca...'})}\n\n"

    caps = f_get_all()

    sys_instr = prompts.get("system_instruction", "")
    if not admin_mode:
        sys_instr += (
            f"\n\n[[POLITICA_LETTORE]]:\n"
            f"Il lettore è fermo al Capitolo {cap_id}. È vietato usare conoscenza da capitoli futuri o dal canone globale."
        )
    else:
        canon = f_get_full_canon()
        sys_instr += f"\n\n[[CANONE_DEFINITIVO]]:\n{canon}"

    meta_table = "### STRUTTURA OPERA (ToC)\n"
    for c in caps:
        if not admin_mode and c['id'] > cap_id:
            meta_table += f"Cap {c['id']}: [IGNOTO - FUTURO]\n"
        else:
            meta_table += f"Cap {c['id']}: {c['titolo']} ({c['pov']})\n"

    relevant_summaries = [
        f"Cap {c['id']}: {c.get('riassunto', '')}"
        for c in caps
        if (not admin_mode and c['id'] <= cap_id) or admin_mode
    ]
    summaries_text = "\n".join(relevant_summaries[-30:])

    prev_cap = f_read_txt(cap_id - 1) if cap_id > 1 else ""
    curr_cap = f_read_txt(cap_id)
    deep_text = (
        f"CAPITOLO {cap_id-1}:\n{prev_cap[-1500:]}\n\nCAPITOLO {cap_id}:\n{curr_cap[:2000]}"
        if admin_mode
        else f"CAPITOLO CORRENTE {cap_id}:\n{curr_cap[:2500]}"
    )

    # ── LOOP ITERATIVO ─────────────────────────────────────────────────
    all_results = {}
    extra_query = ""
    orchestrator_decision = ""
    sufficient = False

    for iteration in range(1, MAX_ITERATIONS + 1):
        iter_label = f"Ciclo {iteration}/{MAX_ITERATIONS}"
        yield f"data: {json.dumps({'stage': 'context', 'content': f'🔍 {iter_label}: Agenti in ricerca parallela...'})}\n\n"

        # Esegui agenti in parallelo
        results, sse_updates = _run_agents_parallel(
            provider, model_name, api_key, sys_instr, prompts,
            meta_table, summaries_text, deep_text, user_msg, extra_query
        )

        # Aggiorna dossier cumulativo
        for k, v in results.items():
            if k not in all_results:
                all_results[k] = v
            else:
                all_results[k] += f"\n\n[APPROFONDIMENTO {iteration}]\n{v}"

        # Yield aggiornamenti agenti
        for upd in sse_updates:
            yield f"data: {json.dumps({'stage': 'context', 'content': upd})}\n\n"

        # ── VALUTAZIONE ORCHESTRATORE ──────────────────────────────────
        yield f"data: {json.dumps({'stage': 'context', 'content': f'⚙️ {iter_label}: Valutazione del dossier...'})}\n\n"

        dossier = (
            f"[RAPPORTO ARCHITETTO]\n{all_results.get('architetto', 'N/A')}\n\n"
            f"[RAPPORTO STORICO]\n{all_results.get('storico', 'N/A')}\n\n"
            f"[RAPPORTO LETTORE]\n{all_results.get('lettore', 'N/A')}"
        )

        eval_prompt = EVAL_PROMPT_TEMPLATE.format(
            user_msg=user_msg,
            dossier=dossier,
            iteration=iteration,
            max_iter=MAX_ITERATIONS
        )
        eval_hist = [{"role": "system", "content": sys_instr}, {"role": "user", "content": eval_prompt}]
        eval_response = generate_chapter_text("", provider, model_name, api_key, max_tokens=400, messages=eval_hist)

        # ── PARSING RISPOSTA ORCHESTRATORE ────────────────────────────
        eval_clean = re.sub(r'<think>.*?</think>', '', eval_response, flags=re.DOTALL | re.IGNORECASE).strip()
        eval_json_match = re.search(r'\{.*\}', eval_clean, re.DOTALL)
        
        status = ""
        orchestrator_data = {}
        if eval_json_match:
            try:
                orchestrator_data = json.loads(eval_json_match.group(0))
                status = str(orchestrator_data.get("status", "")).upper()
            except:
                pass
                
        if not status:
            if "SUFFICIENTE" in eval_clean.upper(): status = "SUFFICIENTE"
            elif "APPROFONDIRE" in eval_clean.upper(): status = "APPROFONDIRE"

        if status.startswith("SUFFICIENTE"):
            orchestrator_decision = orchestrator_data.get("dossier_finale_per_agente_sintesi", dossier) if orchestrator_data else dossier
            sufficient = True
            yield f"data: {json.dumps({'stage': 'context', 'content': '✅ Informazioni sufficienti. Elaboro la risposta...'})}\n\n"
            break

        elif "APPROFONDIRE" in status:
            draft_msg = orchestrator_data.get("draft_risposta_o_direttiva", "") if orchestrator_data else ""
            if "|" in draft_msg:
                parts = draft_msg.split("|", 1)
                provisional_user_msg = parts[0].strip()
                extra_query = parts[1].strip()
            else:
                parts = eval_clean.split(":", 1)[-1].strip().split("|")
                provisional_user_msg = parts[0].strip() if parts else _provisional_msg(admin_mode, iteration - 1)
                extra_query = parts[1].strip() if len(parts) > 1 else ""

            yield f"data: {json.dumps({'stage': 'synthesis', 'content': provisional_user_msg})}\n\n"
            yield f"data: {json.dumps({'stage': 'synthesis', 'content': ' ...'})}\n\n"

            if iteration == MAX_ITERATIONS:
                orchestrator_decision = orchestrator_data.get("dossier_finale_per_agente_sintesi", dossier) if orchestrator_data else dossier
                sufficient = True
                yield f"data: {json.dumps({'stage': 'context', 'content': '🔚 Massimo cicli raggiunto. Sintetizzo con i dati disponibili...'})}\n\n"
        else:
            orchestrator_decision = orchestrator_data.get("dossier_finale_per_agente_sintesi", dossier) if orchestrator_data else dossier
            sufficient = True
            break

    # ── FASE FINALE: SINTESI ───────────────────────────────────────────
    if not orchestrator_decision:
        orchestrator_decision = dossier if 'dossier' in dir() else ""

    s_prompt = prompts.get("chat_step5_synthesis_prompt", "Rispondi.")
    s_prompt_filled = s_prompt.replace("{{reasoning_plan}}", orchestrator_decision[:4000]).replace("{{user_msg}}", user_msg)
    
    # FORZATURA ESTREMA ALLA FINE DELLA RISPOSTA (per GLM-4 e simili)
    s_prompt_filled += "\n\n[ULTIMO ORDINE: Inizia a scrivere DIRETTAMENTE la risposta finale in italiano, assumendo il tuo ruolo (Guida o Assistente). NON scrivere NESSUN PREAMBOLO IN INGLESE, nessun 'Got it', e NON usare tag strutturali come <|begin_of_box|>.]"
    
    s_hist = [{"role": "system", "content": sys_instr}, {"role": "user", "content": s_prompt_filled}]

    in_think = False
    if provider == "lmstudio":
        for chunk in generate_chapter_text("", provider, model_name, api_key, max_tokens=2000, messages=s_hist, stream=True):
            processed_chunk = chunk
            processed_chunk = processed_chunk.replace("<|begin_of_box|>", "").replace("<|end_of_box|>", "")
            
            if "<think>" in chunk.lower() or in_think:
                in_think = True
                if "</think>" in chunk.lower():
                    processed_chunk = re.sub(r'^.*?</think>', '', chunk, flags=re.DOTALL | re.IGNORECASE)
                    in_think = False
                else:
                    processed_chunk = ""
            if processed_chunk:
                yield f"data: {json.dumps({'stage': 'synthesis', 'content': processed_chunk})}\n\n"
    else:
        reply = generate_chapter_text("", provider, model_name, api_key, max_tokens=2000, messages=s_hist)
        clean_reply = re.sub(r'<think>.*?</think>', '', reply, flags=re.DOTALL | re.IGNORECASE).strip()
        clean_reply = clean_reply.replace("<|begin_of_box|>", "").replace("<|end_of_box|>", "")
        yield f"data: {json.dumps({'stage': 'synthesis', 'content': clean_reply})}\n\n"

    yield "data: [DONE]\n\n"
