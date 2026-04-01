"""
app.py — Server Flask per visualizzare e modificare capitoli e metadati
Avvio: python app.py  →  http://localhost:5000
"""
from flask import Flask, render_template_string, request, redirect, url_for, jsonify, send_file, session
import sqlite3, os, json, io, zipfile, logging, re
import time
import hashlib
from functools import wraps
from dotenv import load_dotenv

import ai_queue
import llm_client
from agent_registry import ensure_schema as ensure_agent_registry_schema, list_agents as registry_list_agents, list_endpoints as registry_list_endpoints, seed_defaults as registry_seed_defaults, resolve_agent_for_role as registry_resolve_agent_for_role, upsert_agent as registry_upsert_agent, upsert_provider_endpoint as registry_upsert_provider_endpoint, get_agent as registry_get_agent, get_endpoint as registry_get_endpoint, set_agent_enabled as registry_set_agent_enabled, delete_agent as registry_delete_agent, delete_provider_endpoint as registry_delete_provider_endpoint, validate_agent_configuration as registry_validate_agent_configuration, export_registry_bundle as registry_export_bundle, import_registry_bundle as registry_import_bundle, upsert_discovery_cache as registry_upsert_discovery_cache, get_discovery_cache as registry_get_discovery_cache, readiness_report as registry_readiness_report
from provider_discovery import discover_models as provider_discover_models, test_provider as provider_test_provider
from chat_memory import upsert_session_memory, load_session_memory
from spoiler_guard import enforce_reader_safety
from chat_tools import execute_tool as chat_execute_tool, available_tools as chat_available_tools, available_tools_catalog as chat_available_tools_catalog, execute_tool_plan as chat_execute_tool_plan, normalize_tool_plan as chat_normalize_tool_plan
from vector_index_local import ensure_schema as ensure_vector_schema, rebuild_index as vector_rebuild_index, index_stats as vector_index_stats, search_index as vector_search_index, list_index_versions as vector_list_index_versions, refresh_index_for_chapters as vector_refresh_index_for_chapters
from compila_iterativo import build_prompt
from agent_config import load_agent_configs, save_agent_configs
import requests, base64
from datetime import datetime

# --- CONFIGURAZIONI PROMPT ---
PROMPTS_FILE = "prompts.json"

def load_prompts():
    if os.path.exists(PROMPTS_FILE):
        try:
            with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    # Default if file missing or corrupted
    return {
        "admin_chat_reasoning_prompt": "### STAGE: RAGIONAMENTO INTERNO (Admin Reasoning)\n### OBIETTIVO: Analizza la domanda dell'autore e il contesto globale dell'opera.\n\n[[CONTESTO_OPERA]]:\n{{context_text}}\n\n[[DOMANDA_UTENTE]]:\n{{user_msg}}\n\n[[ISTRUZIONI]]:\nIdentifica i punti chiave, le potenziali incoerenze e i dettagli del canone rilevanti. Produci un piano di risposta strutturato. Non rispondere ancora all'utente.",
        "admin_chat_synthesis_prompt": "### STAGE: SINTESI FINALE (Admin Synthesis)\n### OBIETTIVO: Rispondi all'autore in modo accurato e professionale.\n\n[[RAGIONAMENTO_PRECEDENTE]]:\n{{reasoning}}\n\n[[DOMANDA_UTENTE]]:\n{{user_msg}}\n\n[[ISTRUZIONI]]:\nUsa il ragionamento per fornire la risposta finale. Sii l'assistente perfetto per lo scrittore.",
        "frontend_chat_reasoning_prompt": "### STAGE: RAGIONAMENTO SPOILER-FREE (Frontend Reasoning)\n### OBIETTIVO: Analizza la domanda del lettore senza svelare il futuro.\n\n[[CONTESTO_ACCESSIBILE]]:\n{{context_text}}\n\n[[DOMANDA_UTENTE]]:\n{{user_msg}}\n\n[[ISTRUZIONI]]:\nIdentifica cosa il lettore sa già. Prepara una risposta che chiarisca i dubbi senza fare spoiler. Non rispondere ancora al lettore.",
        "frontend_chat_synthesis_prompt": "### STAGE: SINTESI LETTORE (Frontend Synthesis)\n### OBIETTIVO: Rispondi al lettore in modo coinvolgente.\n\n[[RAGIONAMENTO_SPOILER_FREE]]:\n{{reasoning}}\n\n[[DOMANDA_UTENTE]]:\n{{user_msg}}\n\n[[ISTRUZIONI]]:\nUsa il ragionamento per fornire la risposta finale. Mantieni il mistero sui capitoli futuri.",
        "system_instruction": "Sei un ghostwriter di altissimo livello, maestro del romanzo crudo, oscuro e realistico (stile George R.R. Martin, Joe Abercrombie). Scrivi ESCLUSIVAMENTE in Prima Persona. REGOLE D'ORO: 1. VOCABOLARIO: Usa solo parole esistenti nella lingua italiana. ZERO neologismi o termini inventati. 2. SHOW DON'T TELL: mostra reazioni fisiche, non nominare emozioni. 3. SENSORIALITÀ: focus su odori, suoni e texture concrete. 4. REALISMO CRUDO: Niente metafore poetiche astratte o surreali. Se descrivi un oggetto, deve avere una consistenza fisica logica.",
        "planner_prompt": "Esegui una pianificazione dettagliata per il Capitolo {{cap_id}} del romanzo \"{{p_title}}\".",
        "metadata_generator_prompt": "### STAGE: ARCHITETTURA METADATI E COERENZA\n..."
    }

def save_prompts(data):
    with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

UI_SETTINGS_FILE = "ui_settings.json"

def load_ui_settings():
    if os.path.exists(UI_SETTINGS_FILE):
        try:
            with open(UI_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {
        "contact_intro": "Hai domande o suggerimenti? Scrivici qui sotto.",
        "contact_success": "Messaggio inviato con successo!",
        "donation_links": []
    }

def save_ui_settings(data):
    with open(UI_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

WP_SETTINGS_FILE = "wordpress_settings.json"

def load_wp_settings():
    if os.path.exists(WP_SETTINGS_FILE):
        try:
            with open(WP_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {
        "wp_url": "",
        "wp_user": "",
        "wp_app_pass": "",
        "seo_plugin": "rankmath"
    }

def save_wp_settings(data):
    with open(WP_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

load_dotenv()
ADMIN_USER = os.getenv("ADMIN_USER", "vash")
ADMIN_PASS = os.getenv("ADMIN_PASS", "mammata")

def get_env_var(key, default=""):
    if key == 'PROJECT_TIMELINE':
        canon_path = os.path.join(os.getcwd(), "CANONE_DEFINITIVO.md")
        if os.path.exists(canon_path):
            try:
                with open(canon_path, "r", encoding="utf-8") as f:
                    return f.read()
            except:
                pass
    return os.getenv(key, default)

DB_PATH = "roman.db"
CAPITOLI_DIR = "capitoli"
LOGS_DIR = "logs"

if not os.path.exists(LOGS_DIR): os.makedirs(LOGS_DIR)
log_file = os.path.join(LOGS_DIR, f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    encoding='utf-8'
)
logger = logging.getLogger(__name__)
logger.info("--- AVVIO APPLICAZIONE ---")

app = Flask(__name__)
app.secret_key = os.urandom(24)

def set_env_var(key, value):
    if key == 'PROJECT_TIMELINE':
        # Per la Timeline usiamo il file Markdown dedicato per preservare i newline e la formattazione
        canon_path = os.path.join(os.getcwd(), "CANONE_DEFINITIVO.md")
        try:
            with open(canon_path, 'w', encoding="utf-8") as f:
                f.write(str(value))
        except Exception as e:
            logger.error(f"Errore salvataggio CANONE_DEFINITIVO.md: {e}")
            
        # Nel file .env mettiamo solo un segnaposto
        value = "Consulta CANONE_DEFINITIVO.md"
    else:
        # Rimuove eventuali newline per le altre variabili ENV per evitare corruzione del file .env
        value = str(value).replace("\n", " ").replace("\r", " ").strip()
    
    env_path = os.path.join(os.getcwd(), '.env')
    lines = []
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding="utf-8") as f:
            lines = f.readlines()
            
    # Ricostruiamo il file pulito senza duplicati
    new_lines = []
    found = False
    for line in lines:
        if line.strip() and not line.startswith("#"):
            if "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == key:
                    new_lines.append(f"{key}={value}\n")
                    found = True
                    continue
        new_lines.append(line)
        
    if not found:
        new_lines.append(f"{key}={value}\n")
        
    with open(env_path, 'w', encoding="utf-8") as f:
        f.writelines(new_lines)
    
    os.environ[key] = value

def get_project_title():
    title = get_env_var('PROJECT_TITLE', 'Romanzo')
    # Forza l'isolamento della prima riga per evitare leak di altre variabili .env
    return title.split('=')[-1].split('\n')[0].split('\r')[0].strip()

def get_full_canon():
    canon_path = os.path.join(os.getcwd(), "CANONE_DEFINITIVO.md")
    if os.path.exists(canon_path):
        with open(canon_path, "r", encoding="utf-8") as f:
            return f.read()
    return get_env_var('PROJECT_TIMELINE', 'Timeline non disponibile.')

def estimate_tokens(text):
    """Stima approssimativa dei token (1 token ogni ~4 caratteri)."""
    if not text: return 0
    return len(str(text)) // 4

def chunk_text(text, max_tokens, overlap=100):
    """Divide il testo in chunk basati sulla stima dei token con overlap."""
    if not text: return []
    max_chars = max_tokens * 4
    overlap_chars = overlap * 4
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        chunks.append(text[start:end])
        if end >= len(text): break
        start = end - overlap_chars
    return chunks

def get_character_context(cap_id):
    """Recupera metadati profondi dei personaggi per il capitolo."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT p.nome, p.ruolo, p.background, p.tratti_fisici, p.tratti_psicologici,
               pc.presente, pc.luogo, pc.stato_emotivo, pc.obiettivo, pc.azione_parallela, pc.note
        FROM personaggi p
        JOIN personaggi_capitoli pc ON pc.personaggio_id = p.id
        WHERE pc.capitolo_id = ? AND (pc.presente = 1 OR pc.azione_parallela != '')
    """, (cap_id,)).fetchall()
    conn.close()
    
    ctx = "### STATO PERSONAGGI E AZIONI PARALLELE\n"
    for r in rows:
        status = "PRESENTE" if r['presente'] else "ASSENTE (Altrove)"
        ctx += f"- {r['nome']} ({r['ruolo']}) - [{status}]\n"
        if r['presente']:
            ctx += f"  - Luogo: {r['luogo']}\n"
            ctx += f"  - Stato Emotivo: {r['stato_emotivo']}\n"
            ctx += f"  - Obiettivo: {r['obiettivo']}\n"
        else:
            ctx += f"  - Azione parallela (altrove): {r['azione_parallela']}\n"
        if r['note']: ctx += f"  - Note contestuali: {r['note']}\n"
    return ctx

def run_deep_context_pipeline(cap_id, provider, model_name, api_key, user_msg="", admin_mode=True):
    """
    Esegue la 'digestione' del contesto globale in stadi multi-messaggio.
    Restituisce una lista di messaggi (Chat History) strutturata.
    """
    from llm_client import generate_chapter_text
    prompts = load_prompts()
    caps = get_all()
    max_tokens_limit = int(get_env_var("AI_MAX_CONTEXT_TOKENS", "18000"))
    
    messages = []
    
    # --- STAGE 0: ARCHETIPO (System) ---
    canon = get_full_canon()
    sys_instr = prompts.get("system_instruction", "")
    # Reader mode: hard anti-spoiler boundary (niente canone completo nel system prompt)
    if not admin_mode:
        sys_instr += (
            f"\n\n[[POLITICA_LETTORE]]:\n"
            f"Il lettore è fermo al Capitolo {cap_id}. Usa SOLO contesto da capitoli <= {cap_id}, timeline accessibile, stati personaggi accessibili e testo corrente. "
            f"NON usare né citare informazioni dai capitoli futuri."
        )
    else:
        sys_instr += f"\n\n[[CANONE_DEFINITIVO]]:\n{canon}"

    messages.append({"role": "system", "content": sys_instr})

    # --- STAGE 1: STRUTTURA (Metadata Table) ---
    meta_table = "### STRUTTURA OPERA (ToC)\n"
    for c in caps:
        # Per il lettore, mostriamo solo i titoli fino al capitolo corrente
        if not admin_mode and c['id'] > cap_id:
            meta_table += f"Cap {c['id']}: [NON ANCORA DISPONIBILE]\n"
        else:
            meta_table += f"Cap {c['id']}: {c['titolo']} ({c['pov']})\n"
            
    messages.append({"role": "user", "content": f"Analizza la struttura globale:\n{meta_table}\n\nRichiesta specifica: {user_msg}"})
    messages.append({"role": "assistant", "content": "Struttura acquisita. Procedo con l'analisi temporale."})

    # --- STAGE 1.5: TIMELINE (Event Context) ---
    conn = get_conn()
    cap_row = conn.execute("SELECT timeline_event_id FROM capitoli WHERE id=?", (cap_id,)).fetchone()
    timeline_ctx = "### CONTESTO TIMELINE (Evento associato)\nNessun evento specifico associato a questo capitolo."
    if cap_row and cap_row['timeline_event_id']:
        event = conn.execute("SELECT * FROM timeline WHERE id=?", (cap_row['timeline_event_id'],)).fetchone()
        if event:
            e = dict(event)
            timeline_ctx = f"### CONTESTO TIMELINE\n- ARCO: {e['arco_inizio']} — {e['arco_fine']}\n- EVENTO: {e['descrizione']}\n- MOTIVO: {e['motivo']}\n- COINVOLTI: {e['personaggi_coinvolti']}\n- ESCLUSI: {e['personaggi_esclusi']} ({e['motivo_esclusione']})"
    conn.close()
    messages.append({"role": "user", "content": timeline_ctx})
    messages.append({"role": "assistant", "content": "Contesto temporale integrato."})

    # --- STAGE 2: MEMORIA STORICA (Summaries) ---
    # Prendiamo i riassunti rilevanti (tutti per admin, solo precedenti per lettore)
    relevant_summaries = [f"Cap {c['id']}: {c.get('riassunto','')}" for c in caps if (not admin_mode and c['id'] <= cap_id) or admin_mode]
    summaries_text = "### ANALISI STORICA (RIASSUNTI)\n" + "\n".join(relevant_summaries)
    
    # Se troppo lungo, mandiamo solo un chunk compatto (pruning preventivo)
    if len(summaries_text.split()) > (max_tokens_limit // 4):
        # Per il lettore, se siamo troppo avanti, mostriamo solo gli ultimi N
        summaries_text = "### ANALISI STORICA COMPATTA (Riassunti salienti)\n" + "\n".join(relevant_summaries[-20:])
        
    messages.append({"role": "user", "content": summaries_text})
    messages.append({"role": "assistant", "content": "Contesto storico integrato nella memoria di lavoro."})

    # --- STAGE 3: CHARACTER PULSE (Deep Metadata) ---
    char_ctx = get_character_context(cap_id)
    messages.append({"role": "user", "content": char_ctx})
    messages.append({"role": "assistant", "content": "Stati emotivi e azioni parallele dei personaggi acquisiti."})

    # --- STAGE 4: PROSSIMITÀ (Testo Profondo) ---
    deep_text = ""
    prev_cap = read_txt(cap_id - 1) if cap_id > 1 else ""
    curr_cap = read_txt(cap_id)
    
    if admin_mode:
        deep_text = f"### DETTAGLIO PROSSIMITÀ\nCAPITOLO PRECEDENTE ({cap_id-1}):\n{prev_cap[-2000:]}\n\nCAPITOLO CORRENTE ({cap_id}):\n{curr_cap[:2000]}"
    else:
        deep_text = f"### DETTAGLIO PROSSIMITÀ\nTESTO CORRENTE:\n{curr_cap[:3000]}"
        
    messages.append({"role": "user", "content": deep_text})
    
    return messages

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

COLORI_POV = {
    "Lin":"#e8d5b7","Michael":"#b7c9e8","Artem":"#b7e8c9","Sergej":"#e8b7b7",
    "Omar":"#d4e8b7","Leah":"#e8d4b7","Yusuf":"#b7d4e8","Eitan":"#c9b7e8",
    "Andriy":"#e8e8b7","Neda":"#e8b7d4","Vash":"#d4b7e8",
}

MODELS_CONFIG = {
    "openai": [
        ("gpt-5", "GPT-5 (Flagship)"),
        ("gpt-5-mini", "GPT-5 Mini (Fast)"),
        ("o3-mini", "o3-mini (Reasoning)"),
        ("gpt-4o", "GPT-4o (Omni)"),
        ("gpt-4o-mini", "GPT-4o Mini"),
        ("o1", "o1 (Advanced Reasoning)"),
        ("openai13b", "OpenAI 13B (Custom/OSS)"),
    ],
    "anthropic": [
        ("claude-3-7-sonnet-20250219", "Claude 3.7 Sonnet (Latest)"),
        ("claude-3-5-sonnet-20241022", "Claude 3.5 Sonnet"),
        ("claude-3-5-haiku-20241022", "Claude 3.5 Haiku"),
        ("claude-3-opus-20240229", "Claude 3 Opus"),
    ],
    "google": [
        ("gemini-2.0-flash", "Gemini 2.0 Flash (Fast)"),
        ("gemini-2.0-pro-exp-02-05", "Gemini 2.0 Pro Experimental"),
        ("gemini-1.5-pro", "Gemini 1.5 Pro"),
        ("gemini-1.5-flash", "Gemini 1.5 Flash"),
    ]
}

LINEE = ["Lin","Artem/Sergej","Omar/Leah","Yusuf/Eitan","Andriy","Neda","Convergenza","Michael","Vash/Ezra"]

CAMPI_META = [
    ("titolo","Titolo","text"),
    ("pov","POV (narratore)","text"),
    ("anno","Anno","text"),
    ("luogo","Luogo specifico","text"),
    ("luogo_macro","Luogo macro","text"),
    ("linea_narrativa","Linea narrativa","text"),
    ("data_narrativa","Data narrativa","text"),
    ("stato","Stato","select"),
    ("parole_target","Parole target","text"),
    ("personaggi_capitolo","Personaggi in scena","textarea"),
    ("personaggi_precedenti","Personaggi — info PRECEDENTI","textarea"),
    ("personaggi_successivi","Personaggi — info SUCCESSIVE","textarea"),
    ("scene_outline","Outline delle scene","textarea"),
    ("oggetti_simbolo","Oggetti simbolo","text"),
    ("tensione_capitolo","Tensione capitolo","text"),
    ("hook_finale","Hook finale","text"),
    ("rischi_incoerenza","Rischi di incoerenza","textarea"),
    ("transizione_prossimo_capitolo","Transizione prossimo cap","textarea"),
    ("descrizione","Descrizione","textarea"),
    ("background","Background (altri archi)","textarea"),
    ("parallelo","Cosa succede ALTROVE","textarea"),
    ("obiettivi_personaggi","Obiettivi personaggi","textarea"),
    ("timeline_capitolo","Timeline del capitolo","textarea"),
    ("timeline_opera","Timeline dell'opera","textarea"),
    ("riassunto","Riassunto","textarea"),
    ("riassunto_capitolo_precedente","Riassunto Cap Precedente","textarea"),
    ("riassunto_capitolo_successivo","Riassunto Cap Successivo","textarea"),
    ("revisione_istruzioni","Istruzioni Specifiche Revisione","textarea"),
]

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_agent_registry_ready():
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
    finally:
        conn.close()

ensure_agent_registry_ready()
def resolve_chat_model_from_registry(admin_mode):
    role_key = "AnswerSynthesizer" if admin_mode else "ReaderAnswerer"
    mode = "author" if admin_mode else "reader"
    conn = get_conn()
    try:
        agent = registry_resolve_agent_for_role(conn, mode=mode, role_key=role_key)
    finally:
        conn.close()
    if not agent:
        return None

    provider = agent.get("provider_type")
    model_name = agent.get("model_id")
    endpoint_base_url = agent.get("base_url") or ""
    api_key = ""
    api_key_env = (agent.get("api_key_env") or "").strip()
    if api_key_env:
        api_key = get_env_var(api_key_env, "")

    if endpoint_base_url:
        if provider == "lmstudio":
            set_env_var("LMSTUDIO_URL", endpoint_base_url)
        elif provider == "openai_compatible":
            set_env_var("OPENAI_COMPATIBLE_URL", endpoint_base_url)
        elif provider == "ollama":
            set_env_var("OLLAMA_URL", endpoint_base_url)

    return {
        "provider": provider,
        "model_name": model_name,
        "api_key": api_key,
        "agent": {
            "agent_key": agent.get("agent_key"),
            "label": agent.get("label"),
            "role_key": agent.get("role_key"),
            "provider_type": provider,
            "model_id": model_name,
        },
    }


def _agent_prompt_text(agent, prompt_kind, default_text=""):
    prompts = agent.get("prompts") or []
    if isinstance(prompts, dict):
        val = (prompts.get(prompt_kind) or "").strip()
        return val or default_text
    if isinstance(prompts, list):
        for item in prompts:
            if str(item.get("prompt_kind", "")).strip() == prompt_kind:
                txt = (item.get("prompt_text") or "").strip()
                if txt:
                    return txt
    return default_text


def _apply_agent_endpoint_env(provider, endpoint_base_url):
    if not endpoint_base_url:
        return
    if provider == "lmstudio":
        set_env_var("LMSTUDIO_URL", endpoint_base_url)
    elif provider == "openai_compatible":
        set_env_var("OPENAI_COMPATIBLE_URL", endpoint_base_url)
    elif provider == "ollama":
        set_env_var("OLLAMA_URL", endpoint_base_url)


def _agent_runtime_config(agent):
    provider = (agent.get("provider_type") or "").strip()
    model_name = (agent.get("model_id") or "").strip()
    api_key_env = (agent.get("api_key_env") or "").strip()
    endpoint_base_url = (agent.get("base_url") or "").strip()
    api_key = get_env_var(api_key_env, "") if api_key_env else ""
    _apply_agent_endpoint_env(provider, endpoint_base_url)
    return {"provider": provider, "model_name": model_name, "api_key": api_key}


def resolve_agents_for_mode(admin_mode):
    mode = "author" if admin_mode else "reader"
    required_roles = ["AuthorTaskRouter", "AnswerSynthesizer"] if admin_mode else ["ReaderAnswerer", "SpoilerJudge"]
    conn = get_conn()
    try:
        resolved = {}
        missing = []
        for role_key in required_roles:
            agent = registry_resolve_agent_for_role(conn, mode=mode, role_key=role_key)
            if agent:
                resolved[role_key] = agent
            else:
                missing.append(role_key)
    finally:
        conn.close()
    return {"mode": mode, "required_roles": required_roles, "resolved": resolved, "missing": missing}


def _extract_json_object(raw_text):
    text = str(raw_text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def _parse_agent_tool_scope(agent):
    scope_raw = agent.get("tool_scope", "[]")
    if isinstance(scope_raw, list):
        return [str(x).strip() for x in scope_raw if str(x).strip()]
    try:
        parsed = json.loads(scope_raw or "[]")
    except Exception:
        parsed = []
    if not isinstance(parsed, list):
        return []
    return [str(x).strip() for x in parsed if str(x).strip()]


def _normalize_tool_plan_contract(raw_text):
    parsed = _extract_json_object(raw_text)
    if not isinstance(parsed, dict):
        return {"ok": False, "error": "Output JSON mancante o non valido", "tool_plan": [], "parsed": {}}
    tool_plan = parsed.get("tool_plan", [])
    norm = chat_normalize_tool_plan(tool_plan)
    if not norm.get("ok"):
        return {"ok": False, "error": norm.get("error", "tool_plan non valido"), "tool_plan": [], "parsed": parsed}
    return {"ok": True, "tool_plan": norm["plan"], "parsed": parsed}


def _ensure_tool_session(conn, session_key, admin_mode, cap_id):
    row = conn.execute("SELECT id FROM chat_sessions WHERE session_key=?", (session_key,)).fetchone()
    if row:
        return row["id"]
    mode = "author" if admin_mode else "reader"
    cur = conn.execute(
        "INSERT OR IGNORE INTO chat_sessions (session_key, mode, cap_id, user_scope) VALUES (?, ?, ?, '')",
        (session_key, mode, cap_id),
    )
    if cur.lastrowid:
        return cur.lastrowid
    row_retry = conn.execute("SELECT id FROM chat_sessions WHERE session_key=?", (session_key,)).fetchone()
    return row_retry["id"] if row_retry else None


def _execute_tool_plan_with_logging(conn, session_key, cap_id, admin_mode, agent, tool_plan, stop_on_error=True):
    allowed_tools = _parse_agent_tool_scope(agent)
    result = chat_execute_tool_plan(
        conn,
        tool_plan,
        admin_mode=admin_mode,
        allowed_tools=allowed_tools,
        stop_on_error=stop_on_error,
    )
    session_id = _ensure_tool_session(conn, session_key, admin_mode, cap_id) if session_key else None
    agent_id = agent.get("id")
    for run in result.get("runs", []):
        idx = max(0, int(run.get("index", 1)) - 1)
        args = tool_plan[idx].get("arguments", {}) if idx < len(tool_plan) else {}
        status = "ok" if run.get("status") == "ok" else ("blocked" if run.get("status") == "blocked" else "error")
        conn.execute(
            """
            INSERT INTO chat_tool_runs (session_id, agent_id, tool_name, arguments_json, result_json, status, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (
                session_id,
                agent_id,
                run.get("tool", ""),
                json.dumps(args, ensure_ascii=False),
                json.dumps(run.get("result", {}), ensure_ascii=False),
                status,
            ),
        )
    conn.commit()
    return result


def _should_force_vector_lookup(user_msg):
    text = (user_msg or "").lower()
    if not text:
        return False
    keywords = [
        "chi ", "chi è", "quando", "dove", "perché", "spiega", "riassunto",
        "cosa succede", "timeline", "personaggio", "personaggi", "capitolo",
        "coerenza", "analisi", "simbolo", "tema",
    ]
    return any(k in text for k in keywords)


def _tool_plan_has_vector(plan, admin_mode):
    target = "vector_search_author" if admin_mode else "vector_search_reader"
    for step in (plan or []):
        if str(step.get("tool", "")).strip() == target:
            return True
    return False


def _forced_vector_step(user_msg, cap_id, admin_mode, k=6):
    if admin_mode:
        return {"tool": "vector_search_author", "arguments": {"query": user_msg, "k": k}}
    return {"tool": "vector_search_reader", "arguments": {"query": user_msg, "cap_id": cap_id, "k": k}}


def _run_direct_vector_fallback(conn, session_key, cap_id, admin_mode, agent, user_msg, k=6):
    ensure_vector_schema(conn)
    if admin_mode:
        result = vector_search_index(conn, user_msg, k=k, max_cap_id=None)
        tool_name = "vector_search_author"
        args = {"query": user_msg, "k": k}
    else:
        result = vector_search_index(conn, user_msg, k=k, max_cap_id=cap_id)
        tool_name = "vector_search_reader"
        args = {"query": user_msg, "cap_id": cap_id, "k": k}
    session_id = _ensure_tool_session(conn, session_key, admin_mode, cap_id) if session_key else None
    conn.execute(
        """
        INSERT INTO chat_tool_runs (session_id, agent_id, tool_name, arguments_json, result_json, status, duration_ms)
        VALUES (?, ?, ?, ?, ?, ?, 0)
        """,
        (
            session_id,
            agent.get("id") if agent else None,
            tool_name,
            json.dumps(args, ensure_ascii=False),
            json.dumps(result, ensure_ascii=False),
            "ok" if result.get("ok") else "error",
        ),
    )
    conn.commit()
    return result


def _extract_evidence_refs(tool_result, max_items=8):
    refs = []
    for run in (tool_result or {}).get("runs", []):
        res = run.get("result") or {}
        if not isinstance(res, dict):
            continue
        for item in res.get("results", []) or []:
            if not isinstance(item, dict):
                continue
            cap_id = item.get("cap_id")
            chunk_no = item.get("chunk_no")
            score = item.get("score")
            if cap_id is None or chunk_no is None:
                continue
            refs.append({
                "cap_id": cap_id,
                "chunk_no": chunk_no,
                "score": score,
            })
            if len(refs) >= max_items:
                return refs
    return refs


def _mcp_token_sha(token):
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _sync_mcp_tokens_from_env(conn):
    raw = (get_env_var("MCP_BRIDGE_TOKENS_JSON", "") or "").strip()
    if not raw:
        return
    try:
        items = json.loads(raw)
    except Exception:
        return
    if not isinstance(items, list):
        return
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        plain = str(item.get("token") or "").strip()
        if not plain:
            continue
        token_id = str(item.get("token_id") or f"env-token-{idx}").strip()
        scope = str(item.get("scope") or "both").strip().lower()
        if scope not in {"reader", "author", "both"}:
            scope = "both"
        max_cap_id = item.get("max_cap_id")
        try:
            max_cap_id = int(max_cap_id) if max_cap_id is not None else None
            if max_cap_id is not None and max_cap_id <= 0:
                max_cap_id = None
        except Exception:
            max_cap_id = None
        try:
            rpm = max(1, min(int(item.get("rate_limit_per_minute", 60) or 60), 600))
        except Exception:
            rpm = 60
        enabled = 1 if bool(item.get("enabled", True)) else 0
        conn.execute(
            """
            INSERT INTO mcp_bridge_tokens
                (token_id, token_hash, label, tenant_id, scope, max_cap_id, rate_limit_per_minute, enabled, policy_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(token_id) DO UPDATE SET
                token_hash=excluded.token_hash,
                label=excluded.label,
                tenant_id=excluded.tenant_id,
                scope=excluded.scope,
                max_cap_id=excluded.max_cap_id,
                rate_limit_per_minute=excluded.rate_limit_per_minute,
                enabled=excluded.enabled,
                policy_json=excluded.policy_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                token_id,
                _mcp_token_sha(plain),
                str(item.get("label") or token_id),
                str(item.get("tenant_id") or "default"),
                scope,
                max_cap_id,
                rpm,
                enabled,
                json.dumps(item.get("policy", {}), ensure_ascii=False),
            ),
        )
    conn.commit()


def _mcp_resolve_policy(conn, req):
    auth = (req.headers.get("Authorization") or "").strip()
    if not auth.lower().startswith("bearer "):
        return None
    token = auth[7:].strip()
    if not token:
        return None
    _sync_mcp_tokens_from_env(conn)
    row = conn.execute(
        """
        SELECT token_id, tenant_id, scope, max_cap_id, rate_limit_per_minute, enabled, policy_json
        FROM mcp_bridge_tokens
        WHERE token_hash=? AND enabled=1
        LIMIT 1
        """,
        (_mcp_token_sha(token),),
    ).fetchone()
    if row:
        try:
            policy_extra = json.loads(row["policy_json"] or "{}")
        except Exception:
            policy_extra = {}
        return {
            "token_id": row["token_id"],
            "tenant_id": row["tenant_id"] or "default",
            "scope": row["scope"] or "both",
            "max_cap_id": row["max_cap_id"],
            "rate_limit_per_minute": int(row["rate_limit_per_minute"] or 60),
            "policy": policy_extra,
        }
    fallback = get_env_var("MCP_BRIDGE_TOKEN", "").strip() or get_env_var("API_TOKEN", "").strip()
    if fallback and token == fallback:
        try:
            fallback_rpm = max(1, min(int(get_env_var("MCP_BRIDGE_RATE_LIMIT_PER_MINUTE", "60") or 60), 600))
        except Exception:
            fallback_rpm = 60
        return {
            "token_id": "env-default",
            "tenant_id": "default",
            "scope": "both",
            "max_cap_id": None,
            "rate_limit_per_minute": fallback_rpm,
            "policy": {"source": "env_fallback"},
        }
    return None


def _mcp_rate_limit_ok(conn, token_id, client_key, per_minute=60):
    window = int(time.time()) // 60
    row = conn.execute(
        """
        SELECT id, count
        FROM mcp_bridge_rate_limits
        WHERE token_id=? AND client_key=? AND window_minute=?
        LIMIT 1
        """,
        (token_id, client_key, window),
    ).fetchone()
    if not row:
        conn.execute(
            """
            INSERT INTO mcp_bridge_rate_limits (token_id, client_key, window_minute, count)
            VALUES (?, ?, ?, 1)
            """,
            (token_id, client_key, window),
        )
        conn.commit()
        return True
    current = int(row["count"] or 0)
    if current >= int(per_minute):
        return False
    conn.execute(
        "UPDATE mcp_bridge_rate_limits SET count=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (current + 1, row["id"]),
    )
    conn.commit()
    return True


def _mcp_policy_allows_mode(policy, mode):
    scope = (policy or {}).get("scope", "both")
    if scope == "both":
        return True
    return scope == mode


def _mcp_policy_allows_cap(policy, mode, cap_id):
    if mode != "reader":
        return True
    max_cap_id = (policy or {}).get("max_cap_id")
    if max_cap_id is None:
        return True
    try:
        return int(cap_id or 0) <= int(max_cap_id)
    except Exception:
        return False


def _mcp_audit_log(conn, **kwargs):
    conn.execute(
        """
        INSERT INTO mcp_bridge_audit
            (token_id, tenant_id, client_key, endpoint, mode, cap_id, query_len, k, min_score, status, result_count, error_message, latency_ms, meta_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            kwargs.get("token_id", ""),
            kwargs.get("tenant_id", ""),
            kwargs.get("client_key", ""),
            kwargs.get("endpoint", ""),
            kwargs.get("mode", ""),
            kwargs.get("cap_id"),
            int(kwargs.get("query_len", 0) or 0),
            kwargs.get("k"),
            kwargs.get("min_score"),
            kwargs.get("status", "error"),
            int(kwargs.get("result_count", 0) or 0),
            kwargs.get("error_message", ""),
            int(kwargs.get("latency_ms", 0) or 0),
            json.dumps(kwargs.get("meta", {}), ensure_ascii=False),
        ),
    )
    conn.commit()


def _mcp_public_token_row(row):
    if not row:
        return None
    policy = {}
    try:
        policy = json.loads(row["policy_json"] or "{}")
    except Exception:
        policy = {}
    return {
        "token_id": row["token_id"],
        "label": row["label"] or "",
        "tenant_id": row["tenant_id"] or "default",
        "scope": row["scope"] or "both",
        "max_cap_id": row["max_cap_id"],
        "rate_limit_per_minute": int(row["rate_limit_per_minute"] or 60),
        "enabled": bool(row["enabled"]),
        "policy": policy if isinstance(policy, dict) else {},
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def normalize_chat_history(history, max_turns=8):
    if not isinstance(history, list):
        return []
    cleaned = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = (item.get("role") or "").strip().lower()
        content = (item.get("content") or "").strip()
        if role not in {"user", "assistant"}:
            continue
        if not content:
            continue
        cleaned.append({"role": role, "content": content})
    if len(cleaned) > max_turns:
        cleaned = cleaned[-max_turns:]
    return cleaned


def build_chat_session_key(cap_id, admin_mode):
    role = "author" if admin_mode else "reader"
    sid = session.get("sid")
    if not sid:
        sid = os.urandom(8).hex()
        session["sid"] = sid
    return f"{sid}:{role}:cap{cap_id}"


def compose_user_message_with_history(user_msg, history):
    turns = normalize_chat_history(history)
    if not turns:
        return user_msg

    lines = ["[CONTESTO_CONVERSAZIONE_RECENTE]"]
    for item in turns:
        prefix = "Utente" if item["role"] == "user" else "Assistente"
        lines.append(f"- {prefix}: {item['content']}")
    lines.append("[/CONTESTO_CONVERSAZIONE_RECENTE]")

    return f"{user_msg}\n\n" + "\n".join(lines)


def parse_sse_payload(chunk_sse):
    prefix = "data: "
    if not isinstance(chunk_sse, str) or not chunk_sse.startswith(prefix):
        return None
    raw = chunk_sse[len(prefix):].strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def log_spoiler_audit_event(session_key, cap_id, audit, rewritten):
    if not session_key:
        return
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        row = conn.execute("SELECT id FROM chat_sessions WHERE session_key=?", (session_key,)).fetchone()
        session_id = row["id"] if row else None
        conn.execute(
            """
            INSERT INTO chat_tool_runs (session_id, agent_id, tool_name, arguments_json, result_json, status, duration_ms)
            VALUES (?, NULL, 'spoiler_audit', ?, ?, ?, 0)
            """,
            (
                session_id,
                json.dumps({"cap_id": cap_id}, ensure_ascii=False),
                json.dumps({"audit": audit, "rewritten": rewritten}, ensure_ascii=False),
                "blocked" if audit.get("status") == "unsafe" else "ok",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _render_agent_studio_form(reader_agents):
    blocks = []
    for name, cfg in (reader_agents or {}).items():
        tools = ", ".join(cfg.get("allowed_tools", []))
        block = f"""
        <div style="border:1px solid #2a2f3a;border-radius:8px;padding:12px;margin-bottom:12px;background:#0f1115">
          <h3 style="margin:0 0 10px 0">{name}</h3>
          <label><input type="checkbox" name="agent_{name}_enabled" {'checked' if cfg.get('enabled') else ''}> enabled</label>
          <div class="field"><label>Provider</label><input type="text" name="agent_{name}_provider" value="{cfg.get('provider','')}"></div>
          <div class="field"><label>Model</label><input type="text" name="agent_{name}_model" value="{cfg.get('model','')}"></div>
          <div class="field"><label>System prompt</label><textarea name="agent_{name}_system_prompt" style="height:90px">{cfg.get('system_prompt','')}</textarea></div>
          <div class="field"><label>Allowed tools (comma-separated)</label><input type="text" name="agent_{name}_allowed_tools" value="{tools}"></div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div class="field"><label>Temperature</label><input type="number" step="0.1" name="agent_{name}_temperature" value="{cfg.get('temperature',0.2)}"></div>
            <div class="field"><label>Max tokens</label><input type="number" step="1" name="agent_{name}_max_tokens" value="{cfg.get('max_tokens',1200)}"></div>
          </div>
        </div>
        """
        blocks.append(block)
    return "".join(blocks)

def get_all():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM capitoli ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_cap(cap_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM capitoli WHERE id=?", (cap_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

# --- HELPERS TIMELINE ---
def get_timeline():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM timeline ORDER BY arco_inizio").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_timeline_event(id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM timeline WHERE id=?", (id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def save_timeline_event(data):
    conn = get_conn()
    if data.get('id'):
        conn.execute("""
            UPDATE timeline SET arco_inizio=?, arco_fine=?, descrizione=?, motivo=?, 
                                personaggi_coinvolti=?, personaggi_esclusi=?, motivo_esclusione=?
            WHERE id=?
        """, (data['arco_inizio'], data['arco_fine'], data['descrizione'], data['motivo'], 
              data['personaggi_coinvolti'], data['personaggi_esclusi'], data['motivo_esclusione'], data['id']))
    else:
        conn.execute("""
            INSERT INTO timeline (arco_inizio, arco_fine, descrizione, motivo, 
                                 personaggi_coinvolti, personaggi_esclusi, motivo_esclusione)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (data['arco_inizio'], data['arco_fine'], data['descrizione'], data['motivo'], 
              data['personaggi_coinvolti'], data['personaggi_esclusi'], data['motivo_esclusione']))
    conn.commit()
    conn.close()

# --- HELPERS PROMPTS VALIDATION ---
def get_validation_prompt(scopo):
    conn = get_conn()
    row = conn.execute("SELECT prompt_testo FROM validation_prompts WHERE scopo=?", (scopo,)).fetchone()
    conn.close()
    return row['prompt_testo'] if row else ""

def update_validation_prompt(scopo, testo):
    conn = get_conn()
    conn.execute("UPDATE validation_prompts SET prompt_testo=? WHERE scopo=?", (testo, scopo))
    conn.commit()
    conn.close()

def read_txt(cap_id):
    path = os.path.join(CAPITOLI_DIR, f"cap{cap_id:02d}.txt")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Errore lettura {path}: {e}")
            return ""
    return ""

def write_txt(cap_id, content):
    path = os.path.join(CAPITOLI_DIR, f"cap{cap_id:02d}.txt")
    if not os.path.exists(CAPITOLI_DIR): os.makedirs(CAPITOLI_DIR)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return len(content.split())
    except Exception as e:
        logger.error(f"Errore scrittura {path}: {e}")
        return 0

def get_sidebar_html(active_id=None, is_admin=True):
    caps = get_all()
    html = ""
    campi_meta_principali = ['descrizione', 'background', 'scene_outline', 'rischi_incoerenza', 'obiettivi_personaggi']
    
    for c in caps:
        cap_id = c['id']
        active = "active" if cap_id == active_id else ""
        
        # Word counts
        # 1. Narrativa (N) - Real-time calculation from text file
        txt_content = read_txt(cap_id)
        count_n = len(txt_content.split()) if txt_content else 0
        
        # 2. Riassunto (R) - From DB
        r = c.get('riassunto', '') or ''
        count_r = len(r.split())
        
        # 3. Metadati (M) - From DB
        count_m = 0
        for f in campi_meta_principali:
            val = c.get(f, '') or ''
            count_m += len(str(val).split())
            
        pov = c.get('pov') or ''
        color = COLORI_POV.get(pov.split('/')[0].strip(), '#888')
        
        url_prefix = "/cap" if is_admin else "/read"
        
        if is_admin:
            html += f"""<a href="{url_prefix}/{cap_id}" class="cap-link {active}">
      <span class="cap-num">{cap_id:02d}</span>
      <span class="pov-dot" style="background:{color}"></span>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{c['titolo']}</span>
      <span class="cap-parole" title="N: Narrativa | R: Riassunto | M: Metadati">
        <b style="color:var(--accent)">{count_n}</b> 
        <span style="color:#6fcf6f">{count_r}</span> 
        <span style="color:#a888ca">{count_m}</span>
      </span>
    </a>"""
        else:
             html += f'<a href="{url_prefix}/{cap_id}" class="cap-link {active}"><b>{cap_id:02d}</b> {c["titolo"]}</a>'
             
    return html

def get_paginated_text(text, words_per_page=500):
    paragraphs = text.replace("\r\n", "\n").split("\n\n")
    pages = []
    current_page_paragraphs = []
    current_word_count = 0
    
    for p in paragraphs:
        p_strip = p.strip()
        if not p_strip: continue
        p_words = len(p_strip.split())
        
        if current_word_count + p_words > words_per_page and current_page_paragraphs:
            # Chiudi la pagina corrente
            pages.append("\n\n".join(current_page_paragraphs))
            current_page_paragraphs = [p_strip]
            current_word_count = p_words
        else:
            current_page_paragraphs.append(p_strip)
            current_word_count += p_words
            
    if current_page_paragraphs:
        pages.append("\n\n".join(current_page_paragraphs))
        
    return pages if pages else [""]

BASE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
:root{--bg:#0f0f0f;--fg:#e8e6df;--accent:#c9a96e;--border:#2a2a2a;--card:#161616;--muted:#666;--input:#1e1e1e;--danger:#c0392b}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--fg);font-family:'Inter',sans-serif;font-size:14px;line-height:1.6}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.layout{display:flex;min-height:calc(100vh - 40px);margin-top:40px}
.sidebar{width:260px;background:var(--card);border-right:1px solid var(--border);overflow-y:auto;flex-shrink:0;position:sticky;top:40px;height:calc(100vh - 40px)}
.wp-adminbar{background:#1d2327;color:#f0f0f1;display:flex;align-items:center;height:40px;padding:0 16px;position:fixed;top:0;left:0;right:0;z-index:9999;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Oxygen-Sans,Ubuntu,Cantarell,"Helvetica Neue",sans-serif}
.wp-adminbar a{color:#f0f0f1;text-decoration:none;padding:0 12px;font-size:13px;display:flex;align-items:center;height:100%;transition:background 0.2s}
.wp-adminbar a:hover{background:#2c3338;color:#00a0d2}
.wp-adminbar-brand{font-weight:600;font-size:14px;color:var(--accent);margin-right:16px;display:flex;align-items:center;height:100%}
.wp-adminbar-right{margin-left:auto;display:flex;height:100%}
.cap-link{display:flex;align-items:center;gap:8px;padding:6px 12px;border-bottom:1px solid #1a1a1a;color:var(--fg);font-size:12px;transition:background 0.1s}
.cap-link:hover{background:#1f1f1f;text-decoration:none}
.cap-link.active{background:#22180a;color:var(--accent)}
.cap-num{color:var(--muted);min-width:24px;font-size:11px}
.pov-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.cap-parole{margin-left:auto;color:var(--muted);font-size:10px;display:flex;gap:4px;align-items:center}
.main{flex:1;overflow:auto}
.topbar{background:var(--card);border-bottom:1px solid var(--border);padding:12px 24px;display:flex;align-items:center;gap:12px}
.project-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 24px;
  position: relative;
}
.project-meta-item { margin-bottom: 12px; }
.project-meta-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; display: block; margin-bottom: 4px; }
.project-meta-value { font-size: 14px; line-height: 1.5; color: var(--fg); }
.read-more { color: var(--accent); cursor: pointer; font-size: 12px; margin-left: 8px; text-decoration: underline; }
.full-text-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); z-index: 2000; align-items: center; justify-content: center; padding: 40px; }
.full-text-modal { background: #111; border: 1px solid var(--accent); border-radius: 12px; padding: 30px; max-width: 800px; width: 100%; max-height: 80%; overflow-y: auto; position: relative; box-shadow: 0 20px 50px rgba(0,0,0,0.5); }
.close-overlay { position: absolute; top: 15px; right: 20px; font-size: 24px; cursor: pointer; color: var(--muted); }
.topbar h1{font-size:15px;color:var(--accent)}
.topbar .actions{margin-left:auto;display:flex;gap:8px}
.btn{display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border-radius:6px;border:1px solid var(--border);background:var(--input);color:var(--fg);font-size:12px;cursor:pointer;transition:all 0.15s;text-decoration:none}
.btn:hover{border-color:var(--accent);color:var(--accent);text-decoration:none}
.btn-primary{background:#2e1f08;border-color:var(--accent);color:var(--accent)}
.btn-primary:hover{background:#3a2a10}
.btn-danger{border-color:var(--danger);color:var(--danger)}
.content{padding:24px;max-width:1100px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:24px}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:20px;margin-bottom:16px}
.card h2{font-size:13px;color:var(--accent);text-transform:uppercase;letter-spacing:1px;margin-bottom:16px}
.field{margin-bottom:14px}
.field label{display:block;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px}
.field input,.field select,.field textarea{width:100%;background:var(--input);border:1px solid var(--border);color:var(--fg);padding:8px 10px;border-radius:6px;font-size:13px;font-family:inherit;transition:border-color 0.15s}
.field input:focus,.field select,.field textarea:focus,.field select:focus{outline:none;border-color:var(--accent)}
.field select{-webkit-appearance:none}
.field textarea{resize:vertical;min-height:80px}
.field textarea.tall{min-height:300px;font-family:'Georgia',serif;font-size:14px;line-height:1.8}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;color:#111}
.stat-row{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:16px}
.stat{display:flex;flex-direction:column}
.stat-label{font-size:10px;color:var(--muted);text-transform:uppercase}
.stat-val{font-size:20px;font-weight:600;color:var(--accent)}
.home-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px}
.cap-card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px;transition:border-color 0.15s}
.cap-card:hover{border-color:var(--accent);text-decoration:none}
.cap-card .num{font-size:10px;color:var(--muted)}
.cap-card .titolo{font-size:13px;font-weight:500;color:var(--fg);margin:4px 0}
.cap-card .meta{font-size:11px;color:var(--muted)}
.cap-card .words{font-size:11px;color:var(--accent);margin-top:4px}
.filter-bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}
.filter-btn{padding:4px 10px;border-radius:20px;border:1px solid var(--border);background:transparent;color:var(--muted);font-size:11px;cursor:pointer}
.filter-btn.active,.filter-btn:hover{border-color:var(--accent);color:var(--accent)}
.msg{padding:10px 16px;border-radius:6px;margin-bottom:16px;font-size:13px}
.msg.ok{background:#1a2e1a;border:1px solid #2d5a2d;color:#6fcf6f}
.msg.err{background:#2e1a1a;border:1px solid #5a2d2d;color:#cf6f6f}
.tabs{display:flex;gap:0;border-bottom:1px solid var(--border);margin-bottom:20px}
.tab{padding:8px 16px;font-size:13px;cursor:pointer;border-bottom:2px solid transparent;color:var(--muted);transition:all 0.15s}
.tab.active{color:var(--accent);border-bottom-color:var(--accent)}
.tab-content{display:none}.tab-content.active{display:block}
"""

ADMIN_LAYOUT = """
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} — Admin Dashboard</title>
<style>{{BASE_CSS | safe}}</style>
</head>
<body>
<div class="wp-adminbar">
  <div class="wp-adminbar-brand" title="{{ project_title }}">{{ project_title[:30] }}{{ '...' if project_title|length > 30 else '' }}</div>
  <a href="/admin">🏠 Dashboard</a>
  <a href="/admin/contatti">📩 Messaggi</a>
  <a href="/admin/sync" style="color:#6fcf6f;font-weight:600">🧮 Ricalcola Parole</a>
  <a href="/generazione" style="color:#c9a96e;font-weight:600">🧠 Generazione AI</a>
  <a href="/personaggi" style="color:#e8b7d4;font-weight:600">👥 Personaggi</a>
  <a href="/timeline" style="color:#6fcf6f;font-weight:600">⏳ Timeline</a>
  <div class="wp-adminbar-right">
    <a href="/">🌐 Vedi Sito</a>
    <a href="/settings">⚙️ Impostazioni</a>
    <a href="/logout">🚪 Logout</a>
  </div>
</div>
<div class="layout">
  <nav class="sidebar" id="admin-sidebar">
    <div style="display:flex;border-bottom:1px solid var(--border)">
      <a href="/admin" id="sb-cap-btn" style="flex:1;text-align:center;padding:8px 0;font-size:11px;color:var(--accent);border-bottom:2px solid var(--accent);text-decoration:none;transition:all 0.15s" title="Capitoli">📖 Capitoli</a>
      <a href="/personaggi" id="sb-per-btn" style="flex:1;text-align:center;padding:8px 0;font-size:11px;color:var(--muted);border-bottom:2px solid transparent;text-decoration:none;transition:all 0.15s" title="Personaggi">👥 Personaggi</a>
    </div>
    <div style="flex:1;overflow-y:auto;padding-top:4px">
    {{ all_caps_html | safe }}
    </div>
  </nav>
  <div class="main">
    {{ content | safe }}
  </div>
</div>
<script>
// Tabs
document.querySelectorAll('.tab').forEach(t => {
  t.addEventListener('click', () => {
    const group = t.dataset.group;
    document.querySelectorAll('[data-group="'+group+'"]').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    document.querySelectorAll('[data-tab="'+group+'"]').forEach(x => x.classList.remove('active'));
    document.querySelector('[data-tab="'+group+'"][data-id="'+t.dataset.id+'"]').classList.add('active');
  });
});
// Filtro linee
document.querySelectorAll('.filter-btn').forEach(b => {
  b.addEventListener('click', () => {
    const line = b.dataset.line;
    document.querySelectorAll('.filter-btn').forEach(x=>x.classList.remove('active'));
    b.classList.add('active');
    document.querySelectorAll('.cap-card').forEach(card => {
      card.style.display = (!line || card.dataset.linea === line || line==='all') ? '' : 'none';
    });
  });
});
// Auto-resize textarea
document.querySelectorAll('textarea').forEach(t => {
  t.addEventListener('input', () => { t.style.height='auto'; t.style.height=t.scrollHeight+'px'; });
});
</script>

<!-- ================= AI CHAT OVERLAY (Admin Backend) ================= -->
<div id="ai-chat-widget" style="position:fixed; bottom:30px; right:30px; z-index:9999; font-family:'Inter', sans-serif;">
  <button id="ai-chat-btn" onclick="toggleAIChat()" style="width:60px; height:60px; border-radius:50%; background:#111; border:2px solid #a888ca; color:#a888ca; font-size:24px; cursor:pointer; box-shadow:0 10px 25px rgba(0,0,0,0.8); display:flex; align-items:center; justify-content:center; transition:transform 0.3s; padding:0">
    <span style="font-family:'Special Elite', cursive; font-size:10px; font-weight:bold; letter-spacing:1px; line-height:1">AI DEV</span>
  </button>
  
  <div id="ai-chat-window" style="display:none; position:absolute; bottom:80px; right:0; width:450px; height:600px; background:rgba(12,12,13,0.98); backdrop-filter:blur(10px); border:1px solid #a888ca; border-radius:12px; box-shadow:0 15px 40px rgba(0,0,0,0.9); flex-direction:column; overflow:hidden;">
    <div style="background:rgba(168, 136, 202, 0.1); border-bottom:1px solid rgba(168, 136, 202,0.3); padding:15px; display:flex; justify-content:space-between; align-items:center;">
      <div>
        <h4 style="color:#a888ca; margin:0; font-family:'Special Elite', cursive; font-size:13px; text-transform:uppercase; letter-spacing:1px">Assistente Scrittura</h4>
        <span style="font-size:10px; color:var(--muted); font-family:'Inter', sans-serif;">Accesso globale a spoiler e timeline</span>
      </div>
      <button onclick="toggleAIChat()" style="background:transparent; border:none; color:#a888ca; font-size:20px; cursor:pointer; padding:0; line-height:1">&times;</button>
    </div>
    
    <div id="ai-chat-messages" style="flex:1; overflow-y:auto; padding:15px; display:flex; flex-direction:column; gap:12px; font-size:13px; scrollbar-width: thin; scrollbar-color: #a888ca transparent;">
      <div style="text-align:center; padding:10px; font-size:11px; opacity:0.5; color:var(--muted); border-bottom:1px solid rgba(255,255,255,0.05); margin-bottom:10px">Modalità Autore. L'AI ha accesso a CANONE_DEFINITIVO e ai riassunti di TUTTI i capitoli scritti e non.</div>
    </div>
    
    <div style="padding:15px; border-top:1px solid var(--border); display:flex; gap:10px; background:rgba(0,0,0,0.3)">
      <input type="text" id="ai-chat-input" placeholder="Come posso aiutarti col romanzo?" style="flex:1; background:transparent; border:none; color:#fff; font-family:'Inter', sans-serif; font-size:13px; padding:8px 0;" onkeypress="if(event.key==='Enter') sendAIChatMessage()">
      <button onclick="sendAIChatMessage()" style="background:transparent; border:none; color:#a888ca; cursor:pointer; font-weight:600; text-transform:uppercase; font-size:11px; letter-spacing:1px">Invia</button>
    </div>
  </div>
</div>

<script>
let chatMsgHistory = [];

function toggleAIChat() {
    const win = document.getElementById('ai-chat-window');
    const btn = document.getElementById('ai-chat-btn');
    if (win.style.display === 'none') {
        win.style.display = 'flex';
        btn.style.transform = 'scale(0.9)';
        setTimeout(() => document.getElementById('ai-chat-input').focus(), 100);
    } else {
        win.style.display = 'none';
        btn.style.transform = 'scale(1)';
    }
}

async function sendAIChatMessage() {
    const input = document.getElementById('ai-chat-input');
    const text = input.value.trim();
    if (!text) return;
    
    const messagesDiv = document.getElementById('ai-chat-messages');
    
    const userBubble = document.createElement('div');
    userBubble.style = "align-self:flex-end; background:#a888ca; color:#000; padding:10px 14px; border-radius:12px 12px 0 12px; max-width:85%; line-height:1.5;";
    userBubble.textContent = text;
    messagesDiv.appendChild(userBubble);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    
    input.value = '';
    
    const loadingBubble = document.createElement('div');
    loadingBubble.id = 'ai-chat-loading';
    loadingBubble.style = "align-self:flex-start; background:rgba(255,255,255,0.05); color:#a888ca; padding:10px 14px; border-radius:12px 12px 12px 0; font-size:16px; letter-spacing:2px; animation: pulse 1s infinite alternate";
    loadingBubble.textContent = "● ● ●";
    messagesDiv.appendChild(loadingBubble);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    
    let capIdStr = window.location.pathname.split('/')[2];
    let capId = parseInt(capIdStr);
    if (isNaN(capId)) capId = 1; 
    
    chatMsgHistory.push({"role": "user", "content": text});
    
    try {
        const response = await fetch(`/api/chat/${capId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text, admin_mode: true, stream: true, history: chatMsgHistory })
        });

        if (loadingBubble) loadingBubble.remove();
        
        const aiBubble = document.createElement('div');
        aiBubble.style = "align-self:flex-start; background:rgba(255,255,255,0.05); color:#d5d5d5; padding:10px 14px; border-radius:12px 12px 12px 0; max-width:85%; line-height:1.5;";
        messagesDiv.appendChild(aiBubble);

        // Zona 1: status orchestratore (piccola, aggiornata senza sovrascrivere il testo)
        const statusDiv = document.createElement('div');
        statusDiv.style = "font-size:11px; color:#a888ca; margin-bottom:8px; opacity:0.8; font-style:italic; min-height:16px;";
        aiBubble.appendChild(statusDiv);

        // Zona 2: risposta cumulativa (mai sovrascritta)
        const replyDiv = document.createElement('div');
        replyDiv.style = "white-space:pre-wrap; margin-top:4px;";
        aiBubble.appendChild(replyDiv);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullReply = "";
        let reasoningDiv = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split("\\n");
            
            for (const line of lines) {
                if (line.startsWith("data: ")) {
                    const dataStr = line.slice(6).trim();
                    if (dataStr === "[DONE]") continue;
                    try {
                        const data = JSON.parse(dataStr);
                        if (data.error) {
                            replyDiv.innerHTML = `<span style="color:#cf6f6f">Errore: ${data.error}</span>`;
                        } else if (data.stage === "context" || data.stage === "orchestrator") {
                            // Aggiorna solo il piccolo status — NON sovrascrive la risposta
                            statusDiv.textContent = data.content;
                        } else if (data.stage === "reasoning_start") {
                            reasoningDiv = document.createElement("div");
                            reasoningDiv.style = "font-size:11px; background:rgba(168,136,202,0.05); padding:8px; border-radius:6px; margin-bottom:8px; border-left:2px solid #a888ca; color:#aaa; font-style:italic;";
                            reasoningDiv.innerHTML = "<strong style='color:#a888ca; font-style:normal'>Analisi in corso:</strong><br>";
                            replyDiv.appendChild(reasoningDiv);
                        } else if (data.stage === "reasoning") {
                            if (reasoningDiv) reasoningDiv.innerHTML += data.content;
                        } else if (data.stage === "synthesis_start") {
                            statusDiv.style.opacity = "0.4"; // sfuma lo status quando parte la risposta
                        } else if (data.stage === "synthesis") {
                            fullReply += data.content;
                            if (fullReply.length > 0) statusDiv.style.display = 'none'; // nasconde status appena arriva testo
                            let formatted = fullReply.replace(/\*\*(.*?)\*\*/g, '<b>$1</b>').replace(/\\n/g, '<br>');
                            replyDiv.innerHTML = formatted;
                        }
                        messagesDiv.scrollTop = messagesDiv.scrollHeight;
                    } catch (e) { }
                }
            }
        }
        chatMsgHistory.push({"role": "ai", "content": fullReply});
    } catch (err) {
        if (loadingBubble) loadingBubble.remove();
        console.error(err);
        const errBubble = document.createElement('div');
        errBubble.style = "align-self:flex-start; background:rgba(207,111,111,0.1); color:#cf6f6f; padding:10px 14px; border-radius:12px; font-size:13px";
        errBubble.textContent = "Errore di connessione.";
        messagesDiv.appendChild(errBubble);
    }
}

window.fullSubtitle = {{ fullSubtitle | tojson | safe if fullSubtitle is defined else '""' }};
window.fullTimeline = {{ fullTimeline | tojson | safe if fullTimeline is defined else '""' }};

function showFullText(type) {
  const overlay = document.getElementById('full-text-overlay');
  const title = document.getElementById('overlay-title');
  const modalBody = document.getElementById('overlay-body');
  if(!overlay || !title || !modalBody) return;
  
  if(type === 'sub') {
    title.innerText = "Sottotitolo Completo";
    modalBody.innerText = window.fullSubtitle || "";
  } else {
    title.innerText = "Timeline Globale";
    modalBody.innerText = window.fullTimeline || "";
  }
  overlay.style.display = 'flex';
}
function closeFullText() {
  const overlay = document.getElementById('full-text-overlay');
  if(overlay) overlay.style.display = 'none';
}

const style = document.createElement('style');
style.innerHTML = `@keyframes pulse { 0% { opacity:0.4; } 100% { opacity:1; } }`;
document.head.appendChild(style);
</script>

<!-- Global Overlay for Full Text -->
<div id="full-text-overlay" class="full-text-overlay" onclick="closeFullText()">
  <div class="full-text-modal" onclick="event.stopPropagation()">
    <span class="close-overlay" onclick="closeFullText()">&times;</span>
    <h2 id="overlay-title" style="color:var(--accent); margin-top:0"></h2>
    <div id="overlay-body" style="white-space:pre-wrap; line-height:1.6; font-size:15px; color:#ddd"></div>
  </div>
</div>

</body>
</html>
"""

READER_LAYOUT = """
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} — {{ project_title }}</title>
<link href="https://fonts.googleapis.com/css2?family=Crimson+Pro:ital,wght@0,400;0,600;1,400&family=Special+Elite&family=Inter:wght@400;600&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #0c0c0d;
  --bg-sidebar: #0e0e10;
  --fg: #d5d5d5;
  --accent: #c9a96e; /* Oro invecchiato */
  --accent-glow: rgba(201, 169, 110, 0.4);
  --border: rgba(255,255,255,0.06);
  --nav-height: 65px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { 
  background-color: var(--bg);
  background-image: 
    radial-gradient(ellipse at 50% -20%, rgba(201, 169, 110, 0.05) 0%, transparent 80%),
    linear-gradient(rgba(12, 12, 13, 0.97), rgba(12, 12, 13, 0.97));
  color: var(--fg); 
  font-family: 'Inter', sans-serif; 
  -webkit-font-smoothing: antialiased;
}

/* Subtile Grain */
body::before {
  content: "";
  position: fixed; top: 0; left: 0; width: 100%; height: 100%;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 400 400' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E");
  opacity: 0.015;
  pointer-events: none;
  z-index: 9999;
}

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(201, 169, 110, 0.2); border-radius: 4px; }

.navbar {
  height: var(--nav-height);
  background: rgba(12, 12, 13, 0.9);
  backdrop-filter: blur(15px);
  border-bottom: 1px solid var(--border);
  position: fixed; top: 0; left: 0; right: 0;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 40px; z-index: 1000;
}
.nav-brand { 
  font-family: 'Special Elite', cursive;
  font-size: 16px; color: var(--accent); 
  letter-spacing: 2px; text-transform: uppercase;
}
.nav-links a { 
  color: var(--fg); text-decoration: none; font-size: 11px; margin-left: 25px; 
  opacity: 0.5; transition: 0.3s; letter-spacing: 2px;
  font-weight: 600; text-transform: uppercase;
}
.nav-links a:hover { opacity: 1; color: var(--accent); }

.reader-container {
  display: flex;
  margin-top: var(--nav-height);
  min-height: calc(100vh - var(--nav-height));
}
.sidebar {
  width: 280px;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border);
  position: fixed; top: var(--nav-height); bottom: 0;
  overflow-y: auto; padding: 40px 0;
}
.sidebar h3 { 
  font-family: 'Special Elite', cursive; font-size: 9px;
  text-transform: uppercase; color: var(--accent); 
  padding: 0 30px 25px; letter-spacing: 3px; opacity: 0.5; 
}
.cap-link {
  display: flex; align-items: center; gap: 15px;
  padding: 12px 30px;
  color: rgba(255,255,255,0.35);
  text-decoration: none; font-size: 13px;
  transition: all 0.2s;
}
.cap-link:hover { color: #fff; background: rgba(255,255,255,0.02); }
.cap-link.active { 
  color: var(--accent); 
  background: rgba(201, 169, 110, 0.08); 
  box-shadow: inset 3px 0 0 var(--accent);
}
.cap-link b { font-family: 'Special Elite', cursive; font-size: 11px; opacity: 0.4; width: 25px; }

.main-content {
  flex: 1;
  margin-left: 280px;
  display: flex; flex-direction: column;
  align-items: center;
  padding: 100px 40px;
}
article {
  max-width: 680px;
  width: 100%;
}
.chapter-meta { 
  font-family: 'Special Elite', cursive;
  font-size: 11px; color: var(--accent); 
  letter-spacing: 5px; text-transform: uppercase; 
  margin-bottom: 20px; text-align: center; opacity: 0.6;
}
h1.chapter-title { 
  font-family: 'Crimson Pro', serif; 
  font-size: 48px; font-weight: 400; font-style: italic;
  text-align: center; margin-bottom: 80px;
  color: #fff; letter-spacing: -0.5px;
}
.chapter-text {
  font-family: 'Crimson Pro', serif;
  font-size: 21px; line-height: 1.75;
  color: #c0c0c0;
}
.chapter-text p { margin-bottom: 1.8em; text-indent: 1.8em; text-align: justify; }
.chapter-text p:first-of-type { text-indent: 0; }

.pagination {
  margin-top: 100px; padding-top: 40px;
  display: flex; justify-content: center; align-items: center; gap: 40px;
  border-top: 1px solid var(--border); width: 100%;
}
.pg-btn {
  font-family: 'Special Elite', cursive; font-size: 12px;
  color: var(--accent); text-decoration: none;
  opacity: 0.5; transition: 0.3s; letter-spacing: 2px;
}
.pg-btn:hover:not(.disabled) { opacity: 1; text-shadow: 0 0 10px var(--accent-glow); }
.pg-btn.disabled { opacity: 0.05; cursor: default; }
.pg-info { font-family: 'Special Elite', cursive; font-size: 10px; opacity: 0.3; }

footer {
  margin-top: auto; padding: 80px 40px;
  text-align: center; font-size: 9px;
  opacity: 0.2; letter-spacing: 4px;
  text-transform: uppercase;
}

/* Scroll Buttons */
.page-scrollers {
  position: fixed; bottom: 30px; left: 310px;
  display: flex; flex-direction: column; gap: 10px; z-index: 900;
}
.scroll-btn {
  width: 44px; height: 44px; border-radius: 50%;
  background: rgba(12, 12, 13, 0.9); border: 1px solid var(--border);
  color: var(--accent); font-family: 'Inter', sans-serif; font-size: 18px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; opacity: 0.6; transition: 0.3s;
  box-shadow: 0 5px 15px rgba(0,0,0,0.5);
}
.scroll-btn:hover { opacity: 1; border-color: var(--accent); transform: scale(1.05); }

/* Contact Styles */
.contact-grid { display: grid; grid-template-columns: 1fr 300px; gap: 40px; width: 100%; max-width: 1000px; }
.card { background: rgba(255,255,255,0.01); border: 1px solid var(--border); padding: 50px; border-radius: 4px; }
.form-group { margin-bottom: 30px; }
.form-group label { 
  display: block; font-family: 'Special Elite', cursive; font-size: 10px; 
  color: var(--accent); margin-bottom: 12px; letter-spacing: 2px;
}
.form-group input, .form-group textarea { 
  width: 100%; background: transparent; border: none; border-bottom: 1px solid #222; 
  color: #fff; padding: 12px 0; font-family: inherit; font-size: 16px; transition: 0.3s;
}
.form-group input:focus, .form-group textarea:focus { border-color: var(--accent); outline: none; }
.btn-submit { 
  background: var(--accent); color: #000; border: none; padding: 12px 40px; 
  font-family: 'Special Elite', cursive; font-size: 12px; cursor: pointer; transition: 0.3s;
}
.btn-submit:hover { background: #fff; }

@media (max-width: 900px) {
  .sidebar { display: none; }
  .main-content { margin-left: 0; padding: 60px 24px; }
  h1.chapter-title { font-size: 34px; }
  .chapter-text { font-size: 19px; }
  .navbar { padding: 0 20px; }
  .page-scrollers { left: 20px; bottom: 20px; }
}

/* Accordion Styles */
.meta-accordion {
  width: 100%;
  max-width: 680px;
  margin: 0 auto 60px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255,255,255,0.02);
  overflow: hidden;
}
.meta-item {
  border-bottom: 1px solid var(--border);
}
.meta-item:last-child { border-bottom: none; }
.meta-header {
  padding: 15px 25px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-family: 'Special Elite', cursive;
  font-size: 11px;
  color: var(--accent);
  letter-spacing: 2px;
  text-transform: uppercase;
  transition: background 0.3s;
  user-select: none;
}
.meta-header:hover { background: rgba(201, 169, 110, 0.05); }
.meta-header::after {
  content: '+';
  font-family: 'Inter', sans-serif;
  font-size: 18px;
  font-weight: 300;
  transition: transform 0.3s;
}
.meta-item.active .meta-header::after { transform: rotate(45deg); }
.meta-content {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.4s cubic-bezier(0, 1, 0, 1);
  padding: 0 25px;
  font-size: 14px;
  line-height: 1.6;
  color: #aaa;
}
.meta-item.active .meta-content {
  max-height: 1000px;
  transition: max-height 1s ease-in-out;
  padding: 0 25px 25px;
}
.meta-block { margin-top: 15px; }
.meta-label { 
  display: block; font-family: 'Special Elite', cursive; font-size: 9px; 
  color: var(--accent); opacity: 0.6; margin-bottom: 5px; letter-spacing: 1px;
}
</style>
<script>
function toggleMeta(el) {
  const item = el.parentElement;
  item.classList.toggle('active');
}
</script>
</head>
<body>
<nav class="navbar">
  <div class="nav-brand">{{ project_title }}</div>
  <div class="nav-links">
    <a href="/">BIBLIOTECA</a>
    <a href="/contatti">CONTATTI</a>
    <a href="/admin">ADMIN</a>
  </div>
</nav>

<div class="reader-container">
  <aside class="sidebar">
    <h3>Indice Archivio</h3>
    {{ all_caps_sidebar | safe }}
  </aside>
  
  <main class="main-content">
    <article>
        {{ content | safe }}
    </article>
    
    <!-- Floating Scroll Buttons -->
    <div class="page-scrollers">
      <button class="scroll-btn" onclick="window.scrollTo({top: 0, behavior: 'smooth'})" title="Torna in Cima">↑</button>
      <button class="scroll-btn" onclick="window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})" title="Vai in Fondo">↓</button>
    </div>

    <footer>
      &copy; 2026 — {{ project_title }} — Sistema di Lettura Archivio
    </footer>
  </main>
</div>

<!-- ================= AI CHAT OVERLAY (Frontend) ================= -->
<div id="ai-chat-widget" style="position:fixed; bottom:30px; right:30px; z-index:9999; font-family:'Inter', sans-serif;">
  
  <!-- Icona Bottone Chiuso -->
  <button id="ai-chat-btn" onclick="toggleAIChat()" style="width:60px; height:60px; border-radius:50%; background:var(--bg-sidebar); border:2px solid var(--accent); color:var(--accent); font-size:24px; cursor:pointer; box-shadow:0 10px 25px rgba(0,0,0,0.8); display:flex; align-items:center; justify-content:center; transition:transform 0.3s; padding:0">
    <span style="font-family:'Special Elite', cursive; font-size:12px; font-weight:bold; letter-spacing:1px; line-height:1">AI</span>
  </button>
  
  <!-- Finestra Aperta -->
  <div id="ai-chat-window" style="display:none; position:absolute; bottom:80px; right:0; width:350px; height:500px; background:rgba(12,12,13,0.95); backdrop-filter:blur(10px); border:1px solid var(--accent); border-radius:12px; box-shadow:0 15px 40px rgba(0,0,0,0.9); flex-direction:column; overflow:hidden;">
    
    <!-- Testata -->
    <div style="background:rgba(201, 169, 110, 0.1); border-bottom:1px solid rgba(201,169,110,0.3); padding:15px; display:flex; justify-content:space-between; align-items:center;">
      <div>
        <h4 style="color:var(--accent); margin:0; font-family:'Special Elite', cursive; font-size:13px; text-transform:uppercase; letter-spacing:1px">Guida Archivio</h4>
        <span style="font-size:10px; color:var(--muted); font-family:'Inter', sans-serif;">Niente Spoiler oltre questo punto</span>
      </div>
      <button onclick="toggleAIChat()" style="background:transparent; border:none; color:var(--accent); font-size:20px; cursor:pointer; padding:0; line-height:1">&times;</button>
    </div>
    
    <!-- Area Messaggi -->
    <div id="ai-chat-messages" style="flex:1; overflow-y:auto; padding:15px; display:flex; flex-direction:column; gap:12px; font-size:13px; scrollbar-width: thin; scrollbar-color: var(--accent) transparent;">
      <div style="text-align:center; padding:10px; font-size:11px; opacity:0.5; color:var(--muted); border-bottom:1px solid rgba(255,255,255,0.05); margin-bottom:10px">Inizio Conversazione. La Guida conosce il Canone e gli eventi narrati fino al capitolo che stai leggendo.</div>
      <div style="align-self:flex-start; background:rgba(255,255,255,0.05); color:#d5d5d5; padding:10px 14px; border-radius:12px 12px 12px 0; max-width:85%; line-height:1.5;">Salve Viaggiatore. Sono la voce dell'Archivio. Come posso esserti utile per comprendere o riassumere ciò che hai letto finora?</div>
    </div>
    
    <!-- Area Input -->
    <div style="padding:15px; border-top:1px solid var(--border); display:flex; gap:10px; background:rgba(0,0,0,0.3)">
      <input type="text" id="ai-chat-input" placeholder="Chiedi qualcosa sul capitolo..." style="flex:1; background:transparent; border:none; color:#fff; font-family:'Inter', sans-serif; font-size:13px; padding:8px 0;" onkeypress="if(event.key==='Enter') sendAIChatMessage()">
      <button onclick="sendAIChatMessage()" style="background:transparent; border:none; color:var(--accent); cursor:pointer; font-weight:600; text-transform:uppercase; font-size:11px; letter-spacing:1px">Invia</button>
    </div>
  </div>
</div>

<script>
let chatMsgHistory = [];

function toggleAIChat() {
    const win = document.getElementById('ai-chat-window');
    const btn = document.getElementById('ai-chat-btn');
    if (win.style.display === 'none') {
        win.style.display = 'flex';
        btn.style.transform = 'scale(0.9)';
        setTimeout(() => document.getElementById('ai-chat-input').focus(), 100);
    } else {
        win.style.display = 'none';
        btn.style.transform = 'scale(1)';
    }
}

async function sendAIChatMessage() {
    const input = document.getElementById('ai-chat-input');
    const text = input.value.trim();
    if (!text) return;
    
    const messagesDiv = document.getElementById('ai-chat-messages');
    
    // Mostra messaggio utente
    const userBubble = document.createElement('div');
    userBubble.style = "align-self:flex-end; background:var(--accent); color:#000; padding:10px 14px; border-radius:12px 12px 0 12px; max-width:85%; line-height:1.5;";
    userBubble.textContent = text;
    messagesDiv.appendChild(userBubble);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    
    input.value = '';
    
    // Mostra indicator loading a 3 pallini
    const loadingBubble = document.createElement('div');
    loadingBubble.id = 'ai-chat-loading';
    loadingBubble.style = "align-self:flex-start; background:rgba(255,255,255,0.05); color:var(--accent); padding:10px 14px; border-radius:12px 12px 12px 0; font-size:16px; letter-spacing:2px; animation: pulse 1s infinite alternate";
    loadingBubble.textContent = "● ● ●";
    messagesDiv.appendChild(loadingBubble);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    
    // Trova l'ID del capitolo dalla URL (se è /read/X)
    let capIdStr = window.location.pathname.split('/')[2];
    let capId = parseInt(capIdStr);
    if (isNaN(capId)) capId = 1; // Default
    
    // Aggiungi alla history 
    chatMsgHistory.push({"role": "user", "content": text});
    
    try {
        const response = await fetch(`/api/chat/${capId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text, admin_mode: false, stream: true, history: chatMsgHistory })
        });

        if (loadingBubble) loadingBubble.remove();
        
        const aiBubble = document.createElement('div');
        aiBubble.style = "align-self:flex-start; background:rgba(255,255,255,0.05); color:#d5d5d5; padding:10px 14px; border-radius:12px 12px 12px 0; max-width:85%; line-height:1.5;";
        messagesDiv.appendChild(aiBubble);

        // Zona 1: status orchestratore (aggiornato in place, non sovrascrive la risposta)
        const statusDiv = document.createElement('div');
        statusDiv.style = "font-size:11px; color:var(--accent); margin-bottom:8px; opacity:0.7; font-style:italic; min-height:16px;";
        aiBubble.appendChild(statusDiv);

        // Zona 2: risposta cumulativa della Guida
        const replyDiv = document.createElement('div');
        replyDiv.style = "white-space:pre-wrap; margin-top:4px;";
        aiBubble.appendChild(replyDiv);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullReply = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split("\\n");
            
            for (const line of lines) {
                if (line.startsWith("data: ")) {
                    const dataStr = line.slice(6).trim();
                    if (dataStr === "[DONE]") continue;
                    try {
                        const data = JSON.parse(dataStr);
                        if (data.error) {
                            replyDiv.innerHTML = `<span style="color:#cf6f6f">Il varco narrativo è interrotto. Errore: ${data.error}</span>`;
                        } else if (data.stage === "context" || data.stage === "orchestrator") {
                            // Aggiorna solo lo status — NON sovrascrive la risposta cumulativa
                            statusDiv.textContent = data.content;
                        } else if (data.stage === "synthesis") {
                            fullReply += data.content;
                            if (fullReply.length > 0) statusDiv.style.display = 'none';
                            let formatted = fullReply.replace(/\*\*(.*?)\*\*/g, '<b>$1</b>').replace(/\\n/g, '<br>');
                            replyDiv.innerHTML = formatted;
                        }
                        messagesDiv.scrollTop = messagesDiv.scrollHeight;
                    } catch (e) { }
                }
            }
        }
        chatMsgHistory.push({"role": "ai", "content": fullReply});
    } catch (err) {
        if (loadingBubble) loadingBubble.remove();
        console.error(err);
        const errBubble = document.createElement('div');
        errBubble.style = "align-self:flex-start; background:rgba(207,111,111,0.1); color:#cf6f6f; padding:10px 14px; border-radius:12px; font-size:13px";
        errBubble.textContent = "Il varco narrativo è interrotto.";
        messagesDiv.appendChild(errBubble);
    }
}
// Add simple keyframe for loading pulse
const style = document.createElement('style');
style.innerHTML = `@keyframes pulse { 0% { opacity:0.4; } 100% { opacity:1; } }`;
document.head.appendChild(style);
</script>
</body>
</html>
"""

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form["username"] == ADMIN_USER and request.form["password"] == ADMIN_PASS:
            session["logged_in"] = True
            if request.form.get("remember"):
                session.permanent = True
            return redirect(request.args.get("next") or url_for("admin_dashboard"))
        else:
            error = "Credenziali non valide."
            
    p_title = get_project_title()
    p_subtitle = get_env_var('PROJECT_SUBTITLE', '')
    
    # Troncamento per la pagina di login per evitare overflow
    disp_title = (p_title[:40] + "...") if len(p_title) > 40 else p_title
    disp_sub = (p_subtitle[:100] + "...") if len(p_subtitle) > 100 else p_subtitle

    body = f"""
    <div style="max-width:440px;margin:80px auto;padding:30px;background:var(--card);border:1px solid var(--border);border-radius:12px;box-shadow:0 20px 50px rgba(0,0,0,0.3)">
      <h1 style="color:var(--accent);font-size:22px;text-align:center;margin-bottom:8px" title="{p_title}">{disp_title}</h1>
      <p style="text-align:center; color:var(--muted); font-size:12px; margin-bottom:24px; line-height:1.4">{disp_sub}</p>
      
      {'<div class="msg err">'+error+'</div>' if error else ''}
      <form method="POST">
        <div class="field">
          <label>Username</label>
          <input type="text" name="username" required>
        </div>
        <div class="field">
          <label>Password</label>
          <div style="display:flex; gap:8px;">
            <input type="password" name="password" id="pass_input" required style="flex:1">
            <button type="button" class="btn" style="padding:0 12px;cursor:pointer" onclick="let i=document.getElementById('pass_input'); i.type=(i.type==='password'?'text':'password');">👁️</button>
          </div>
        </div>
        <div style="margin-bottom:20px;display:flex;align-items:center;gap:8px;font-size:13px">
          <input type="checkbox" name="remember" id="remember" value="yes">
          <label for="remember" style="margin:0;color:var(--muted);cursor:pointer;user-select:none">Resta collegato (Salva password)</label>
        </div>
        <button type="submit" class="btn btn-primary" style="width:100%;justify-content:center;padding:12px;font-size:14px;font-weight:600">ENTRA NEL SISTEMA</button>
      </form>
    </div>
    """
    
    html = f"""
    <!DOCTYPE html><html lang="it"><head><meta charset="UTF-8"><title>Login — {p_title[:20]}</title>
    <style>{BASE_CSS}</style></head>
    <body style="display:flex;align-items:center;justify-content:center;height:100vh;background:#050505">
      {body}
    </body></html>
    """
    return render_template_string(html)

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for('login'))

@app.route("/")
def public_reader_home():
    caps = get_all()
    if not caps: return "Nessun capitolo trovato", 404
    return redirect(url_for('public_read_cap', cap_id=caps[0]['id']))

@app.route("/read/<int:cap_id>")
@app.route("/read/<int:cap_id>/<int:page_num>")
def public_read_cap(cap_id, page_num=1):
    cap = get_cap(cap_id)
    if not cap: return "Capitolo non trovato", 404
    testo = read_txt(cap_id)
    pages = get_paginated_text(testo)
    
    if page_num < 1: page_num = 1
    if page_num > len(pages): page_num = len(pages)
    
    content = pages[page_num - 1]
    # Formattazione paragrafi per una lettura pulita
    content_html = "".join(f"<p>{p.strip()}</p>" for p in content.split("\n\n") if p.strip())
    
    sidebar_html = get_sidebar_html(active_id=cap_id, is_admin=False)
    
    # Paginazione interna al capitolo (CIMA e FONDO)
    pagination_html = ""
    if len(pages) > 1:
        prev_class = "" if page_num > 1 else "disabled"
        next_class = "" if page_num < len(pages) else "disabled"
        prev_url = url_for('public_read_cap', cap_id=cap_id, page_num=page_num-1) if page_num > 1 else "#"
        next_url = url_for('public_read_cap', cap_id=cap_id, page_num=page_num+1) if page_num < len(pages) else "#"
        mid_url = url_for('public_read_cap', cap_id=cap_id, page_num=max(1, len(pages)//2))
        
        # Pagina a libro: ← Pagina Precedente | Centra | Pagina Successiva →
        pagination_html = f"""
        <div class="pagination">
            <a href="{prev_url}" class="pg-btn {prev_class}" id="btn-prev">← Precedente</a>
            <a href="{mid_url}" class="pg-btn" title="Vai a metà capitolo">Metà Capitolo</a>
            <span class="pg-info">Pagina {page_num} di {len(pages)}</span>
            <a href="{next_url}" class="pg-btn {next_class}" id="btn-next">Successiva →</a>
        </div>
        """

    # Accordion Metadati per il Lettore
    def format_meta_text(text):
        if not text: return "Non specificato."
        return text.replace("\n", "<br>")

    meta_accordion_html = f"""
    <div class="meta-accordion">
        <div class="meta-item">
            <div class="meta-header" onclick="toggleMeta(this)">Note di Archivio</div>
            <div class="meta-content">
                <div class="meta-block">
                    <span class="meta-label">Sinossi Strategica</span>
                    {format_meta_text(cap.get('riassunto'))}
                </div>
                <div class="meta-block">
                    <span class="meta-label">Scenario e Atmosfera</span>
                    {cap.get('data_narrativa', 'N/D')} &middot; {cap.get('luogo', 'N/D')} ({cap.get('luogo_macro', 'N/D')})<br>
                    Tensione: {cap.get('tensione_capitolo', 'Standard')}
                </div>
                <div class="meta-block">
                    <span class="meta-label">Personaggi in Scena</span>
                    {format_meta_text(cap.get('personaggi_capitolo'))}
                </div>
                <div class="meta-block">
                    <span class="meta-label">Oggetti Simbolo</span>
                    {cap.get('oggetti_simbolo', 'Nessuno')}
                </div>
                <div class="meta-block">
                    <span class="meta-label">Sviluppo Scenico (Outline)</span>
                    {format_meta_text(cap.get('scene_outline'))}
                </div>
            </div>
        </div>
    </div>
    """

    # JavaScript per le Swipe Gesture e Transizioni
    # JavaScript per le Swipe Gesture e Transizioni SPA-like
    # JavaScript per le Swipe Gesture e Transizioni SPA-like
    swipe_js = """
    <style>
      /* --- TRANSIZIONI CAPITOLO (Fade/Slide Morbido) --- */
      .chapter-transition-in { animation: chapterFadeIn 0.5s ease-out forwards; }
      @keyframes chapterFadeIn {
         0% { opacity: 0; transform: translateY(20px); }
         100% { opacity: 1; transform: translateY(0); }
      }
      .chapter-transition-out { animation: chapterFadeOut 0.4s ease-in forwards; }
      @keyframes chapterFadeOut {
         0% { opacity: 1; transform: translateY(0); }
         100% { opacity: 0; transform: translateY(-20px); }
      }

      /* --- TRANSIZIONI PAGINA (Effetto Libro 3D) --- */
      .page-flip-container {
          perspective: 1200px; /* Necessario per il 3D */
      }
      
      /* Pagina Successiva (Sfoglia in avanti - Da Destra a Sinistra) */
      .page-flip-out-left {
          transform-origin: left center;
          animation: flipOutLeft 0.5s ease-in forwards;
      }
      @keyframes flipOutLeft {
          0% { transform: rotateY(0deg); opacity: 1; }
          40% { opacity: 1; }
          100% { transform: rotateY(-90deg); opacity: 0; }
      }
      .page-flip-in-right {
          transform-origin: right center;
          animation: flipInRight 0.5s ease-out forwards;
      }
      @keyframes flipInRight {
          0% { transform: rotateY(90deg); opacity: 0; }
          60% { opacity: 1; }
          100% { transform: rotateY(0deg); opacity: 1; }
      }

      /* Pagina Precedente (Sfoglia all'indietro - Da Sinistra a Destra) */
      .page-flip-out-right {
          transform-origin: right center;
          animation: flipOutRight 0.5s ease-in forwards;
      }
      @keyframes flipOutRight {
          0% { transform: rotateY(0deg); opacity: 1; }
          40% { opacity: 1; }
          100% { transform: rotateY(90deg); opacity: 0; }
      }
      .page-flip-in-left {
          transform-origin: left center;
          animation: flipInLeft 0.5s ease-out forwards;
      }
      @keyframes flipInLeft {
          0% { transform: rotateY(-90deg); opacity: 0; }
          60% { opacity: 1; }
          100% { transform: rotateY(0deg); opacity: 1; }
      }
      
      /* Overlay Lading */
      #loading-overlay {
          position: fixed; top:0; left:0; width:100%; height:100%; 
          background: rgba(12, 12, 13, 0.7); backdrop-filter: blur(5px);
          z-index: 9999; display: none; align-items: center; justify-content: center;
          color: var(--accent); font-family: 'Special Elite', cursive; font-size: 14px;
      }
      .loader {
          border: 2px solid rgba(201, 169, 110, 0.2);
          border-left-color: var(--accent);
          border-radius: 50%; width: 40px; height: 40px;
          animation: spin 1s linear infinite; margin-bottom: 15px;
      }
      @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
    
    <div id="loading-overlay">
        <div style="text-align:center;">
            <div class="loader"></div>
            <div>Sfoglio le pagine...</div>
        </div>
    </div>

    <script>
        document.addEventListener('DOMContentLoaded', function() {
            let touchstartX = 0;
            let touchendX = 0;
            const threshold = 50; 
            
            function getContainer() { return document.getElementById('chapter-content-body'); }
            
            // Abilita la prospettiva 3D sul parent del testo
            getContainer().parentElement.classList.add('page-flip-container');
            
            function parseUrlPath(urlstr) {
                try {
                    return new URL(urlstr, window.location.origin).pathname;
                } catch(e) { return urlstr; }
            }

            function animateAndFetch(url, actionType) {
                if(!url || url === '#' || url === window.location.href) return;
                
                const container = getContainer();
                const overlay = document.getElementById('loading-overlay');
                
                let outAnim = "";
                let inAnim = "";
                
                // Determina l'animazione in base al tipo di azione
                if(actionType === 'page_next') {
                    outAnim = 'page-flip-out-left';
                    inAnim = 'page-flip-in-right';
                } else if(actionType === 'page_prev') {
                    outAnim = 'page-flip-out-right';
                    inAnim = 'page-flip-in-left';
                } else {
                    // Cambio Capitolo o click dalla sidebar
                    outAnim = 'chapter-transition-out';
                    inAnim = 'chapter-transition-in';
                }
                
                // 1. Avvia animazione di uscita
                container.style.animation = "none"; // reset
                container.offsetHeight; // force reflow
                
                container.classList.add(outAnim);
                
                // 2. Mostra Loader se la rete è lenta
                const loaderTimeout = setTimeout(() => { overlay.style.display = 'flex'; }, 400); // Ritardato un po' di più per non coprire l'animazione 3D
                
                // 3. Esegui Fetch
                fetch(url)
                .then(r => r.text())
                .then(html => {
                    clearTimeout(loaderTimeout);
                    overlay.style.display = 'none';
                    
                    const parser = new DOMParser();
                    const doc = parser.parseFromString(html, 'text/html');
                    
                    const newContent = doc.getElementById('chapter-content-body');
                    const newPaginationTops = doc.querySelectorAll('.pagination');
                    const newSidebar = doc.querySelector('.sidebar');
                    const newTitleInfo = doc.querySelector('title');
                    const newChapterTitle = doc.querySelector('.chapter-title');
                    const newChapterMeta = doc.querySelector('.chapter-meta');
                    const newAccordion = doc.querySelector('.meta-accordion');
                    
                    if(newContent) {
                        window.history.pushState({path: url}, '', url);
                        
                        container.innerHTML = newContent.innerHTML;
                        
                        if(newSidebar && document.querySelector('.sidebar')) document.querySelector('.sidebar').innerHTML = newSidebar.innerHTML;
                        if(newTitleInfo) document.title = newTitleInfo.innerText;
                        if(newChapterTitle) document.querySelector('.chapter-title').innerHTML = newChapterTitle.innerHTML;
                        if(newChapterMeta) document.querySelector('.chapter-meta').innerHTML = newChapterMeta.innerHTML;
                        
                        const currentPaginations = document.querySelectorAll('.pagination');
                        if(currentPaginations.length >= 2 && newPaginationTops.length >= 2) {
                            currentPaginations[0].innerHTML = newPaginationTops[0].innerHTML;
                            currentPaginations[1].innerHTML = newPaginationTops[1].innerHTML;
                        }
                        
                        if(newAccordion && document.querySelector('.meta-accordion')) {
                            document.querySelector('.meta-accordion').innerHTML = newAccordion.innerHTML;
                        }

                        attachAjaxLinks();

                        // 4. Avvia animazione di entrata
                        container.classList.remove(outAnim); // Remove old class
                        container.style.animation = "none"; // reset inline styles
                        container.offsetHeight; // force reflow
                        container.className = "chapter-text " + inAnim; // Apply new class
                        
                        window.scrollTo({ top: 0, behavior: 'smooth' });
                    } else {
                        window.location.href = url;
                    }
                })
                .catch(err => {
                    console.error("AJAX Fetch failed", err);
                    window.location.href = url;
                });
            }

            function handleGesture() {
                if (touchendX < touchstartX - threshold) {
                    let nextBtn = document.getElementById('btn-next');
                    if(nextBtn && !nextBtn.classList.contains('disabled')) {
                       // Swipe = Cambio Pagina (Mantenere stesso capitolo se possibile)
                       // Idealmente sappiamo se è page_next se l'URL ha lo stesso cap_id, ma per semplificare lo swipe e' sempre girare pagina
                       animateAndFetch(nextBtn.href, 'page_next');
                    }
                }
                if (touchendX > touchstartX + threshold) {
                    let prevBtn = document.getElementById('btn-prev');
                    if(prevBtn && !prevBtn.classList.contains('disabled')) {
                        animateAndFetch(prevBtn.href, 'page_prev');
                    }
                }
            }
            
            function isSameChapter(url1, url2) {
               // Path pattern is usually /read/<cap_id> or /read/<cap_id>/<page>
               const p1 = parseUrlPath(url1).split('/');
               const p2 = parseUrlPath(url2).split('/');
               // pX[2] is cap_id
               if(p1.length > 2 && p2.length > 2) return p1[2] === p2[2];
               return false;
            }
            
            function attachAjaxLinks() {
                document.querySelectorAll('.pg-btn, .cap-link').forEach(link => {
                    const newLink = link.cloneNode(true);
                    link.parentNode.replaceChild(newLink, link);
                    
                    newLink.addEventListener('click', function(e) {
                         if(this.classList.contains('disabled')) { e.preventDefault(); return; }
                         
                         const targetUrl = this.href;
                         if(!targetUrl || !targetUrl.includes('/read')) return;
                         
                         e.preventDefault();
                         
                         let actionObj = 'chapter_change'; // Default
                         
                         // Se è un bottone di paginazione, determiniamo se è 'page_next' o 'page_prev'
                         if(this.classList.contains('pg-btn')) {
                            // Controlla se cambiamo capitolo o solo pagina
                            if(isSameChapter(window.location.href, targetUrl)) {
                                if(this.id.includes('next')) actionObj = 'page_next';
                                else if(this.id.includes('prev')) actionObj = 'page_prev';
                            }
                         }
                         
                         animateAndFetch(targetUrl, actionObj);
                    });
                });
            }

            // Init listeners
            document.addEventListener('touchstart', e => { touchstartX = e.changedTouches[0].screenX; }, {passive: true});
            document.addEventListener('touchend', e => { touchendX = e.changedTouches[0].screenX; handleGesture(); }, {passive: true});
            
            window.addEventListener('popstate', function() { window.location.reload(); });

            // Avvio Prima volta
            getContainer().className = "chapter-text chapter-transition-in";
            attachAjaxLinks();
        });
    </script>
    """

    full_content = f"""
    <div class="chapter-meta">Capitolo {cap_id}</div>
    <h1 class="chapter-title">{cap['titolo']}</h1>
    
    {meta_accordion_html}

    <!-- Paginazione CIMA -->
    <div style="margin-bottom: 60px; border-top: none; padding-top: 0; border-bottom: 1px solid var(--border); padding-bottom: 30px; margin-top:0;" class="pagination">
        <a href="{prev_url if 'prev_url' in locals() else '#'}" class="pg-btn {prev_class if 'prev_class' in locals() else 'disabled'}" id="btn-prev-top">← Precedente</a>
        <a href="{mid_url if 'mid_url' in locals() else '#'}" class="pg-btn" title="Vai a metà capitolo">Metà</a>
        <span class="pg-info">Pagina {page_num} di {len(pages)}</span>
        <a href="{next_url if 'next_url' in locals() else '#'}" class="pg-btn {next_class if 'next_class' in locals() else 'disabled'}" id="btn-next-top">Successiva →</a>
    </div>

    <div class="chapter-text" id="chapter-content-body">
        {content_html}
    </div>
    
    <!-- Paginazione FONDO -->
    {pagination_html}
    {swipe_js}
    """
    
    return render_template_string(READER_LAYOUT, 
        title=cap['titolo'],
        content=full_content,
        all_caps_sidebar=sidebar_html,
        project_title=get_project_title())

@app.route("/contatti", methods=["GET", "POST"])
def public_contacts():
    ui = load_ui_settings()
    msg_sent = request.args.get('sent') == '1'
    
    donation_html = ""
    for d in ui.get('donation_links', []):
        donation_html += f"""
        <div class="donation-item">
            <a href="{d['url']}" target="_blank">{d['label']}</a>
            <p>{d['desc']}</p>
        </div>
        """
    
    form_html = f"""
    <div class="contact-grid">
        <div class="card">
            <h2 style="color:var(--accent); font-family:'Crimson Pro',serif; font-size:32px; margin-bottom:20px">Contattaci</h2>
            {f'<div style="background:#1a2e1a; color:#6fcf6f; padding:15px; border-radius:8px; margin-bottom:20px">{ui.get("contact_success")}</div>' if msg_sent else f'<p style="margin-bottom:30px; opacity:0.8">{ui.get("contact_intro")}</p>'}
            
            <form action="/api/contatti" method="POST">
                <div class="form-group">
                    <label>Nome</label>
                    <input type="text" name="nome" placeholder="Il tuo nome" required>
                </div>
                <div class="form-group">
                    <label>Email</label>
                    <input type="email" name="email" placeholder="la-tua@email.com" required>
                </div>
                <div class="form-group">
                    <label>Messaggio</label>
                    <textarea name="messaggio" placeholder="Scrivi qui il tuo messaggio..." required></textarea>
                </div>
                <button type="submit" class="btn-submit">Invia Messaggio</button>
            </form>
        </div>
        
        <div class="card donation-card">
            <h2 style="color:var(--accent); font-family:'Inter',serif; font-size:18px; text-transform:uppercase; letter-spacing:1px; margin-bottom:24px">Supporta l'Opera</h2>
            {donation_html if donation_html else '<p style="font-size:13px; opacity:0.5">Nessun metodo di donazione configurato.</p>'}
        </div>
    </div>
    """
    
    sidebar_html = get_sidebar_html(is_admin=False)

    return render_template_string(READER_LAYOUT,
        title="Contatti & Supporto",
        content=form_html,
        all_caps_sidebar=sidebar_html,
        project_title=get_project_title())

@app.route("/api/contatti", methods=["POST"])
def api_contatti():
    nome = request.form.get('nome')
    email = request.form.get('email')
    messaggio = request.form.get('messaggio')
    
    if nome and email and messaggio:
        conn = get_conn()
        conn.execute("INSERT INTO contatti (nome, email, messaggio) VALUES (?, ?, ?)", (nome, email, messaggio))
        conn.commit()
        conn.close()
        return redirect(url_for('public_contacts', sent=1))
    return "Dati mancanti", 400

@app.route("/admin/contatti")
@login_required
def admin_contatti():
    conn = get_conn()
    messages = conn.execute("SELECT * FROM contatti ORDER BY data_invio DESC").fetchall()
    conn.close()
    
    rows_html = ""
    for m in messages:
        rows_html += f"""
        <div class="card" style="margin-bottom:12px; border-left: 4px solid var(--accent)">
            <div style="display:flex; justify-content:space-between; margin-bottom:8px">
                <strong style="color:var(--accent)">{m['nome']} ({m['email']})</strong>
                <span style="font-size:11px; opacity:0.5">{m['data_invio']}</span>
            </div>
            <div style="white-space:pre-wrap; font-size:13px">{m['messaggio']}</div>
        </div>
        """
    
    body = f"""
    <div class="topbar">
      <h1>Messaggi Ricevuti</h1>
      <div class="actions">
        <a href="/admin" class="btn">← Dashboard</a>
      </div>
    </div>
    <div class="content">
        {rows_html if rows_html else '<p style="text-align:center; padding:40px; opacity:0.5">Nessun messaggio ricevuto.</p>'}
    </div>
    """
    
    caps = get_all()
    all_caps_html = "".join(f'<a href="/cap/{c["id"]}" class="cap-link"><span class="cap-num">{c["id"]:02d}</span><span>{c["titolo"]}</span></a>' for c in caps)
    
    return render_template_string(ADMIN_LAYOUT, title="Messaggi Admin", content=body, all_caps_html=all_caps_html, project_title=get_project_title())

@app.route("/api/lmstudio/discover")
@login_required
def api_lmstudio_discover():
    base_url = request.args.get("url", get_env_var("LMSTUDIO_URL", "http://192.168.1.51:1234"))
    api_key = request.args.get("key", get_env_var("LMSTUDIO_API_KEY", ""))
    try:
        import llm_client
        models = llm_client.get_lmstudio_models(base_url, api_key=api_key)
        return jsonify({"status": "success", "models": models})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/lmstudio/test")
@login_required
def api_lmstudio_test():
    base_url = request.args.get("url", get_env_var("LMSTUDIO_URL", "http://192.168.1.51:1234"))
    api_key = request.args.get("key", get_env_var("LMSTUDIO_API_KEY", ""))
    try:
        import requests
        headers = {}
        if api_key: headers["Authorization"] = f"Bearer {api_key}"
        r = requests.get(f"{base_url}/v1/models", headers=headers, timeout=5)
        r.raise_for_status()
        return jsonify({"status": "success", "message": "Connessione riuscita!"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Errore: {str(e)}"}), 500

@app.route("/api/ollama/discover")
@login_required
def api_ollama_discover():
    base_url = request.args.get("url", get_env_var("OLLAMA_URL", "http://127.0.0.1:11434"))
    try:
        models = provider_discover_models("ollama", base_url=base_url)
        return jsonify({"status": "success", "models": models})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/ollama/test")
@login_required
def api_ollama_test():
    base_url = request.args.get("url", get_env_var("OLLAMA_URL", "http://127.0.0.1:11434"))
    try:
        result = provider_test_provider("ollama", base_url=base_url)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Errore: {str(e)}"}), 500

@app.route("/api/openai-compatible/discover")
@login_required
def api_openai_compatible_discover():
    base_url = request.args.get("url", get_env_var("OPENAI_COMPATIBLE_URL", ""))
    api_key = request.args.get("key", get_env_var("OPENAI_COMPATIBLE_API_KEY", ""))
    try:
        models = provider_discover_models("openai_compatible", base_url=base_url, api_key=api_key)
        return jsonify({"status": "success", "models": models})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/openai-compatible/test")
@login_required
def api_openai_compatible_test():
    base_url = request.args.get("url", get_env_var("OPENAI_COMPATIBLE_URL", ""))
    api_key = request.args.get("key", get_env_var("OPENAI_COMPATIBLE_API_KEY", ""))
    try:
        result = provider_test_provider("openai_compatible", base_url=base_url, api_key=api_key)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Errore: {str(e)}"}), 500

@app.route("/api/agents")
@login_required
def api_agents_list():
    mode = request.args.get("mode")
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        return jsonify({
            "status": "success",
            "agents": registry_list_agents(conn, mode=mode),
            "endpoints": registry_list_endpoints(conn)
        })
    finally:
        conn.close()

@app.route("/api/agents/bootstrap", methods=["POST"])
@login_required
def api_agents_bootstrap():
    conn = get_conn()
    try:
        result = registry_seed_defaults(conn)
        return jsonify({"status": "success", **result})
    finally:
        conn.close()


@app.route("/api/agents/save", methods=["POST"])
@login_required
def api_agents_save():
    payload = request.json or {}
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        result = registry_upsert_agent(conn, payload)
        code = 200 if result.get("ok") else 400
        status = "success" if result.get("ok") else "error"
        return jsonify({"status": status, **result}), code
    finally:
        conn.close()


@app.route("/api/agents/<agent_key>")
@login_required
def api_agents_get(agent_key):
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        agent = registry_get_agent(conn, agent_key)
        if not agent:
            return jsonify({"status": "error", "message": "Agente non trovato"}), 404
        return jsonify({"status": "success", "agent": agent})
    finally:
        conn.close()


@app.route("/api/agents/<agent_key>/enabled", methods=["POST"])
@login_required
def api_agents_set_enabled(agent_key):
    payload = request.json or {}
    enabled = bool(payload.get("enabled", True))
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        result = registry_set_agent_enabled(conn, agent_key, enabled)
        code = 200 if result.get("ok") else 400
        status = "success" if result.get("ok") else "error"
        return jsonify({"status": status, **result}), code
    finally:
        conn.close()


@app.route("/api/agents/<agent_key>", methods=["DELETE"])
@login_required
def api_agents_delete(agent_key):
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        result = registry_delete_agent(conn, agent_key)
        code = 200 if result.get("ok") else 400
        status = "success" if result.get("ok") else "error"
        return jsonify({"status": status, **result}), code
    finally:
        conn.close()


@app.route("/api/provider-endpoints/save", methods=["POST"])
@login_required
def api_provider_endpoints_save():
    payload = request.json or {}
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        result = registry_upsert_provider_endpoint(conn, payload)
        code = 200 if result.get("ok") else 400
        status = "success" if result.get("ok") else "error"
        return jsonify({"status": status, **result}), code
    finally:
        conn.close()


@app.route("/api/provider-endpoints/<endpoint_key>")
@login_required
def api_provider_endpoints_get(endpoint_key):
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        endpoint = registry_get_endpoint(conn, endpoint_key)
        if not endpoint:
            return jsonify({"status": "error", "message": "Endpoint non trovato"}), 404
        return jsonify({"status": "success", "endpoint": endpoint})
    finally:
        conn.close()


@app.route("/api/provider-endpoints/<endpoint_key>", methods=["DELETE"])
@login_required
def api_provider_endpoints_delete(endpoint_key):
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        result = registry_delete_provider_endpoint(conn, endpoint_key)
        code = 200 if result.get("ok") else 400
        status = "success" if result.get("ok") else "error"
        return jsonify({"status": status, **result}), code
    finally:
        conn.close()


@app.route("/api/provider-endpoints/discover", methods=["POST"])
@login_required
def api_provider_endpoints_discover():
    payload = request.json or {}
    endpoint_key = (payload.get("endpoint_key") or "").strip()
    if not endpoint_key:
        return jsonify({"status": "error", "message": "endpoint_key mancante"}), 400

    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        endpoint = registry_get_endpoint(conn, endpoint_key)
        if not endpoint:
            return jsonify({"status": "error", "message": f"Endpoint non trovato: {endpoint_key}"}), 404
        provider_type = endpoint.get("provider_type")
        base_url = endpoint.get("base_url") or ""
        api_key = get_env_var(endpoint.get("api_key_env"), "") if endpoint.get("api_key_env") else ""
        models = provider_discover_models(provider_type, base_url=base_url, api_key=api_key)
        cache_res = registry_upsert_discovery_cache(conn, endpoint_key, models)
        if not cache_res.get("ok"):
            return jsonify({"status": "error", **cache_res}), 400
        return jsonify({"status": "success", "endpoint_key": endpoint_key, "provider_type": provider_type, "models": models})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    finally:
        conn.close()


@app.route("/api/provider-endpoints/test", methods=["POST"])
@login_required
def api_provider_endpoints_test():
    payload = request.json or {}
    endpoint_key = (payload.get("endpoint_key") or "").strip()
    if not endpoint_key:
        return jsonify({"status": "error", "message": "endpoint_key mancante"}), 400

    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        endpoint = registry_get_endpoint(conn, endpoint_key)
        if not endpoint:
            return jsonify({"status": "error", "message": f"Endpoint non trovato: {endpoint_key}"}), 404
        provider_type = endpoint.get("provider_type")
        base_url = endpoint.get("base_url") or ""
        api_key = get_env_var(endpoint.get("api_key_env"), "") if endpoint.get("api_key_env") else ""
        result = provider_test_provider(provider_type, base_url=base_url, api_key=api_key)
        return jsonify({"status": "success", "endpoint_key": endpoint_key, "provider_type": provider_type, "result": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    finally:
        conn.close()


@app.route("/api/provider-endpoints/discovery-cache")
@login_required
def api_provider_endpoints_discovery_cache():
    endpoint_key = (request.args.get("endpoint_key") or "").strip() or None
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        result = registry_get_discovery_cache(conn, endpoint_key=endpoint_key)
        return jsonify({"status": "success", **result})
    finally:
        conn.close()


@app.route("/api/agents/validate")
@login_required
def api_agents_validate():
    mode = (request.args.get("mode") or "").strip() or None
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        result = registry_validate_agent_configuration(conn, mode=mode)
        return jsonify({"status": "success", **result})
    finally:
        conn.close()


@app.route("/api/agents/export")
@login_required
def api_agents_export():
    mode = (request.args.get("mode") or "").strip() or None
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        result = registry_export_bundle(conn, mode=mode)
        if not result.get("ok"):
            return jsonify({"status": "error", **result}), 400
        return jsonify({"status": "success", **result})
    finally:
        conn.close()


@app.route("/api/agentic/readiness")
@login_required
def api_agentic_readiness():
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        report = registry_readiness_report(conn)
        status = "success" if report.get("ok") else "error"
        code = 200 if report.get("ok") else 400
        return jsonify({"status": status, **report}), code
    finally:
        conn.close()


@app.route("/api/agentic/bootstrap-full", methods=["POST"])
@login_required
def api_agentic_bootstrap_full():
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        seed_result = registry_seed_defaults(conn)
        report = registry_readiness_report(conn)
        status = "success" if report.get("ok") else "error"
        code = 200 if report.get("ok") else 400
        return jsonify({"status": status, "seed": seed_result, "readiness": report}), code
    finally:
        conn.close()


@app.route("/api/agents/import", methods=["POST"])
@login_required
def api_agents_import():
    payload = request.json or {}
    bundle = payload.get("bundle")
    overwrite = bool(payload.get("overwrite", False))
    import_disabled = bool(payload.get("import_disabled", True))
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        result = registry_import_bundle(conn, bundle, overwrite=overwrite, import_disabled=import_disabled)
        code = 200 if result.get("ok") else 400
        status = "success" if result.get("ok") else "error"
        return jsonify({"status": status, **result}), code
    finally:
        conn.close()


@app.route("/api/agents/test", methods=["POST"])
@login_required
def api_agents_test():
    data = request.json or {}
    agent_key = (data.get("agent_key") or "").strip()
    prompt = (data.get("prompt") or "Dimmi solo: OK")
    if not agent_key:
        return jsonify({"status": "error", "message": "agent_key mancante"}), 400

    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        row = conn.execute(
            """
            SELECT a.agent_key, a.label, a.provider_type, a.model_id, e.base_url, e.api_key_env
            FROM chat_agents a
            LEFT JOIN provider_endpoints e ON e.id = a.endpoint_id
            WHERE a.agent_key=?
            """,
            (agent_key,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return jsonify({"status": "error", "message": f"Agente non trovato: {agent_key}"}), 404

    agent = dict(row)
    provider = agent.get("provider_type")
    model = agent.get("model_id")
    api_key = get_env_var(agent.get("api_key_env"), "") if agent.get("api_key_env") else ""

    if agent.get("base_url"):
        if provider == "lmstudio":
            set_env_var("LMSTUDIO_URL", agent["base_url"])
        elif provider == "openai_compatible":
            set_env_var("OPENAI_COMPATIBLE_URL", agent["base_url"])
        elif provider == "ollama":
            set_env_var("OLLAMA_URL", agent["base_url"])

    from llm_client import generate_chapter_text

    try:
        reply = generate_chapter_text(prompt, provider, model, api_key, max_tokens=120)
        return jsonify({
            "status": "success",
            "agent": {
                "agent_key": agent.get("agent_key"),
                "label": agent.get("label"),
                "provider": provider,
                "model": model,
            },
            "reply": reply,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/chat/tools")
@login_required
def api_chat_tools_list():
    admin_mode = str(request.args.get("admin_mode", "false")).lower() in {"1", "true", "yes"}
    detailed = str(request.args.get("detailed", "false")).lower() in {"1", "true", "yes"}
    if detailed:
        return jsonify({"status": "success", "tools": chat_available_tools_catalog(admin_mode=admin_mode)})
    return jsonify({"status": "success", "tools": chat_available_tools(admin_mode=admin_mode)})


@app.route("/api/chat/tools/execute", methods=["POST"])
@login_required
def api_chat_tools_execute():
    data = request.json or {}
    tool_name = (data.get("tool") or "").strip()
    arguments = data.get("arguments") or {}
    admin_mode = bool(data.get("admin_mode", False))
    session_key = (data.get("session_key") or "").strip()

    if not tool_name:
        return jsonify({"status": "error", "message": "tool mancante"}), 400

    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        started = time.perf_counter()
        result = chat_execute_tool(conn, tool_name, arguments, admin_mode=admin_mode)
        duration_ms = int((time.perf_counter() - started) * 1000)

        if session_key:
            row = conn.execute("SELECT id FROM chat_sessions WHERE session_key=?", (session_key,)).fetchone()
            session_id = row["id"] if row else None
            if session_id is None:
                mode = "author" if admin_mode else "reader"
                cap_id = None
                try:
                    cap_id = int(arguments.get("cap_id")) if arguments.get("cap_id") is not None else None
                except Exception:
                    cap_id = None
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO chat_sessions (session_key, mode, cap_id, user_scope)
                    VALUES (?, ?, ?, '')
                    """,
                    (session_key, mode, cap_id),
                )
                if cur.lastrowid:
                    session_id = cur.lastrowid
                else:
                    row_retry = conn.execute("SELECT id FROM chat_sessions WHERE session_key=?", (session_key,)).fetchone()
                    session_id = row_retry["id"] if row_retry else None
            conn.execute(
                """
                INSERT INTO chat_tool_runs (session_id, agent_id, tool_name, arguments_json, result_json, status, duration_ms)
                VALUES (?, NULL, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    tool_name,
                    json.dumps(arguments, ensure_ascii=False),
                    json.dumps(result, ensure_ascii=False),
                    "ok" if result.get("ok") else "error",
                    duration_ms,
                ),
            )
            conn.commit()

        status = "success" if result.get("ok") else "error"
        code = 200 if result.get("ok") else 400
        return jsonify({"status": status, "tool": tool_name, "result": result}), code
    finally:
        conn.close()


@app.route("/api/chat/tool-runs")
@login_required
def api_chat_tool_runs():
    limit_raw = request.args.get("limit", "30")
    session_key = (request.args.get("session_key") or "").strip()
    try:
        limit = max(1, min(int(limit_raw), 200))
    except Exception:
        return jsonify({"status": "error", "message": "limit non valido"}), 400

    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        params = []
        query = (
            "SELECT tr.id, tr.tool_name, tr.status, tr.duration_ms, tr.created_at, "
            "s.session_key, a.agent_key "
            "FROM chat_tool_runs tr "
            "LEFT JOIN chat_sessions s ON s.id = tr.session_id "
            "LEFT JOIN chat_agents a ON a.id = tr.agent_id "
        )
        if session_key:
            query += "WHERE s.session_key = ? "
            params.append(session_key)
        query += "ORDER BY tr.id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, tuple(params)).fetchall()
        return jsonify({"status": "success", "runs": [dict(r) for r in rows]})
    finally:
        conn.close()


@app.route("/api/chat/tools/plan", methods=["POST"])
@login_required
def api_chat_tools_plan():
    data = request.json or {}
    admin_mode = bool(data.get("admin_mode", False))
    session_key = (data.get("session_key") or "").strip()
    allowed_tools = data.get("allowed_tools") if isinstance(data.get("allowed_tools"), list) else []
    stop_on_error = bool(data.get("stop_on_error", False))
    dry_run = bool(data.get("dry_run", False))
    plan = data.get("tool_plan")
    agent_key = (data.get("agent_key") or "").strip()

    normalized = chat_normalize_tool_plan(plan)
    if not normalized.get("ok"):
        return jsonify({"status": "error", "message": normalized.get("error", "tool_plan non valido")}), 400
    if dry_run:
        return jsonify({"status": "success", "dry_run": True, "normalized_plan": normalized["plan"]})

    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        agent = None
        if agent_key:
            agent = registry_get_agent(conn, agent_key)
            if not agent:
                return jsonify({"status": "error", "message": f"Agente non trovato: {agent_key}"}), 404
            scoped = _parse_agent_tool_scope(agent)
            if scoped:
                allowed_tools = scoped
        started = time.perf_counter()
        result = chat_execute_tool_plan(
            conn,
            normalized["plan"],
            admin_mode=admin_mode,
            allowed_tools=allowed_tools,
            stop_on_error=stop_on_error,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)

        if session_key:
            row = conn.execute("SELECT id FROM chat_sessions WHERE session_key=?", (session_key,)).fetchone()
            session_id = row["id"] if row else None
            if session_id is None:
                mode = "author" if admin_mode else "reader"
                cur = conn.execute(
                    "INSERT OR IGNORE INTO chat_sessions (session_key, mode, cap_id, user_scope) VALUES (?, ?, NULL, '')",
                    (session_key, mode),
                )
                if cur.lastrowid:
                    session_id = cur.lastrowid
                else:
                    row_retry = conn.execute("SELECT id FROM chat_sessions WHERE session_key=?", (session_key,)).fetchone()
                    session_id = row_retry["id"] if row_retry else None
            for run in result.get("runs", []):
                conn.execute(
                    """
                    INSERT INTO chat_tool_runs (session_id, agent_id, tool_name, arguments_json, result_json, status, duration_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        agent.get("id") if agent else None,
                        run.get("tool", ""),
                        json.dumps((normalized["plan"][max(0, int(run.get("index", 1)) - 1)].get("arguments", {})), ensure_ascii=False),
                        json.dumps(run.get("result", {}), ensure_ascii=False),
                        "ok" if run.get("status") == "ok" else ("blocked" if run.get("status") == "blocked" else "error"),
                        duration_ms,
                    ),
                )
            conn.commit()

        status = "success" if result.get("ok") else "error"
        code = 200 if result.get("ok") else 400
        return jsonify({"status": status, "result": result}), code
    finally:
        conn.close()


@app.route("/api/chat/<int:cap_id>", methods=["POST"])
def api_chat(cap_id):
    data = request.json
    if not data or not data.get("message"):
        return jsonify({"error": "No message provided"}), 400
        
    user_msg = data.get("message")
    history = data.get("history", [])
    admin_mode = data.get("admin_mode", False)

    session_key = (data.get("session_key") or "").strip() or build_chat_session_key(cap_id, admin_mode)
    conn_mem = get_conn()
    try:
        memory_snapshot = upsert_session_memory(
            conn_mem,
            session_key=session_key,
            mode="author" if admin_mode else "reader",
            cap_id=cap_id,
            history=normalize_chat_history(history),
        )
        persisted_memory = load_session_memory(conn_mem, session_key)
    finally:
        conn_mem.close()

    user_msg = compose_user_message_with_history(user_msg, history)
    if persisted_memory.get("open_questions"):
        user_msg += "\n\n[MEMORIA_SESSIONE] Domande aperte: " + " | ".join(persisted_memory["open_questions"][:3])

    requested_mode = (data.get("mode") or "auto").strip().lower()
    should_stream = data.get("stream", True) # Default to stream now
    include_sources = bool(data.get("include_sources", admin_mode))
    
    ui = load_ui_settings()
    prompts = load_prompts()
    
    provider = get_env_var("LLM_PROVIDER", "openai")
    model_id = ui.get("admin_chat_model" if admin_mode else "frontend_chat_model", "claude-3-5-sonnet-20241022")
    model_name = model_id

    local_model = get_env_var("ADMIN_CHAT_MODEL")
    if provider == "lmstudio" and local_model:
        model_name = local_model
    elif "|" in model_id:
        provider, model_name = model_id.split("|", 1)

    api_key = ""
    if provider == "openai": api_key = get_env_var("OPENAI_API_KEY")
    elif provider == "anthropic": api_key = get_env_var("CLAUDE_API_KEY")
    elif provider == "google": api_key = get_env_var("GEMINI_API_KEY")
    elif provider == "lmstudio": api_key = get_env_var("LMSTUDIO_API_KEY", "")
    elif provider == "openai_compatible": api_key = get_env_var("OPENAI_COMPATIBLE_API_KEY", "")
    elif provider == "ollama": api_key = ""

    phase1_enabled = str(get_env_var("AGENTIC_MULTIROLE_ENABLED", "true")).strip().lower() in {"1", "true", "yes", "on"}
    roles_bundle = resolve_agents_for_mode(admin_mode) if phase1_enabled else {"resolved": {}, "missing": [], "required_roles": []}
    roles = roles_bundle.get("resolved", {})
    missing_roles = roles_bundle.get("missing", [])
    multirole_ready = phase1_enabled and (len(missing_roles) == 0)

    fallback_choice = resolve_chat_model_from_registry(admin_mode)
    if fallback_choice:
        provider = fallback_choice["provider"]
        model_name = fallback_choice["model_name"]
        api_key = fallback_choice["api_key"]

    if phase1_enabled and missing_roles:
        app.logger.warning("AGENTIC_MULTIROLE fallback: ruoli mancanti in mode=%s -> %s", "author" if admin_mode else "reader", ",".join(missing_roles))

    from llm_client import generate_chapter_text

    def run_multirole_phase1():
        analysis_history = run_deep_context_pipeline(cap_id, provider, model_name, api_key, user_msg=user_msg, admin_mode=admin_mode)
        debug = {
            "multirole": True,
            "mode": "author" if admin_mode else "reader",
            "roles": sorted(list(roles.keys())),
            "tool_contracts": {},
            "tool_runs": [],
            "forced_vector_policy": False,
        }
        conn_tools = get_conn()

        try:
            if admin_mode:
                router_agent = roles["AuthorTaskRouter"]
                synth_agent = roles["AnswerSynthesizer"]
                router_cfg = _agent_runtime_config(router_agent)
                synth_cfg = _agent_runtime_config(synth_agent)

                router_system = _agent_prompt_text(router_agent, "system", "Classifica il task autore.")
                router_task_tpl = _agent_prompt_text(router_agent, "task", "Restituisci un piano operativo in JSON.")
                router_task = (
                    f"{router_task_tpl}\n\n"
                    f"[DOMANDA_AUTORE]\n{user_msg}\n\n"
                    f"[CONTRATTO_OUTPUT_JSON]\n"
                    f"Restituisci SOLO JSON oggetto con: intent (str), confidence (0..1), tool_plan (array di step {{tool, arguments}}), evidenze_richieste (array), note (str)."
                )
                router_hist = [{"role": "system", "content": router_system}] + analysis_history + [{"role": "user", "content": router_task}]
                router_raw = generate_chapter_text("", router_cfg["provider"], router_cfg["model_name"], router_cfg["api_key"], max_tokens=900, messages=router_hist)
                router_contract = _normalize_tool_plan_contract(router_raw)
                debug["tool_contracts"]["author_router"] = {"ok": router_contract["ok"], "error": router_contract.get("error", "")}

                tool_result = {"ok": True, "runs": [], "executed": 0, "blocked": 0, "errors": 0}
                router_plan = list(router_contract["tool_plan"]) if router_contract["ok"] else []
                force_vector = _should_force_vector_lookup(user_msg)
                if force_vector and not _tool_plan_has_vector(router_plan, admin_mode=True):
                    router_plan.append(_forced_vector_step(user_msg, cap_id, admin_mode=True, k=6))
                    debug["forced_vector_policy"] = True
                if router_plan:
                    tool_result = _execute_tool_plan_with_logging(
                        conn_tools,
                        session_key=session_key,
                        cap_id=cap_id,
                        admin_mode=True,
                        agent=router_agent,
                        tool_plan=router_plan,
                        stop_on_error=True,
                    )
                    debug["tool_runs"] = tool_result.get("runs", [])
                if force_vector and not tool_result.get("executed"):
                    fallback_res = _run_direct_vector_fallback(conn_tools, session_key, cap_id, True, router_agent, user_msg, k=6)
                    tool_result = {"ok": fallback_res.get("ok", False), "runs": [{"index": 1, "tool": "vector_search_author", "status": "ok" if fallback_res.get("ok") else "error", "result": fallback_res}], "executed": 1 if fallback_res.get("ok") else 0, "blocked": 0, "errors": 0 if fallback_res.get("ok") else 1}
                    debug["tool_runs"] = tool_result["runs"]
                    debug["forced_vector_policy"] = True
                evidence_refs = _extract_evidence_refs(tool_result)
                debug["sources_used"] = evidence_refs

                synth_system = _agent_prompt_text(synth_agent, "system", "Sintetizza una risposta grounded per l'autore.")
                synth_summary = _agent_prompt_text(synth_agent, "summary", "Produci la risposta finale operativa.")
                synth_user = (
                    f"{synth_summary}\n\n"
                    f"[PIANO_ROUTER_RAW]\n{router_raw}\n\n"
                    f"[PIANO_ROUTER_JSON]\n{json.dumps(router_contract.get('parsed', {}), ensure_ascii=False)}\n\n"
                    f"[RISULTATI_TOOL]\n{json.dumps(tool_result, ensure_ascii=False)}\n\n"
                    f"[EVIDENZE_RIFERIMENTI]\n{json.dumps(evidence_refs, ensure_ascii=False)}\n\n"
                    f"[DOMANDA_AUTORE]\n{user_msg}"
                )
                synth_hist = [{"role": "system", "content": synth_system}] + analysis_history + [{"role": "user", "content": synth_user}]
                reply = generate_chapter_text("", synth_cfg["provider"], synth_cfg["model_name"], synth_cfg["api_key"], max_tokens=2000, messages=synth_hist)
                if include_sources and evidence_refs:
                    reply += "\n\nFonti usate:\n" + "\n".join([f"- cap {r['cap_id']} chunk {r['chunk_no']} (score={r.get('score')})" for r in evidence_refs[:8]])
                debug["router_plan"] = router_raw[:1500]
                return {"reply": reply, "spoiler_audit": {"status": "skipped", "violations": []}, "rewritten": False, "debug": debug, "sources_used": evidence_refs}

            answerer_agent = roles["ReaderAnswerer"]
            judge_agent = roles["SpoilerJudge"]
            answerer_cfg = _agent_runtime_config(answerer_agent)
            judge_cfg = _agent_runtime_config(judge_agent)

            answerer_system = _agent_prompt_text(answerer_agent, "system", "Rispondi al lettore senza spoiler.")
            answerer_task = _agent_prompt_text(answerer_agent, "task", "Rispondi al lettore in modo chiaro e spoiler-free.")
            answerer_plan_user = (
                f"{answerer_task}\n\n"
                f"[DOMANDA]\n{user_msg}\n\n"
                f"[CONTRATTO_OUTPUT_JSON]\n"
                f"Restituisci SOLO JSON oggetto con: answer_draft (str), tool_plan (array step {{tool, arguments}}), rationale (str breve)."
            )
            answerer_plan_hist = [{"role": "system", "content": answerer_system}] + analysis_history + [{"role": "user", "content": answerer_plan_user}]
            answerer_raw = generate_chapter_text("", answerer_cfg["provider"], answerer_cfg["model_name"], answerer_cfg["api_key"], max_tokens=1200, messages=answerer_plan_hist)
            answerer_json = _extract_json_object(answerer_raw) or {}
            answerer_contract = _normalize_tool_plan_contract(answerer_raw)
            debug["tool_contracts"]["reader_answerer"] = {"ok": answerer_contract["ok"], "error": answerer_contract.get("error", "")}

            tool_result = {"ok": True, "runs": [], "executed": 0, "blocked": 0, "errors": 0}
            answerer_plan = list(answerer_contract["tool_plan"]) if answerer_contract["ok"] else []
            force_vector = _should_force_vector_lookup(user_msg)
            if force_vector and not _tool_plan_has_vector(answerer_plan, admin_mode=False):
                answerer_plan.append(_forced_vector_step(user_msg, cap_id, admin_mode=False, k=6))
                debug["forced_vector_policy"] = True
            if answerer_plan:
                tool_result = _execute_tool_plan_with_logging(
                    conn_tools,
                    session_key=session_key,
                    cap_id=cap_id,
                    admin_mode=False,
                    agent=answerer_agent,
                    tool_plan=answerer_plan,
                    stop_on_error=True,
                )
                debug["tool_runs"] = tool_result.get("runs", [])
            if force_vector and not tool_result.get("executed"):
                fallback_res = _run_direct_vector_fallback(conn_tools, session_key, cap_id, False, answerer_agent, user_msg, k=6)
                tool_result = {"ok": fallback_res.get("ok", False), "runs": [{"index": 1, "tool": "vector_search_reader", "status": "ok" if fallback_res.get("ok") else "error", "result": fallback_res}], "executed": 1 if fallback_res.get("ok") else 0, "blocked": 0, "errors": 0 if fallback_res.get("ok") else 1}
                debug["tool_runs"] = tool_result["runs"]
                debug["forced_vector_policy"] = True
            evidence_refs = _extract_evidence_refs(tool_result)
            debug["sources_used"] = evidence_refs

            draft_from_json = str(answerer_json.get("answer_draft", "")).strip()
            if draft_from_json:
                draft_reply = draft_from_json
            else:
                answerer_final_user = (
                    f"{answerer_task}\n\n"
                    f"[DOMANDA]\n{user_msg}\n\n"
                    f"[RISULTATI_TOOL]\n{json.dumps(tool_result, ensure_ascii=False)}\n\n"
                    f"[ISTRUZIONE]\nGenera solo la risposta finale spoiler-free."
                )
                answerer_final_hist = [{"role": "system", "content": answerer_system}] + analysis_history + [{"role": "user", "content": answerer_final_user}]
                draft_reply = generate_chapter_text("", answerer_cfg["provider"], answerer_cfg["model_name"], answerer_cfg["api_key"], max_tokens=1800, messages=answerer_final_hist)

            judge_guard = _agent_prompt_text(judge_agent, "guard", "Valuta se ci sono spoiler.")
            judge_eval_prompt = (
                f"{judge_guard}\n\n"
                f"[CAPITOLO_FRONTIER]\n{cap_id}\n\n"
                f"[DOMANDA]\n{user_msg}\n\n"
                f"[RISPOSTA_BOZZA]\n{draft_reply}\n\n"
                f"[FORMATO_RISPOSTA]\nRestituisci SOLO JSON con: status (SAFE|UNSAFE), reason, tool_plan (array opzionale)."
            )
            judge_hist = [{"role": "system", "content": judge_guard}, {"role": "user", "content": judge_eval_prompt}]
            judge_eval_raw = generate_chapter_text("", judge_cfg["provider"], judge_cfg["model_name"], judge_cfg["api_key"], max_tokens=400, messages=judge_hist).strip()
            judge_json = _extract_json_object(judge_eval_raw) or {}
            judge_status = str(judge_json.get("status", "")).upper()
            unsafe_by_judge = judge_status == "UNSAFE" or judge_eval_raw.upper().startswith("UNSAFE")

            rewritten = False
            guarded_reply = draft_reply
            if unsafe_by_judge:
                rewrite_prompt = _agent_prompt_text(judge_agent, "rewrite", "Riscrivi in modalità sicura senza spoiler.")
                rewrite_user = (
                    f"{rewrite_prompt}\n\n"
                    f"[CAPITOLO_FRONTIER]\n{cap_id}\n\n"
                    f"[DOMANDA]\n{user_msg}\n\n"
                    f"[RISPOSTA_DA_RISCRIVERE]\n{draft_reply}"
                )
                rewrite_hist = [{"role": "system", "content": rewrite_prompt}, {"role": "user", "content": rewrite_user}]
                guarded_reply = generate_chapter_text("", judge_cfg["provider"], judge_cfg["model_name"], judge_cfg["api_key"], max_tokens=1800, messages=rewrite_hist)
                rewritten = True

            safe_result = enforce_reader_safety(guarded_reply, cap_id, get_all())
            if safe_result["rewritten"]:
                rewritten = True
            debug["judge_eval"] = judge_eval_raw[:500]
            final_reply = safe_result["reply"]
            if include_sources and evidence_refs:
                final_reply += "\n\nFonti usate:\n" + "\n".join([f"- cap {r['cap_id']} chunk {r['chunk_no']} (score={r.get('score')})" for r in evidence_refs[:8]])
            return {"reply": final_reply, "spoiler_audit": safe_result["audit"], "rewritten": rewritten, "debug": debug, "sources_used": evidence_refs}
        finally:
            conn_tools.close()

    if not should_stream:
        try:
            debug = {}
            if not admin_mode:
                from reader_orchestrator_v2 import run_reader_orchestrator_stream
                agent_cfgs = load_agent_configs()
                final_reply = ""
                for chunk_sse in run_reader_orchestrator_stream(
                    cap_id,
                    user_msg,
                    history,
                    agent_cfgs,
                    get_all=get_all,
                    get_cap=get_cap,
                    get_full_canon=get_full_canon,
                    get_conn=get_conn,
                    read_txt=read_txt,
                    get_character_context=get_character_context,
                    mode_hint=requested_mode,
                ):
                    payload = parse_sse_payload(chunk_sse)
                    if payload and payload.get("stage") == "synthesis":
                        final_reply = str(payload.get("content", "") or "")
                reply = final_reply.strip()
                spoiler_audit = {"status": "skipped", "violations": []}
                rewritten = False
                debug = {"reader_v2": True}
            elif multirole_ready:
                result = run_multirole_phase1()
                reply = result["reply"]
                spoiler_audit = result["spoiler_audit"]
                rewritten = result["rewritten"]
                debug = result["debug"]
            else:
                analysis_history = run_deep_context_pipeline(cap_id, provider, model_name, api_key, user_msg=user_msg, admin_mode=admin_mode)
                r_prompt = prompts.get("chat_step4_reasoning_prompt", "Analizza il contesto e l'opera. Pianifica una risposta strategica in base alla richiesta dell'autore.")
                r_history = analysis_history + [{"role": "user", "content": r_prompt}]
                reasoning_plan = generate_chapter_text("", provider, model_name, api_key, max_tokens=1500, messages=r_history)
                s_prompt = prompts.get("chat_step5_synthesis_prompt", "In base al ragionamento precedente, rispondi all'autore.")
                s_history = analysis_history + [{"role": "assistant", "content": reasoning_plan}, {"role": "user", "content": s_prompt}]
                reply = generate_chapter_text("", provider, model_name, api_key, max_tokens=2000, messages=s_history)
                spoiler_audit = {"status": "skipped", "violations": []}
                rewritten = False
                if not admin_mode:
                    safe_result = enforce_reader_safety(reply, cap_id, get_all())
                    reply = safe_result["reply"]
                    spoiler_audit = safe_result["audit"]
                    rewritten = safe_result["rewritten"]
                debug = {"multirole": False, "fallback": True, "missing_roles": missing_roles}

            if not admin_mode:
                log_spoiler_audit_event(session_key, cap_id, spoiler_audit, rewritten)

            return jsonify({
                "reply": reply,
                "session_key": session_key,
                "memory": memory_snapshot,
                "spoiler_audit": spoiler_audit,
                "rewritten_for_safety": rewritten,
                "agentic_debug": debug,
                "sources_used": result.get("sources_used", []) if multirole_ready else [],
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # Streaming mode
    def generate():
        import re
        from ai_orchestrator import run_orchestrator_stream
        from reader_orchestrator_v2 import run_reader_orchestrator_stream
        synthesis_chunks = []
        
        try:
            yield f"data: {json.dumps({'stage': 'context', 'content': f'Sessione: {session_key}'})}\n\n"
            if multirole_ready:
                yield f"data: {json.dumps({'stage': 'context', 'content': '⚙️ Fase 1 multi-role attiva (registry).'})}\n\n"
                result = run_multirole_phase1()
                reply = result["reply"]
                if include_sources and result.get("sources_used"):
                    src_count = len(result.get("sources_used", []))
                    yield f"data: {json.dumps({'stage': 'context', 'content': f'📚 Fonti usate: {src_count}'})}\n\n"
                if not admin_mode:
                    log_spoiler_audit_event(session_key, cap_id, result["spoiler_audit"], result["rewritten"])
                yield f"data: {json.dumps({'stage': 'synthesis', 'content': reply})}\n\n"
                yield "data: [DONE]\n\n"
                return

            if not admin_mode:
                agent_cfgs = load_agent_configs()
                generator = run_reader_orchestrator_stream(
                    cap_id,
                    user_msg,
                    history,
                    agent_cfgs,
                    get_all=get_all,
                    get_cap=get_cap,
                    get_full_canon=get_full_canon,
                    get_conn=get_conn,
                    read_txt=read_txt,
                    get_character_context=get_character_context,
                    mode_hint=requested_mode,
                )
            else:
                generator = run_orchestrator_stream(
                    cap_id, provider, model_name, api_key, user_msg, admin_mode, prompts,
                    get_all, get_full_canon, get_conn, read_txt, get_character_context
                )
            for chunk_sse in generator:
                payload = parse_sse_payload(chunk_sse)
                if payload and payload.get("stage") == "synthesis":
                    part = payload.get("content", "")
                    if isinstance(part, str) and part:
                        synthesis_chunks.append(part)
                yield chunk_sse

            if not admin_mode and synthesis_chunks:
                full_reply = "".join(synthesis_chunks).strip()
                safe_result = enforce_reader_safety(full_reply, cap_id, get_all())
                if safe_result["audit"]["status"] == "unsafe":
                    log_spoiler_audit_event(session_key, cap_id, safe_result["audit"], True)
                    yield f"data: {json.dumps({'stage': 'context', 'content': '🛡️ Spoiler audit: risposta riformulata in modalità sicura.'})}\n\n"
                    yield f"data: {json.dumps({'stage': 'synthesis', 'content': safe_result['reply']})}\n\n"
                else:
                    log_spoiler_audit_event(session_key, cap_id, safe_result["audit"], False)

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    from flask import Response
    return Response(generate(), mimetype='text/event-stream')


@app.route("/api/chat/spoiler-audit", methods=["POST"])
@login_required
def api_chat_spoiler_audit():
    data = request.json or {}
    reply = data.get("reply", "")
    cap_id = int(data.get("cap_id", 0) or 0)
    if cap_id <= 0:
        return jsonify({"status": "error", "message": "cap_id mancante o non valido"}), 400

    result = enforce_reader_safety(reply, cap_id, get_all())
    session_key = (data.get("session_key") or "").strip()
    if session_key:
        log_spoiler_audit_event(session_key, cap_id, result["audit"], result["rewritten"])
    return jsonify({"status": "success", **result})

@app.route("/api/chat/memory")
@login_required
def api_chat_memory():
    session_key = (request.args.get("session_key") or "").strip()
    if not session_key:
        return jsonify({"status": "error", "message": "session_key mancante"}), 400
    conn = get_conn()
    try:
        memory = load_session_memory(conn, session_key)
        return jsonify({"status": "success", "session_key": session_key, "memory": memory})
    finally:
        conn.close()


@app.route("/api/vector-index/stats")
@login_required
def api_vector_index_stats():
    conn = get_conn()
    try:
        ensure_vector_schema(conn)
        stats = vector_index_stats(conn)
        return jsonify({"status": "success", **stats})
    finally:
        conn.close()


@app.route("/api/vector-index/versions")
@login_required
def api_vector_index_versions():
    limit_raw = request.args.get("limit", "20")
    try:
        limit = max(1, min(int(limit_raw), 100))
    except Exception:
        return jsonify({"status": "error", "message": "limit non valido"}), 400
    conn = get_conn()
    try:
        ensure_vector_schema(conn)
        payload = vector_list_index_versions(conn, limit=limit)
        return jsonify({"status": "success", **payload})
    finally:
        conn.close()


@app.route("/api/vector-index/rebuild", methods=["POST"])
@login_required
def api_vector_index_rebuild():
    data = request.json or {}
    chunk_size = int(data.get("chunk_size", 1200) or 1200)
    overlap = int(data.get("overlap", 180) or 180)
    embedding_dim = int(data.get("embedding_dim", 256) or 256)
    embedding_provider = (data.get("embedding_provider") or get_env_var("VECTOR_EMBEDDING_PROVIDER", "hash_local")).strip() or "hash_local"
    embedding_model = (data.get("embedding_model") or get_env_var("VECTOR_EMBEDDING_MODEL", "")).strip()
    embedding_base_url = (data.get("embedding_base_url") or get_env_var("VECTOR_EMBEDDING_BASE_URL", "")).strip()
    embedding_api_key = (data.get("embedding_api_key") or get_env_var("VECTOR_EMBEDDING_API_KEY", "")).strip()
    chunk_size = max(300, min(chunk_size, 3000))
    overlap = max(0, min(overlap, chunk_size - 50))
    embedding_dim = max(64, min(embedding_dim, 1024))
    conn = get_conn()
    try:
        ensure_vector_schema(conn)
        result = vector_rebuild_index(
            conn,
            get_all(),
            read_txt,
            chunk_size=chunk_size,
            overlap=overlap,
            embedding_dim=embedding_dim,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            embedding_base_url=embedding_base_url,
            embedding_api_key=embedding_api_key,
        )
        stats = vector_index_stats(conn)
        return jsonify({"status": "success", "result": result, "stats": stats})
    finally:
        conn.close()


@app.route("/api/vector-index/refresh", methods=["POST"])
@login_required
def api_vector_index_refresh():
    data = request.json or {}
    cap_ids_raw = data.get("cap_ids") if isinstance(data.get("cap_ids"), list) else []
    chunk_size = int(data.get("chunk_size", 1200) or 1200)
    overlap = int(data.get("overlap", 180) or 180)
    embedding_dim = int(data.get("embedding_dim", 256) or 256)
    embedding_provider = (data.get("embedding_provider") or get_env_var("VECTOR_EMBEDDING_PROVIDER", "hash_local")).strip() or "hash_local"
    embedding_model = (data.get("embedding_model") or get_env_var("VECTOR_EMBEDDING_MODEL", "")).strip()
    embedding_base_url = (data.get("embedding_base_url") or get_env_var("VECTOR_EMBEDDING_BASE_URL", "")).strip()
    embedding_api_key = (data.get("embedding_api_key") or get_env_var("VECTOR_EMBEDDING_API_KEY", "")).strip()
    chunk_size = max(300, min(chunk_size, 3000))
    overlap = max(0, min(overlap, chunk_size - 50))
    embedding_dim = max(64, min(embedding_dim, 1024))
    conn = get_conn()
    try:
        ensure_vector_schema(conn)
        result = vector_refresh_index_for_chapters(
            conn,
            get_all(),
            read_txt,
            cap_ids=cap_ids_raw,
            chunk_size=chunk_size,
            overlap=overlap,
            embedding_dim=embedding_dim,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            embedding_base_url=embedding_base_url,
            embedding_api_key=embedding_api_key,
        )
        if not result.get("ok"):
            return jsonify({"status": "error", **result}), 400
        stats = vector_index_stats(conn)
        return jsonify({"status": "success", "result": result, "stats": stats})
    finally:
        conn.close()


@app.route("/api/vector-index/search")
@login_required
def api_vector_index_search():
    query = (request.args.get("q") or "").strip()
    mode = (request.args.get("mode") or "author").strip().lower()
    cap_id_raw = request.args.get("cap_id")
    k_raw = request.args.get("k", "5")
    min_score_raw = request.args.get("min_score", "0")
    embedding_dim_raw = request.args.get("embedding_dim", "256")
    embedding_provider = (request.args.get("embedding_provider") or "").strip() or get_env_var("VECTOR_EMBEDDING_PROVIDER", "hash_local")
    embedding_model = (request.args.get("embedding_model") or "").strip() or get_env_var("VECTOR_EMBEDDING_MODEL", "")
    embedding_base_url = (request.args.get("embedding_base_url") or "").strip() or get_env_var("VECTOR_EMBEDDING_BASE_URL", "")
    embedding_api_key = (request.args.get("embedding_api_key") or "").strip() or get_env_var("VECTOR_EMBEDDING_API_KEY", "")
    try:
        k = max(1, min(int(k_raw), 20))
    except Exception:
        return jsonify({"status": "error", "message": "k non valido"}), 400
    try:
        min_score = float(min_score_raw)
    except Exception:
        return jsonify({"status": "error", "message": "min_score non valido"}), 400
    try:
        embedding_dim = max(64, min(int(embedding_dim_raw), 1024))
    except Exception:
        return jsonify({"status": "error", "message": "embedding_dim non valido"}), 400
    cap_id = None
    if cap_id_raw is not None and str(cap_id_raw).strip() != "":
        try:
            cap_id = max(1, int(cap_id_raw))
        except Exception:
            return jsonify({"status": "error", "message": "cap_id non valido"}), 400
    if mode == "reader" and cap_id is None:
        return jsonify({"status": "error", "message": "cap_id obbligatorio in mode=reader"}), 400

    conn = get_conn()
    try:
        ensure_vector_schema(conn)
        result = vector_search_index(
            conn,
            query,
            k=k,
            max_cap_id=cap_id if mode == "reader" else None,
            min_score=min_score,
            embedding_dim=embedding_dim,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            embedding_base_url=embedding_base_url,
            embedding_api_key=embedding_api_key,
        )
        status = "success" if result.get("ok") else "error"
        code = 200 if result.get("ok") else 400
        return jsonify({"status": status, "mode": mode, **result}), code
    finally:
        conn.close()


@app.route("/api/mcp/health")
def api_mcp_health():
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        ensure_vector_schema(conn)
        stats = vector_index_stats(conn)
        return jsonify(
            {
                "status": "success",
                "bridge": "ok",
                "time": int(time.time()),
                "rate_limit_backend": "sqlite_persistent",
                "token_policy_backend": "sqlite+env",
                "vector_index": {
                    "chunks": stats.get("chunks", 0),
                    "chapters": stats.get("chapters", 0),
                    "active_version": stats.get("active_version", ""),
                },
            }
        )
    finally:
        conn.close()


@app.route("/api/mcp/tokens")
@login_required
def api_mcp_tokens_list():
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        _sync_mcp_tokens_from_env(conn)
        rows = conn.execute(
            """
            SELECT token_id, label, tenant_id, scope, max_cap_id, rate_limit_per_minute, enabled, policy_json, created_at, updated_at
            FROM mcp_bridge_tokens
            ORDER BY token_id
            """
        ).fetchall()
        return jsonify({"status": "success", "items": [_mcp_public_token_row(r) for r in rows]})
    finally:
        conn.close()


@app.route("/api/mcp/tokens/save", methods=["POST"])
@login_required
def api_mcp_tokens_save():
    data = request.json or {}
    token_id = (data.get("token_id") or "").strip()
    plain_token = (data.get("token") or "").strip()
    if not token_id:
        return jsonify({"status": "error", "message": "token_id obbligatorio"}), 400
    scope = (data.get("scope") or "both").strip().lower()
    if scope not in {"reader", "author", "both"}:
        return jsonify({"status": "error", "message": "scope non valido"}), 400
    try:
        rate_limit_per_minute = max(1, min(int(data.get("rate_limit_per_minute", 60) or 60), 600))
    except Exception:
        return jsonify({"status": "error", "message": "rate_limit_per_minute non valido"}), 400
    max_cap_id = data.get("max_cap_id")
    try:
        max_cap_id = int(max_cap_id) if max_cap_id not in (None, "", 0, "0") else None
        if max_cap_id is not None and max_cap_id <= 0:
            max_cap_id = None
    except Exception:
        return jsonify({"status": "error", "message": "max_cap_id non valido"}), 400
    enabled = 1 if bool(data.get("enabled", True)) else 0
    label = (data.get("label") or token_id).strip()
    tenant_id = (data.get("tenant_id") or "default").strip() or "default"
    policy = data.get("policy", {})
    if not isinstance(policy, dict):
        return jsonify({"status": "error", "message": "policy deve essere oggetto JSON"}), 400

    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        row = conn.execute("SELECT token_hash FROM mcp_bridge_tokens WHERE token_id=?", (token_id,)).fetchone()
        token_hash = _mcp_token_sha(plain_token) if plain_token else (row["token_hash"] if row else "")
        if not token_hash:
            return jsonify({"status": "error", "message": "token obbligatorio per nuova creazione"}), 400
        conn.execute(
            """
            INSERT INTO mcp_bridge_tokens
                (token_id, token_hash, label, tenant_id, scope, max_cap_id, rate_limit_per_minute, enabled, policy_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(token_id) DO UPDATE SET
                token_hash=excluded.token_hash,
                label=excluded.label,
                tenant_id=excluded.tenant_id,
                scope=excluded.scope,
                max_cap_id=excluded.max_cap_id,
                rate_limit_per_minute=excluded.rate_limit_per_minute,
                enabled=excluded.enabled,
                policy_json=excluded.policy_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                token_id,
                token_hash,
                label,
                tenant_id,
                scope,
                max_cap_id,
                rate_limit_per_minute,
                enabled,
                json.dumps(policy, ensure_ascii=False),
            ),
        )
        conn.commit()
        out = conn.execute(
            """
            SELECT token_id, label, tenant_id, scope, max_cap_id, rate_limit_per_minute, enabled, policy_json, created_at, updated_at
            FROM mcp_bridge_tokens WHERE token_id=?
            """,
            (token_id,),
        ).fetchone()
        return jsonify({"status": "success", "item": _mcp_public_token_row(out)})
    finally:
        conn.close()


@app.route("/api/mcp/tokens/<token_id>/rotate", methods=["POST"])
@login_required
def api_mcp_tokens_rotate(token_id):
    data = request.json or {}
    new_token = (data.get("new_token") or "").strip()
    if not new_token:
        return jsonify({"status": "error", "message": "new_token obbligatorio"}), 400
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        cur = conn.execute(
            "UPDATE mcp_bridge_tokens SET token_hash=?, updated_at=CURRENT_TIMESTAMP WHERE token_id=?",
            (_mcp_token_sha(new_token), token_id),
        )
        if not cur.rowcount:
            return jsonify({"status": "error", "message": "token_id non trovato"}), 404
        conn.commit()
        return jsonify({"status": "success", "token_id": token_id, "rotated": True})
    finally:
        conn.close()


@app.route("/api/mcp/tokens/<token_id>/enabled", methods=["POST"])
@login_required
def api_mcp_tokens_enabled(token_id):
    data = request.json or {}
    enabled = 1 if bool(data.get("enabled", True)) else 0
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        cur = conn.execute(
            "UPDATE mcp_bridge_tokens SET enabled=?, updated_at=CURRENT_TIMESTAMP WHERE token_id=?",
            (enabled, token_id),
        )
        if not cur.rowcount:
            return jsonify({"status": "error", "message": "token_id non trovato"}), 404
        conn.commit()
        return jsonify({"status": "success", "token_id": token_id, "enabled": bool(enabled)})
    finally:
        conn.close()


@app.route("/api/mcp/tokens/<token_id>", methods=["DELETE"])
@login_required
def api_mcp_tokens_delete(token_id):
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        cur = conn.execute("DELETE FROM mcp_bridge_tokens WHERE token_id=?", (token_id,))
        if not cur.rowcount:
            return jsonify({"status": "error", "message": "token_id non trovato"}), 404
        conn.commit()
        return jsonify({"status": "success", "deleted": True, "token_id": token_id})
    finally:
        conn.close()


@app.route("/api/mcp/audit/analytics")
@login_required
def api_mcp_audit_analytics():
    days_raw = request.args.get("days", "7")
    try:
        days = max(1, min(int(days_raw), 90))
    except Exception:
        return jsonify({"status": "error", "message": "days non valido"}), 400
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        since_expr = f"-{days} day"
        by_status = conn.execute(
            """
            SELECT status, COUNT(*) AS n
            FROM mcp_bridge_audit
            WHERE created_at >= datetime('now', ?)
            GROUP BY status
            ORDER BY n DESC
            """,
            (since_expr,),
        ).fetchall()
        top_tokens = conn.execute(
            """
            SELECT token_id, COUNT(*) AS n
            FROM mcp_bridge_audit
            WHERE created_at >= datetime('now', ?)
            GROUP BY token_id
            ORDER BY n DESC
            LIMIT 10
            """,
            (since_expr,),
        ).fetchall()
        top_clients = conn.execute(
            """
            SELECT client_key, COUNT(*) AS n
            FROM mcp_bridge_audit
            WHERE created_at >= datetime('now', ?)
            GROUP BY client_key
            ORDER BY n DESC
            LIMIT 10
            """,
            (since_expr,),
        ).fetchall()
        latency = conn.execute(
            """
            SELECT AVG(latency_ms) AS avg_latency_ms, MAX(latency_ms) AS max_latency_ms
            FROM mcp_bridge_audit
            WHERE created_at >= datetime('now', ?) AND latency_ms > 0
            """,
            (since_expr,),
        ).fetchone()
        return jsonify(
            {
                "status": "success",
                "days": days,
                "by_status": [dict(r) for r in by_status],
                "top_tokens": [dict(r) for r in top_tokens],
                "top_clients": [dict(r) for r in top_clients],
                "latency": {
                    "avg_latency_ms": float(latency["avg_latency_ms"] or 0.0),
                    "max_latency_ms": int(latency["max_latency_ms"] or 0),
                },
            }
        )
    finally:
        conn.close()


@app.route("/api/mcp/audit/cleanup", methods=["POST"])
@login_required
def api_mcp_audit_cleanup():
    data = request.json or {}
    try:
        retention_days = max(1, min(int(data.get("retention_days", 30) or 30), 3650))
    except Exception:
        return jsonify({"status": "error", "message": "retention_days non valido"}), 400
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        cur = conn.execute(
            "DELETE FROM mcp_bridge_audit WHERE created_at < datetime('now', ?)",
            (f"-{retention_days} day",),
        )
        deleted = int(cur.rowcount or 0)
        conn.commit()
        return jsonify({"status": "success", "retention_days": retention_days, "deleted_rows": deleted})
    finally:
        conn.close()


@app.route("/api/mcp/capabilities")
def api_mcp_capabilities():
    return jsonify(
        {
            "status": "success",
            "bridge": "vector-search-read-only",
            "endpoints": [
                {"path": "/api/mcp/health", "method": "GET", "auth": "optional"},
                {"path": "/api/mcp/capabilities", "method": "GET", "auth": "optional"},
                {"path": "/api/mcp/list_vector_index_versions", "method": "GET", "auth": "bearer"},
                {"path": "/api/mcp/vector-search", "method": "POST", "auth": "bearer"},
                {"path": "/api/mcp/tokens", "method": "GET", "auth": "session_admin"},
                {"path": "/api/mcp/tokens/save", "method": "POST", "auth": "session_admin"},
                {"path": "/api/mcp/tokens/<token_id>/rotate", "method": "POST", "auth": "session_admin"},
                {"path": "/api/mcp/tokens/<token_id>/enabled", "method": "POST", "auth": "session_admin"},
                {"path": "/api/mcp/tokens/<token_id>", "method": "DELETE", "auth": "session_admin"},
                {"path": "/api/mcp/audit/analytics", "method": "GET", "auth": "session_admin"},
                {"path": "/api/mcp/audit/cleanup", "method": "POST", "auth": "session_admin"},
            ],
            "modes": ["reader", "author"],
            "policy_fields": ["scope", "max_cap_id", "rate_limit_per_minute", "tenant_id"],
        }
    )


@app.route("/api/mcp/list_vector_index_versions")
def api_mcp_list_vector_index_versions():
    client_key = request.headers.get("X-Client-Id") or request.remote_addr or "unknown"
    limit_raw = request.args.get("limit", "20")
    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        policy = _mcp_resolve_policy(conn, request)
        if not policy:
            _mcp_audit_log(conn, token_id="", tenant_id="", client_key=client_key, endpoint="/api/mcp/list_vector_index_versions", status="unauthorized", error_message="unauthorized")
            return jsonify({"status": "error", "message": "unauthorized"}), 401
        if not _mcp_rate_limit_ok(conn, policy["token_id"], client_key, per_minute=policy["rate_limit_per_minute"]):
            _mcp_audit_log(conn, token_id=policy["token_id"], tenant_id=policy["tenant_id"], client_key=client_key, endpoint="/api/mcp/list_vector_index_versions", status="rate_limited", error_message="rate_limited")
            return jsonify({"status": "error", "message": "rate_limited"}), 429
        try:
            limit = max(1, min(int(limit_raw), 100))
        except Exception:
            _mcp_audit_log(conn, token_id=policy["token_id"], tenant_id=policy["tenant_id"], client_key=client_key, endpoint="/api/mcp/list_vector_index_versions", status="bad_request", error_message="limit non valido")
            return jsonify({"status": "error", "message": "limit non valido"}), 400
        ensure_vector_schema(conn)
        payload = vector_list_index_versions(conn, limit=limit)
        _mcp_audit_log(conn, token_id=policy["token_id"], tenant_id=policy["tenant_id"], client_key=client_key, endpoint="/api/mcp/list_vector_index_versions", status="ok", result_count=len(payload.get("items", [])), meta={"limit": limit})
        return jsonify({"status": "success", **payload})
    finally:
        conn.close()


@app.route("/api/mcp/vector-search", methods=["POST"])
def api_mcp_vector_search():
    t0 = time.time()
    client_key = request.headers.get("X-Client-Id") or request.remote_addr or "unknown"
    data = request.json or {}
    mode = (data.get("mode") or "author").strip().lower()
    query = (data.get("query") or "").strip()
    embedding_provider = (data.get("embedding_provider") or "").strip() or get_env_var("VECTOR_EMBEDDING_PROVIDER", "hash_local")
    embedding_model = (data.get("embedding_model") or "").strip() or get_env_var("VECTOR_EMBEDDING_MODEL", "")
    embedding_base_url = (data.get("embedding_base_url") or "").strip() or get_env_var("VECTOR_EMBEDDING_BASE_URL", "")
    embedding_api_key = (data.get("embedding_api_key") or "").strip() or get_env_var("VECTOR_EMBEDDING_API_KEY", "")
    try:
        k = max(1, min(int(data.get("k", 5) or 5), 20))
        min_score = float(data.get("min_score", 0.0) or 0.0)
        embedding_dim = max(64, min(int(data.get("embedding_dim", 256) or 256), 1024))
    except Exception:
        return jsonify({"status": "error", "message": "parametri numerici non validi"}), 400
    if mode not in {"reader", "author"}:
        return jsonify({"status": "error", "message": "mode non valido"}), 400
    cap_id = data.get("cap_id")
    if mode == "reader":
        try:
            cap_id = int(cap_id)
        except Exception:
            return jsonify({"status": "error", "message": "cap_id obbligatorio in mode=reader"}), 400
        if cap_id <= 0:
            return jsonify({"status": "error", "message": "cap_id non valido"}), 400
    else:
        cap_id = None

    conn = get_conn()
    try:
        ensure_agent_registry_schema(conn)
        policy = _mcp_resolve_policy(conn, request)
        if not policy:
            _mcp_audit_log(conn, token_id="", tenant_id="", client_key=client_key, endpoint="/api/mcp/vector-search", mode=mode, cap_id=cap_id, query_len=len(query), k=k, min_score=min_score, status="unauthorized", error_message="unauthorized")
            return jsonify({"status": "error", "message": "unauthorized"}), 401
        if not _mcp_policy_allows_mode(policy, mode):
            _mcp_audit_log(conn, token_id=policy["token_id"], tenant_id=policy["tenant_id"], client_key=client_key, endpoint="/api/mcp/vector-search", mode=mode, cap_id=cap_id, query_len=len(query), k=k, min_score=min_score, status="forbidden_scope", error_message="scope non autorizzato")
            return jsonify({"status": "error", "message": "scope non autorizzato"}), 403
        if not _mcp_policy_allows_cap(policy, mode, cap_id):
            _mcp_audit_log(conn, token_id=policy["token_id"], tenant_id=policy["tenant_id"], client_key=client_key, endpoint="/api/mcp/vector-search", mode=mode, cap_id=cap_id, query_len=len(query), k=k, min_score=min_score, status="forbidden_cap", error_message="cap_id oltre policy")
            return jsonify({"status": "error", "message": "cap_id oltre policy"}), 403
        if not _mcp_rate_limit_ok(conn, policy["token_id"], client_key, per_minute=policy["rate_limit_per_minute"]):
            _mcp_audit_log(conn, token_id=policy["token_id"], tenant_id=policy["tenant_id"], client_key=client_key, endpoint="/api/mcp/vector-search", mode=mode, cap_id=cap_id, query_len=len(query), k=k, min_score=min_score, status="rate_limited", error_message="rate_limited")
            return jsonify({"status": "error", "message": "rate_limited"}), 429
        ensure_vector_schema(conn)
        result = vector_search_index(
            conn,
            query,
            k=k,
            max_cap_id=cap_id if mode == "reader" else None,
            min_score=min_score,
            embedding_dim=embedding_dim,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            embedding_base_url=embedding_base_url,
            embedding_api_key=embedding_api_key,
        )
        code = 200 if result.get("ok") else 400
        status = "success" if result.get("ok") else "error"
        _mcp_audit_log(
            conn,
            token_id=policy["token_id"],
            tenant_id=policy["tenant_id"],
            client_key=client_key,
            endpoint="/api/mcp/vector-search",
            mode=mode,
            cap_id=cap_id,
            query_len=len(query),
            k=k,
            min_score=min_score,
            status="ok" if result.get("ok") else "error",
            result_count=len(result.get("results", []) or []),
            error_message=result.get("error", "") if not result.get("ok") else "",
            latency_ms=int((time.time() - t0) * 1000),
            meta={"search_mode": result.get("search_mode", "")},
        )
        return jsonify({"status": status, "mode": mode, **result}), code
    finally:
        conn.close()

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    msg_html = ""
    prompts = load_prompts()
    
    if request.method == "POST":
        # Campi ENV
        env_keys = [
            "PROJECT_TITLE", "PROJECT_SUBTITLE", "PROJECT_TIMELINE", "PROJECT_REVISION_GOALS", "LOCAL_DNS",
            "API_AUTH_MODE", "API_CUSTOM_HEADER_KEY", "API_TOKEN", "API_USER_CODE",
            "OPENAI_API_KEY", "GEMINI_API_KEY", "CLAUDE_API_KEY", "LMSTUDIO_URL", "LMSTUDIO_API_KEY", "LLM_PROVIDER",
            "ADMIN_CHAT_MODEL", "AI_MAX_CONTEXT_TOKENS"
        ]
        for k in env_keys:
            if k in request.form:
                set_env_var(k, request.form[k])
        
        # Campi Prompts
        prompts = load_prompts()
        prompts["system_instruction"] = request.form.get("system_instruction", "")
        prompts["planner_prompt"] = request.form.get("planner_prompt", "")
        prompts["drafter_prompt"] = request.form.get("drafter_prompt", "")
        prompts["chapter_splitter_prompt"] = request.form.get("chapter_splitter_prompt", "")
        prompts["scene_planner_html_prompt"] = request.form.get("scene_planner_html_prompt", "")
        prompts["metadata_generator_prompt"] = request.form.get("metadata_generator_prompt", "")
        prompts["step_reviewer_prompt"] = request.form.get("step_reviewer_prompt", "")
        prompts["revisione_prompt"] = request.form.get("revisione_prompt", "")
        prompts["chat_step1_metadata_prompt"] = request.form.get("chat_step1_metadata_prompt", "")
        prompts["chat_step2_summaries_prompt"] = request.form.get("chat_step2_summaries_prompt", "")
        prompts["chat_step3_deep_text_prompt"] = request.form.get("chat_step3_deep_text_prompt", "")
        prompts["chat_step4_reasoning_prompt"] = request.form.get("chat_step4_reasoning_prompt", "")
        prompts["chat_step5_synthesis_prompt"] = request.form.get("chat_step5_synthesis_prompt", "")
        save_prompts(prompts)
        
        # UI SETTINGS
        ui = load_ui_settings()
        ui["contact_intro"] = request.form.get("u_contact_intro", ui.get("contact_intro"))
        ui["contact_success"] = request.form.get("u_contact_success", ui.get("contact_success"))
        ui["frontend_chat_model"] = request.form.get("frontend_chat_model", ui.get("frontend_chat_model", "claude-3-5-sonnet-20241022"))
        ui["admin_chat_model"] = request.form.get("admin_chat_model", ui.get("admin_chat_model", "claude-3-7-sonnet-20250219"))
        
        labels = request.form.getlist("d_label[]")
        urls = request.form.getlist("d_url[]")
        descs = request.form.getlist("d_desc[]")
        
        new_donations = []
        for i in range(len(labels)):
            if labels[i].strip() and urls[i].strip():
                new_donations.append({"label": labels[i], "url": urls[i], "desc": descs[i]})
        ui["donation_links"] = new_donations
        save_ui_settings(ui)

        # Agent Studio (reader scope)
        agent_cfgs = load_agent_configs()
        reader_cfg = agent_cfgs.get("reader", {})
        for agent_name, cfg in list(reader_cfg.items()):
            pfx = f"agent_{agent_name}_"
            if f"{pfx}provider" not in request.form:
                continue
            cfg["enabled"] = request.form.get(f"{pfx}enabled") == "on"
            cfg["provider"] = request.form.get(f"{pfx}provider", cfg.get("provider", "openai"))
            cfg["model"] = request.form.get(f"{pfx}model", cfg.get("model", ""))
            cfg["system_prompt"] = request.form.get(f"{pfx}system_prompt", cfg.get("system_prompt", ""))
            cfg["allowed_tools"] = [x.strip() for x in request.form.get(f"{pfx}allowed_tools", "").split(",") if x.strip()]
            try:
                cfg["temperature"] = float(request.form.get(f"{pfx}temperature", cfg.get("temperature", 0.2)))
            except Exception:
                pass
            try:
                cfg["max_tokens"] = int(request.form.get(f"{pfx}max_tokens", cfg.get("max_tokens", 1200)))
            except Exception:
                pass
            reader_cfg[agent_name] = cfg
        agent_cfgs["reader"] = reader_cfg
        save_agent_configs(agent_cfgs)
        
        return redirect(url_for('settings', msg='ok'))
        
    msg = request.args.get('msg')
    if msg == 'ok':
        msg_html = '<div class="msg ok">✓ Impostazioni e Prompt salvati!</div>'
        
    caps = get_all()
    all_caps_html = "".join(
        f'<a href="/cap/{c["id"]}" class="cap-link"><span class="cap-num">{c["id"]:02d}</span><span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{c["titolo"]}</span></a>'
        for c in caps
    )
    
    auth_mode = get_env_var('API_AUTH_MODE', 'bearer')
    
    ui_set = load_ui_settings()
    frontend_model_sel = ui_set.get('frontend_chat_model', 'claude-3-5-sonnet-20241022')
    admin_model_sel = ui_set.get('admin_chat_model', 'claude-3-7-sonnet-20250219')
    
    frontend_options = ""
    admin_options = ""
    for k, v in MODELS_CONFIG.items():
        frontend_options += f'<optgroup label="{k.upper()}">'
        admin_options += f'<optgroup label="{k.upper()}">'
        for m in v:
            f_sel = "selected" if frontend_model_sel == m[0] else ""
            a_sel = "selected" if admin_model_sel == m[0] else ""
            frontend_options += f'<option value="{m[0]}" {f_sel}>{m[1]}</option>'
            admin_options += f'<option value="{m[0]}" {a_sel}>{m[1]}</option>'
        frontend_options += '</optgroup>'
        admin_options += '</optgroup>'

    agent_models_catalog = {
        "openai": [m[0] for m in MODELS_CONFIG.get("openai", [])],
        "anthropic": [m[0] for m in MODELS_CONFIG.get("anthropic", [])],
        "gemini": [m[0] for m in MODELS_CONFIG.get("google", [])],
        "openai_compatible": [],
        "lmstudio": [],
        "ollama": [],
    }
    agent_models_catalog_json = json.dumps(agent_models_catalog, ensure_ascii=False)
    
    body = f"""
    <div class="topbar">
      <h1>Impostazioni di Sistema</h1>
      <div class="actions">
        <a href="/admin" class="btn">← Dashboard</a>
      </div>
    </div>
    
    <div class="content">
      {msg_html}
      <div class="tabs">
        <div class="tab active" data-group="set" data-id="gen">🔧 Generali & API LLM</div>
        <div class="tab" data-group="set" data-id="sec">🔐 Sicurezza API /oh-my-book</div>
        <div class="tab" data-group="set" data-id="docs">📖 Documentazione API</div>
        <div class="tab" data-group="set" data-id="aiflow">🧠 Flusso Generazione AI</div>
        <div class="tab" data-group="set" data-id="prompt_edit">✍️ Modifica Prompt</div>
        <div class="tab" data-group="set" data-id="ui_ext">🎨 UI & Contatti (Donazioni)</div>
        <div class="tab" data-group="set" data-id="agent_studio">🧪 Agent Studio</div>
        <div class="tab" data-group="set" data-id="agentic">🤖 Gestione Agenti Chat</div>
      </div>
      
      <form method="POST">
        <!-- TAB UI ESTESA -->
        <div class="tab-content" data-tab="set" data-id="ui_ext">
          <div class="card" style="max-width:900px">
            <h2 style="margin-bottom:12px; color:var(--accent)">Configurazione Pagina Contatti & Donazioni</h2>
            <p style="color:var(--muted); font-size:12px; margin-bottom:20px">Gestisci qui i testi che appaiono al pubblico e i link per ricevere supporto economico.</p>
            
            <div class="field">
                <label>Testo Introduzione Form (Sopra ai campi)</label>
                <textarea name="u_contact_intro" style="height:80px">{load_ui_settings().get('contact_intro')}</textarea>
            </div>
            
            <div class="field">
                <label>Messaggio di Successo (Dopo l'invio)</label>
                <input type="text" name="u_contact_success" value="{load_ui_settings().get('contact_success')}">
            </div>
            
            <h3 style="font-size:14px; color:var(--accent); margin:24px 0 12px; border-bottom:1px solid #333; padding-bottom:8px">Link Donazioni</h3>
            <div id="donations-container">
                { "".join([f'''
                <div class="donation-set" style="background:#0a0a0b; padding:15px; border-radius:8px; margin-bottom:15px; border:1px solid #222">
                    <div class="field"><label>Etichetta (es: PayPal)</label><input type="text" name="d_label[]" value="{d['label']}"></div>
                    <div class="field"><label>URL</label><input type="text" name="d_url[]" value="{d['url']}"></div>
                    <div class="field"><label>Descrizione Breve</label><input type="text" name="d_desc[]" value="{d['desc']}"></div>
                    <button type="button" class="btn btn-danger" onclick="this.parentElement.remove()">Rimuovi Link</button>
                </div>
                ''' for d in load_ui_settings().get('donation_links', [])]) }
            </div>
            <button type="button" class="btn" style="margin-top:10px" onclick="addDonationRow()">+ Aggiungi Nuovo Link Donazione</button>
            <script>
            function addDonationRow() {{
                const div = document.createElement('div');
                div.className = "donation-set";
                div.style = "background:#0a0a0b; padding:15px; border-radius:8px; margin-bottom:15px; border:1px solid #222";
                div.innerHTML = `
                    <div class="field"><label>Etichetta (es: Buy Me a Coffee)</label><input type="text" name="d_label[]" value=""></div>
                    <div class="field"><label>URL</label><input type="text" name="d_url[]" value=""></div>
                    <div class="field"><label>Descrizione Breve</label><input type="text" name="d_desc[]" value=""></div>
                    <button type="button" class="btn btn-danger" onclick="this.parentElement.remove()">Rimuovi Link</button>
                `;
                document.getElementById('donations-container').appendChild(div);
            }}
            </script>
          </div>
        </div>
        <!-- TAB GESTIONE AGENTI -->
        <div class="tab-content" data-tab="set" data-id="agentic">
          <div class="card" style="max-width:1100px">
            <h2 style="margin-bottom:10px;color:#6fa8dc">🤖 Registro Agenti Chat (Reader/Author)</h2>
            <p style="color:var(--muted);font-size:12px;margin-bottom:18px">
              Da qui puoi bootstrap, validare, testare e <b>modificare provider/modello/endpoint</b> degli agenti usati dalla chat backend/frontend.
              I modelli cloud disponibili vengono caricati dal catalogo interno (<code>OpenAI/Anthropic/Gemini</code>), mentre per <code>LM Studio/Ollama/OpenAI-compatible</code> puoi usare ID custom o discovery endpoint.
            </p>
            <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px">
              <button type="button" class="btn btn-primary" onclick="agenticBootstrap()">Bootstrap Defaults</button>
              <button type="button" class="btn" onclick="agenticReadiness()">Readiness Report</button>
              <button type="button" class="btn" onclick="agenticValidate('reader')">Valida Reader</button>
              <button type="button" class="btn" onclick="agenticValidate('author')">Valida Author</button>
              <button type="button" class="btn" onclick="agenticLoadRegistry()">Ricarica Registro</button>
            </div>
            <div id="agentic-status" style="display:none;padding:10px;border:1px solid #333;border-radius:6px;background:#111;font-family:monospace;font-size:12px;white-space:pre-wrap"></div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px">
              <div style="background:#0f1115;border:1px solid #2a2f3a;border-radius:8px;padding:12px">
                <h3 style="margin:0 0 8px 0;color:#6fa8dc">Agenti Reader</h3>
                <div id="agentic-reader-list" style="font-size:12px;color:#d1d5db">Caricamento...</div>
              </div>
              <div style="background:#0f1115;border:1px solid #2a2f3a;border-radius:8px;padding:12px">
                <h3 style="margin:0 0 8px 0;color:#a888ca">Agenti Author</h3>
                <div id="agentic-author-list" style="font-size:12px;color:#d1d5db">Caricamento...</div>
              </div>
            </div>
            <div style="margin-top:16px;background:#0f1115;border:1px solid #2a2f3a;border-radius:8px;padding:12px">
              <h3 style="margin:0 0 8px 0;color:#c9a96e">Endpoint Provider registrati</h3>
              <div id="agentic-endpoints-list" style="font-size:12px;color:#d1d5db">Caricamento...</div>
            </div>
            <div style="margin-top:16px;background:#0f1115;border:1px solid #2a2f3a;border-radius:8px;padding:12px">
              <h3 style="margin:0 0 8px 0;color:#d0b36a">Aggiungi/aggiorna endpoint custom</h3>
              <div style="display:grid;grid-template-columns:repeat(3,minmax(180px,1fr));gap:10px">
                <input id="agentic-ep-key" type="text" placeholder="endpoint_key es: lmstudio-locale" style="background:#0b0e13;border:1px solid #2a2f3a;color:#e5e7eb;padding:8px;border-radius:6px">
                <input id="agentic-ep-label" type="text" placeholder="Label endpoint" style="background:#0b0e13;border:1px solid #2a2f3a;color:#e5e7eb;padding:8px;border-radius:6px">
                <select id="agentic-ep-provider" style="background:#0b0e13;border:1px solid #2a2f3a;color:#e5e7eb;padding:8px;border-radius:6px">
                  <option value="openai">openai</option>
                  <option value="anthropic">anthropic</option>
                  <option value="gemini">gemini</option>
                  <option value="openai_compatible">openai_compatible</option>
                  <option value="lmstudio">lmstudio</option>
                  <option value="ollama">ollama</option>
                </select>
                <input id="agentic-ep-url" type="text" placeholder="Base URL (opzionale per cloud)" style="grid-column:span 2;background:#0b0e13;border:1px solid #2a2f3a;color:#e5e7eb;padding:8px;border-radius:6px">
                <input id="agentic-ep-keyenv" type="text" placeholder="API key env (es: OPENAI_API_KEY)" style="background:#0b0e13;border:1px solid #2a2f3a;color:#e5e7eb;padding:8px;border-radius:6px">
              </div>
              <div style="display:flex;gap:12px;align-items:center;margin-top:10px;flex-wrap:wrap">
                <label style="font-size:12px;color:#9ca3af"><input type="checkbox" id="agentic-ep-discovery" checked> supports_discovery</label>
                <label style="font-size:12px;color:#9ca3af"><input type="checkbox" id="agentic-ep-local"> is_local</label>
                <label style="font-size:12px;color:#9ca3af"><input type="checkbox" id="agentic-ep-enabled" checked> enabled</label>
                <button type="button" class="btn btn-primary" onclick="agenticSaveEndpoint()">Salva endpoint</button>
              </div>
            </div>
            <div style="margin-top:16px;background:#0f1115;border:1px solid #2a2f3a;border-radius:8px;padding:12px">
              <h3 style="margin:0 0 8px 0;color:#6fcf6f">🔐 Token MCP (CRUD + rotazione)</h3>
              <div id="agentic-mcp-tokens-list" style="font-size:12px;color:#d1d5db">Caricamento...</div>
              <div style="display:grid;grid-template-columns:repeat(4,minmax(160px,1fr));gap:10px;margin-top:10px">
                <input id="mcp-token-id" type="text" placeholder="token_id" style="background:#0b0e13;border:1px solid #2a2f3a;color:#e5e7eb;padding:8px;border-radius:6px">
                <input id="mcp-token-label" type="text" placeholder="label" style="background:#0b0e13;border:1px solid #2a2f3a;color:#e5e7eb;padding:8px;border-radius:6px">
                <input id="mcp-token-tenant" type="text" placeholder="tenant_id (default)" style="background:#0b0e13;border:1px solid #2a2f3a;color:#e5e7eb;padding:8px;border-radius:6px">
                <select id="mcp-token-scope" style="background:#0b0e13;border:1px solid #2a2f3a;color:#e5e7eb;padding:8px;border-radius:6px">
                  <option value="both">both</option>
                  <option value="reader">reader</option>
                  <option value="author">author</option>
                </select>
                <input id="mcp-token-secret" type="text" placeholder="token (nuovo o rotate)" style="grid-column:span 2;background:#0b0e13;border:1px solid #2a2f3a;color:#e5e7eb;padding:8px;border-radius:6px">
                <input id="mcp-token-max-cap" type="number" min="1" placeholder="max_cap_id opzionale" style="background:#0b0e13;border:1px solid #2a2f3a;color:#e5e7eb;padding:8px;border-radius:6px">
                <input id="mcp-token-rpm" type="number" min="1" max="600" value="60" placeholder="rate/min" style="background:#0b0e13;border:1px solid #2a2f3a;color:#e5e7eb;padding:8px;border-radius:6px">
              </div>
              <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:10px">
                <label style="font-size:12px;color:#9ca3af"><input type="checkbox" id="mcp-token-enabled" checked> enabled</label>
                <button type="button" class="btn btn-primary" onclick="mcpSaveToken()">Salva token</button>
                <button type="button" class="btn" onclick="mcpRotateToken()">Ruota token</button>
                <button type="button" class="btn" onclick="mcpDeleteToken()">Elimina token</button>
                <button type="button" class="btn" onclick="mcpLoadAuditAnalytics()">Audit analytics</button>
                <button type="button" class="btn" onclick="mcpCleanupAudit()">Cleanup audit</button>
              </div>
            </div>
          </div>
        </div>
        <div class="tab-content" data-tab="set" data-id="agent_studio">
          <div class="card" style="max-width:1100px">
            <h2 style="margin-bottom:12px;color:#8ad">Agent Studio (Reader)</h2>
            <p style="color:var(--muted);font-size:12px">Configura provider/modello/prompt/tool policy per ogni agente reader.</p>
            {_render_agent_studio_form(load_agent_configs().get('reader', {}))}
          </div>
        </div>
        <!-- TAB GENERALI E CHIAVI -->
        <div class="tab-content active" data-tab="set" data-id="gen">
          <div class="card" style="max-width:800px">
            <h2 style="margin-bottom:12px">Impostazioni Progetto</h2>
            <div class="field">
              <label>Titolo del Progetto (Opera)</label>
              <input type="text" name="PROJECT_TITLE" value="{get_project_title()}">
              <small style="color:var(--muted);font-size:11px;display:block;margin-top:4px">Verrà mostrato nell'interfaccia e nei file HTML esportati come titolo primario.</small>
            </div>
            
            <div class="field">
              <label>Sottotitolo</label>
              <input type="text" name="PROJECT_SUBTITLE" value="{get_env_var('PROJECT_SUBTITLE')}">
            </div>
            
            <div class="field">
              <label>Timeline dell'Opera (Riassunto Grande)</label>
              <textarea name="PROJECT_TIMELINE" class="tall" placeholder="Inserisci qui il riassunto esteso globale dell'opera...">{get_env_var('PROJECT_TIMELINE')}</textarea>
            </div>

            <div class="field" style="border:1px solid #c9a96e; padding:12px; border-radius:6px; background:rgba(201,169,110,0.05)">
              <label style="color:#c9a96e">🎯 Obiettivi Generali della Revisione</label>
              <textarea name="PROJECT_REVISION_GOALS" style="height:100px" placeholder="Es: Eliminare ripetizioni, migliorare il ritmo, rendere i dialoghi più secchi...">{get_env_var('PROJECT_REVISION_GOALS')}</textarea>
              <small style="color:var(--muted);font-size:11px;display:block;margin-top:4px">Questi obiettivi verranno inviati all'AI durante ogni operazione di revisione capitolo.</small>
            </div>

            <div class="field" style="background:rgba(201,169,110,0.1);padding:12px;border-radius:6px;border:1px solid rgba(201,169,110,0.2)">
              <label style="color:#c9a96e">🌐 Accesso Rete Locale (LAN)</label>
              <input type="text" name="LOCAL_DNS" value="{get_env_var('LOCAL_DNS', '192.168.1.52')}" placeholder="es: oh-my-book.local o 192.168.1.52">
              <small style="color:var(--muted);font-size:11px;display:block;margin-top:4px">Indirizzo IP rilevato: <b>192.168.1.52</b>. Se hai configurato un DNS locale (es. nel file hosts o router), scrivilo qui per vederlo nei link.</small>
            </div>
            
            <h2 style="margin-top:32px;margin-bottom:12px;color:#a888ca">🔑 Chiavi API IA (Accesso Globale)</h2>
            <div class="field">
              <label>OpenAI API Key (ChatGPT)</label>
              <input type="password" name="OPENAI_API_KEY" value="{get_env_var('OPENAI_API_KEY')}">
            </div>
            <div class="field">
              <label>Google Gemini API Key</label>
              <input type="password" name="GEMINI_API_KEY" value="{get_env_var('GEMINI_API_KEY')}">
            </div>
            <div class="field">
              <label>Anthropic API Key (Claude)</label>
              <input type="password" name="CLAUDE_API_KEY" value="{get_env_var('CLAUDE_API_KEY')}">
            </div>

            <h2 style="margin-top:32px;margin-bottom:12px;color:#6fa8dc">💬 Modelli AI per le Chat Assistenti</h2>
            <div class="field">
                <label>Modello AI per la Chat Lettore (Frontend - Spoiler Free)</label>
                <select name="frontend_chat_model">
                    {frontend_options}
                </select>
                <small style="color:var(--muted);font-size:11px;display:block;margin-top:4px">Risponde ai lettori conoscendo solo il testo fino al capitolo che stanno leggendo.</small>
            </div>
            <div class="field">
                <label>Modello AI per la Chat Autore (Backend Admin)</label>
                <select name="admin_chat_model">
                    {admin_options}
                </select>
                <small style="color:var(--muted);font-size:11px;display:block;margin-top:4px">L'assistente dell'autore: ha accesso all'intera timeline e non teme spoiler.</small>
            </div>
            
            <div class="field" style="border:1px solid #6fa8dc; padding:12px; border-radius:6px; background:rgba(111,168,220,0.05)">
              <label style="color:#6fa8dc">🛡️ AI Context Limit (Global 18k) per Chat, Generazione e Revisione</label>
              <input type="number" name="AI_MAX_CONTEXT_TOKENS" value="{get_env_var('AI_MAX_CONTEXT_TOKENS', '18000')}" step="1000">
              <small style="color:var(--muted);font-size:11px;display:block;margin-top:4px">
                Attualmente impostato a <b>18.000 token</b>. Questo limite istruisce la pipeline a dividere il contesto (Metadati + Riassunti + Testo) in chunck se viene superato, proteggendo la RAM del tuo modello locale in TUTTE le operazioni AI.
              </small>
            </div>

            <div class="field" style="background:rgba(111,168,220,0.05); padding:10px; border-radius:6px; border:1px solid rgba(111,168,220,0.2)">
                <label style="color:#6fa8dc">🔧 Modello Custom per LM Studio (Local)</label>
                <div style="display:flex; gap:10px; align-items:center">
                    <input type="text" name="ADMIN_CHAT_MODEL" value="{get_env_var('ADMIN_CHAT_MODEL')}" placeholder="es: qwen2.5-7b" style="flex:1">
                    <div style="font-size:10px; color:var(--muted)">Usato se Provider è <b>LM Studio</b></div>
                </div>
                <small style="color:var(--muted);font-size:11px;display:block;margin-top:4px">Inserisci qui il nome esatto del modello caricato su LM Studio. Questo campo sovrascrive la selezione Cloud se LM Studio è attivo.</small>
            </div>

            <h2 style="margin-top:32px;margin-bottom:12px;color:#c9a96e">🖥️ Integrazione LM Studio (Locale)</h2>
            <div class="field" style="border:1px solid #c9a96e; padding:15px; border-radius:8px; background:rgba(201,169,110,0.05)">
              <div class="field">
                <label>LM Studio Base URL (Endpoint OpenAI-compatibile)</label>
                <div style="display:flex; gap:10px;">
                    <input type="text" name="LMSTUDIO_URL" id="lmstudio_url" value="{get_env_var('LMSTUDIO_URL', 'http://192.168.1.51:1234')}" placeholder="http://192.168.1.51:1234" style="flex:1">
                </div>
              </div>
              <div class="field" style="margin-top:10px">
                <label>API Key (Opzionale - se l'endpoint richiede autenticazione Bearer)</label>
                <div style="display:flex; gap:10px;">
                    <input type="password" name="LMSTUDIO_API_KEY" id="lmstudio_key" value="{get_env_var('LMSTUDIO_API_KEY')}" placeholder="..." style="flex:1">
                    <button type="button" class="btn" onclick="testLMStudio()">Test Connessione</button>
                    <button type="button" class="btn btn-primary" onclick="discoverLMStudio()">Discover Models</button>
                </div>
              </div>
              
              <div id="lm-discovery-results" style="margin-top:15px; display:none">
                <label style="font-size:11px; text-transform:uppercase; color:#c9a96e">Modelli Rilevati:</label>
                <div id="lm-models-list" style="margin-top:5px; padding:10px; background:#111; border-radius:4px; font-family:monospace; font-size:12px; border:1px solid #333"></div>
              </div>

              <div class="field" style="margin-top:20px">
                <label>Utilizza LM Studio come Provider Predefinito?</label>
                <select name="LLM_PROVIDER">
                    <option value="none" {'selected' if get_env_var('LLM_PROVIDER') == 'none' else ''}>No, usa provider Cloud (OpenAI/Anthropic/Google)</option>
                    <option value="lmstudio" {'selected' if get_env_var('LLM_PROVIDER') == 'lmstudio' else ''}>Sì, forza LM Studio (Ignora modelli Cloud)</option>
                </select>
                <small style="color:var(--muted);font-size:11px;display:block;margin-top:4px">Se attivo, il sistema cercherà di usare sempre l'endpoint locale indipendentemente dal modello selezionato sopra.</small>
              </div>
            </div>

            <script>
            function testLMStudio() {{
                const url = document.getElementById('lmstudio_url').value;
                const key = document.getElementById('lmstudio_key').value;
                fetch(`/api/lmstudio/test?url=${{encodeURIComponent(url)}}&key=${{encodeURIComponent(key)}}`)
                .then(r => r.json())
                .then(data => {{
                    alert(data.message);
                }});
            }}
            function discoverLMStudio() {{
                const url = document.getElementById('lmstudio_url').value;
                const key = document.getElementById('lmstudio_key').value;
                const listDiv = document.getElementById('lm-models-list');
                const resDiv = document.getElementById('lm-discovery-results');
                
                listDiv.innerHTML = "Ricerca in corso...";
                resDiv.style.display = "block";
                
                fetch(`/api/lmstudio/discover?url=${{encodeURIComponent(url)}}&key=${{encodeURIComponent(key)}}`)
                .then(r => r.json())
                .then(data => {{
                    if(data.status === "success") {{
                        if(data.models && data.models.length > 0) {{
                            listDiv.innerHTML = data.models.map(m => `<div style="padding:4px 0; border-bottom:1px solid #222">🔹 ${{m}}</div>`).join('');
                        }} else {{
                            listDiv.innerHTML = "Nessun modello caricato in LM Studio.";
                        }}
                    }} else {{
                        listDiv.innerHTML = "Errore: " + data.message;
                    }}
                }})
                .catch(err => {{
                    listDiv.innerHTML = "Errore di rete: " + err;
                }});
            }}
            </script>
          </div>
        </div>

        <!-- TAB SECURITY API -->
        <div class="tab-content" data-tab="set" data-id="sec">
          <div class="card" style="max-width:800px; border-color:#2d5a2d">
            <h2 style="margin-bottom:12px; color:#6fcf6f">🛡️ Configurazione Sicurezza API Ingress</h2>
            
            <div class="field">
              <label>API User Code</label>
              <input type="text" name="API_USER_CODE" value="{get_env_var('API_USER_CODE', 'admin99')}" style="background:#1a2e1a;color:#6fcf6f">
              <small style="color:var(--muted);font-size:11px;display:block;margin-top:4px">Questo codice deve essere passato sempre nel body JSON: <code>{{"user_code": "..."}}</code></small>
            </div>
            
            <div class="field" style="margin-top:24px">
              <label>Modalità Autenticazione Header</label>
              <select name="API_AUTH_MODE">
                <option value="bearer" {'selected' if auth_mode=='bearer' else ''}>Bearer Token (Authorization: Bearer <token>)</option>
                <option value="custom" {'selected' if auth_mode=='custom' else ''}>Intestazione Custom (Chiave: Valore)</option>
              </select>
            </div>
            
            <div class="field">
              <label>Chiave Header Custom (usata SOLO se Modalità è "Intestazione Custom")</label>
              <input type="text" name="API_CUSTOM_HEADER_KEY" value="{get_env_var('API_CUSTOM_HEADER_KEY', 'x-api-key')}">
            </div>
            
            <div class="field">
              <label>API Token Segreto</label>
              <input type="text" name="API_TOKEN" value="{get_env_var('API_TOKEN', '123456789')}">
            </div>
          </div>
        </div>

        <!-- TAB MODIFICA PROMPT -->
        <div class="tab-content" data-tab="set" data-id="prompt_edit">
          <div class="card" style="max-width:900px">
            <h2 style="margin-bottom:12px">✍️ Editor dei Prompt AI</h2>
            <p style="color:var(--muted); font-size:12px; margin-bottom:16px">
              <b>Variabili disponibili:</b> <code>{{cap_id}}, {{p_title}}, {{p_subtitle}}, {{timeline}}, {{titolo}}, {{pov}}, {{luogo}}, {{data_narrativa}}, {{obiettivi}}, {{descrizione}}, {{scene_outline}}, {{parole_target}}, {{base_prompt}}, {{pre_context}}, {{current_step_num}}, {{tot_steps}}, {{step_titolo}}, {{step_descrizione}}, {{step_mood}}</code>
            </p>

            <div class="field">
              <label>System Instruction</label>
              <div style="font-size:11px; color:#c9a96e; margin-bottom:6px; background:rgba(201,169,110,0.1); padding:8px; border-radius:4px; border-left:3px solid #c9a96e">
                📌 <b>IL CUORE DEL MODELLO:</b> Definisce la 'persona' e lo stile base (es. 'Sei un autore di noir'). Viene inviato come messaggio di sistema in <b>OGNI</b> chiamata all'IA per mantenere la coerenza stilistica globale.
              </div>
              <textarea name="system_instruction" style="height:80px">{prompts.get('system_instruction', '')}</textarea>
            </div>

            <div class="field">
              <label>Prompt SPLITTER (Suddivisione Capitolo)</label>
              <div style="font-size:11px; color:#c9a96e; margin-bottom:6px; background:rgba(201,169,110,0.1); padding:8px; border-radius:4px; border-left:3px solid #c9a96e">
                📌 <b>FLUSSO NASCOSTO:</b> Analizza i metadati (Titolo, POV, Luogo) e la descrizione grezza del capitolo per dividerli in 1-4 macro-parti logiche. Questo evita che l'IA si perda in capitoli troppo lunghi.
              </div>
              <textarea name="chapter_splitter_prompt" class="tall">{prompts.get('chapter_splitter_prompt', '')}</textarea>
            </div>

            <div class="field">
              <label>Prompt SCENE PLANNER (Scaletta di Parte)</label>
              <div style="font-size:11px; color:#c9a96e; margin-bottom:6px; background:rgba(201,169,110,0.1); padding:8px; border-radius:4px; border-left:3px solid #c9a96e">
                📌 <b>FLUSSO NASCOSTO:</b> Riceve una singola macro-parte dello Splitter e genera una scaletta dettagliata in formato HTML (<code>&lt;h3&gt;</code> per i titoli, <code>&lt;em&gt;</code> per i beat). È il ponte tra la struttura e la scrittura vera e propria.
              </div>
              <textarea name="scene_planner_html_prompt" class="tall">{prompts.get('scene_planner_html_prompt', '')}</textarea>
            </div>

            <div class="field">
              <label>Prompt PLANNER (VECCHIO - Utilizzato in API secondarie)</label>
              <div style="font-size:11px; color:#c9a96e; margin-bottom:6px">📌 Nota: Questo prompt è quello 'classico' che restituisce JSON diretto.</div>
              <textarea name="planner_prompt" class="tall">{prompts.get('planner_prompt', '')}</textarea>
            </div>

            <div class="field">
              <label>Prompt DRAFTER (Scrittura Scena Loop)</label>
              <div style="font-size:11px; color:#c9a96e; margin-bottom:6px; background:rgba(201,169,110,0.1); padding:8px; border-radius:4px; border-left:3px solid #c9a96e">
                📌 <b>IL MOTORE:</b> Riceve i beat del Planner e il testo delle scene precedenti (Continuity Chained Context). Include <b>Loop Detection</b> (scarta testi ripetitivi) e <b>Adaptive Retry</b>: riprova fino a 3 volte se l'output è insufficiente.
              </div>
              <textarea name="drafter_prompt" class="tall">{prompts.get('drafter_prompt', '')}</textarea>
            </div>

            <div class="field">
              <label>Prompt GENERAZIONE METADATI</label>
              <div style="font-size:11px; color:#c9a96e; margin-bottom:6px; background:rgba(201,169,110,0.1); padding:8px; border-radius:4px; border-left:3px solid #c9a96e">
                📌 <b>FLUSSO NASCOSTO:</b> Attivato quando crei un capitolo vuoto. Legge il Canone e la Timeline globale per suggerire automaticamente POV, Luogo e Riassunto coerenti con l'opera.
              </div>
              <textarea name="metadata_generator_prompt" class="tall">{prompts.get('metadata_generator_prompt', '')}</textarea>
            </div>

            <div class="field" style="border:1px solid #cf6f6f; padding:12px; border-radius:6px; background:rgba(207,111,111,0.05)">
              <label style="color:#cf6f6f">Prompt REVISIONE CORTA (Step Reviewer)</label>
              <div style="font-size:11px; color:#cf6f6f; margin-bottom:6px; background:rgba(207,111,111,0.1); padding:8px; border-radius:4px; border-left:3px solid #cf6f6f">
                📌 <b>IL FILTRO:</b> Agisce subito dopo ogni scena del Drafter. Corregge neologismi errati e allucinazioni. Pulisce il testo tramite <code>extract_narrative</code> prima del salvataggio.
              </div>
              <textarea name="step_reviewer_prompt" class="tall">{prompts.get('step_reviewer_prompt', '')}</textarea>
            </div>

            <div class="field" style="border:1px solid #6fcf6f; padding:12px; border-radius:6px; background:rgba(111,207,111,0.05)">
              <label style="color:#6fcf6f">Prompt REVISIONE CAPITOLO (Editor)</label>
              <div style="font-size:11px; color:#6fcf6f; margin-bottom:6px; background:rgba(111,207,111,0.1); padding:8px; border-radius:4px; border-left:3px solid #6fcf6f">
                📌 <b>REVISIONE MASSIVA:</b> Lavora sull'intero file di testo pre-esistente. Migliora ritmo, stile e corregge incoerenze profonde introdotte durante la stesura veloce.
              </div>
              <textarea name="revisione_prompt" class="tall">{prompts.get('revisione_prompt', '')}</textarea>
            </div>

            <h2 style="margin-top:32px; color:var(--accent)">💬 Multi-Agent RAG Pipeline (Orchestratore)</h2>
            <p style="color:var(--muted); font-size:11px; margin-bottom:16px">
              Questa pipeline usa un'architettura ad agenti asincroni coordinata dall'innovativo Orchestratore. I tre Sub-Agenti lavorano in <b style="color:var(--accent)">parallelo</b> per recuperare le informazioni, accelerando i tempi. L'Orchestratore valuta poi se le informazioni recuperate sono sufficienti per permettere all'Agente Principale di rispondere all'utente con precisione chirurgica.
            </p>

            <div class="field">
              <label>Agent 1: Architetto (Struttura e Canone)</label>
              <div style="font-size:10px; color:#c9a96e; margin-bottom:4px">⚠️ Eseguito in parallelo dal ThreadPool. Estrae limiti e regole globali.</div>
              <textarea name="chat_step1_metadata_prompt" class="tall">{prompts.get('chat_step1_metadata_prompt', '')}</textarea>
            </div>
            
            <div class="field">
              <label>Agent 2: Storico (Recupero Eventi dai Riassunti)</label>
              <div style="font-size:10px; color:#c9a96e; margin-bottom:4px">⚠️ Eseguito in parallelo dal ThreadPool. Trova i collegamenti nel passato.</div>
              <textarea name="chat_step2_summaries_prompt" class="tall">{prompts.get('chat_step2_summaries_prompt', '')}</textarea>
            </div>

            <div class="field">
              <label>Agent 3: Lettore (Analisi Testo Profondo Corrente)</label>
              <div style="font-size:10px; color:#c9a96e; margin-bottom:4px">⚠️ Eseguito in parallelo dal ThreadPool. Legge le singole parole per trovare odori, dialoghi e sensazioni.</div>
              <textarea name="chat_step3_deep_text_prompt" class="tall">{prompts.get('chat_step3_deep_text_prompt', '')}</textarea>
            </div>

            <div class="field" style="border:1px solid #c9a96e; padding:12px; border-radius:6px; background:rgba(201,169,110,0.05)">
              <label style="color:#c9a96e">Nodo Centrale: L'Orchestratore e Stratega (Valutazione)</label>
              <div style="font-size:11px; color:#c9a96e; margin-bottom:6px; background:rgba(201,169,110,0.1); padding:8px; border-radius:4px; border-left:3px solid #c9a96e">
                📌 Riceve i rapporti dei tre agenti paralleli. Valuta se c'è abbastanza materiale per rispondere all'utente o se ci sono punti ciechi. Disegna il piano d'azione finale per la Sintesi.
              </div>
              <textarea name="chat_step4_reasoning_prompt" class="tall">{prompts.get('chat_step4_reasoning_prompt', '')}</textarea>
            </div>

            <div class="field">
              <label>Sintesi Finale: Agente Principale (Risposta Utente)</label>
              <div style="font-size:10px; color:#c9a96e; margin-bottom:4px">L'Agente finale. Nasconde i suoi ragionamenti interni (rimuove i tag &lt;think&gt;) e risponde in Character come 'Guida dell'Archivio' senza mai svelare spoiler ai lettori.</div>
              <textarea name="chat_step5_synthesis_prompt" class="tall">{prompts.get('chat_step5_synthesis_prompt', '')}</textarea>
            </div>
          </div>
        </div>
        
        <div style="position:fixed;bottom:24px;right:24px;z-index:1000">
          <button type="submit" class="btn btn-primary" style="padding:12px 24px;font-size:14px;box-shadow:0 4px 12px rgba(0,0,0,0.5)">💾 Salva Tutte le Impostazioni</button>
        </div>
      </form>
      
      <!-- TAB DOCUMENTAZIONE -->
      <div class="tab-content" data-tab="set" data-id="docs">
        <div class="card" style="max-width:900px">
          <h2>📖 Guida all'utilizzo dell'API /api-book/update-add-remove-info-of-book</h2>
          <div style="background:#1e1e1e;border-radius:6px;padding:16px;font-family:monospace;font-size:12px;line-height:1.6;overflow-x:auto;color:#d4d4d4">
            <h3 style="color:var(--accent);margin-bottom:8px">1. Autenticazione (Sempre Obbligatoria)</h3>
            Se <b>Bearer</b>: <code>Header -> Authorization: Bearer {get_env_var('API_TOKEN', '123456789')}</code><br>
            Se <b>Custom</b>: <code>Header -> {get_env_var('API_CUSTOM_HEADER_KEY', 'x-api-key')}: {get_env_var('API_TOKEN', '123456789')}</code><br>
            <br>Il payload <b>JSON Body</b> deve sempre includere il tuo <code>user_code</code>.<br>
            <hr style="border:0;border-top:1px solid var(--border);margin:16px 0">

            <h3 style="color:#6fcf6f;margin-bottom:8px">2. Elenco Action (POST /api-book/update-add-remove-info-of-book)</h3>
            <b>search-capitolo</b>: Ritorna l'elenco dei capitoli e i metadati se passi la query.<br>
            <code>{{"user_code": "{get_env_var('API_USER_CODE', 'admin99')}", "action": "search-capitolo", "q": "parola"}}</code> (q è opzionale)<br><br>
            
            <b>read-capitolo</b>: Ritorna il testo e la scheda di un singolo capitolo.<br>
            <code>{{"user_code": "{get_env_var('API_USER_CODE', 'admin99')}", "action": "read-capitolo", "id": 5}}</code><br><br>
            
            <b>update-capitolo</b>: Aggiorna metadati parziali ed eventualmente il "testo". I campi omessi nel JSON resteranno invariati (Override parziale).<br>
            <i>Parametri Inviabili (oltre all'id obbligatorio)</i>: <code>titolo, pov, anno, luogo, luogo_macro, linea_narrativa, data_narrativa, stato, parole_target, personaggi_capitolo, personaggi_precedenti, personaggi_successivi, scene_outline, oggetti_simbolo, tensione_capitolo, hook_finale, rischi_incoerenza, transizione_prossimo_capitolo, descrizione, background, parallelo, obiettivi_personaggi, timeline_capitolo, timeline_opera, riassunto, riassunto_capitolo_precedente, riassunto_capitolo_successivo, testo</code>.<br>
            <code>{{"user_code": "{get_env_var('API_USER_CODE', 'admin99')}", "action": "update-capitolo", "id": {cap_id if 'cap_id' in locals() else 1}, "titolo": "Nuovo Titolo Parziale"}}</code><br><br>
            
            <b>add-capitolo</b>: Crea un nuovo capitolo accodato.<br>
            <i>Accetta gli stessi parametri di update-capitolo.</i><br>
            <code>{{"user_code": "{get_env_var('API_USER_CODE', 'admin99')}", "action": "add-capitolo", "titolo": "Inizio", "pov": "Lin..."}}</code><br><br>
            
            <b>delete-capitolo</b>: Elimina DEFINITIVAMENTE un capitolo e il file txt.<br>
            <code>{{"user_code": "{get_env_var('API_USER_CODE', 'admin99')}", "action": "delete-capitolo", "id": 5}}</code><br><br>
            
            <b>modify-book-title</b>: Modifica il titolo globale del progetto.<br>
            <code>{{"user_code": "{get_env_var('API_USER_CODE', 'admin99')}", "action": "modify-book-title", "project_title": "Nuovo Titolo"}}</code><br>
          </div>
        </div>
      </div>

      <!-- TAB FLUSSO GENERAZIONE AI -->
      <div class="tab-content" data-tab="set" data-id="aiflow">
        <div class="card" style="max-width:900px">
          <h2 style="color:#c9a96e;margin-bottom:12px">🧠 Architettura della Generazione Multi-Step</h2>
          
          <div style="margin-bottom:24px;line-height:1.7">
            <h3 style="color:#fff;margin-bottom:8px">1. Background Worker Asincrono</h3>
            <p style="color:var(--muted)">Il sistema gestisce la generazione come un processo in background ("queue"). Questo permette di generare decine di capitoli contemporaneamente senza bloccare il server e senza rischiare timeout del browser.</p>
          </div>
          
          <div style="margin-bottom:24px;line-height:1.7">
            <h3 style="color:#fff;margin-bottom:8px">2. La Pipeline Narrativa (Pipeline Attempt #20)</h3>
            <p style="color:var(--muted)">Per evitare "collassi creativi" e garantire volume alto (>2k parole), il sistema segue questo flusso:</p>
            
            <div style="display:flex; flex-direction:column; gap:15px; margin-top:20px; border-left:2px solid #333; padding-left:20px">
              <div style="background:rgba(255,255,255,0.02); padding:15px; border-radius:8px; border:1px solid #444">
                <strong style="color:#e8d5b7">Step A: Adaptive Splitter</strong><br>
                <small style="color:var(--muted)">Analizza il capitolo e decide se dividerlo in 1, 2, 3 o 4 parti macro basate sulla complessità.</small>
              </div>
              <div style="background:rgba(255,255,255,0.02); padding:15px; border-radius:8px; border:1px solid #444">
                <strong style="color:#e8d5b7">Step B: Scene Planner</strong><br>
                <small style="color:var(--muted)">Per ogni macro-parte, crea una scaletta di scene dettagliate (titolo, mood, obiettivi sensoriali).</small>
              </div>
              <div style="background:rgba(255,255,255,0.02); padding:15px; border-radius:8px; border:1px solid #444">
                <strong style="color:#e8d5b7">Step C: Drafter Loop</strong><br>
                <small style="color:var(--muted)">Scrive la prosa vera e propria. Riceve la cronologia dei fatti già narrati (Causal Anchor) per evitare ripetizioni.</small>
              </div>
              <div style="background:rgba(255,255,255,0.02); padding:15px; border-radius:8px; border:1px solid #444">
                <strong style="color:#e8d5b7">Step D: Step Reviewer</strong><br>
                <small style="color:var(--muted)">Un'IA "Editor" lucida ogni scena, rimuove allucinazioni, neologismi e metafore surreali prima del salvataggio.</small>
              </div>
            </div>
          </div>
          
          <h3 style="color:#c9a96e;margin-bottom:12px">Visualizzazione Prompt Context</h3>
          <p style="color:var(--muted); font-size:13px">Puoi personalizzare ogni prompt nella scheda <b>"Modifica Prompt"</b>. Ogni pezzo della catena riceve dati diversi (Full Canon, Timeline, Testo Precedente) per garantire coerenza totale.</p>
          
          <div style="margin-top:32px; border-top:1px solid #333; padding-top:20px">
            <h2 style="color:#6fa8dc;margin-bottom:12px">💬 Architettura della Chat (Multi-Role)</h2>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:20px">
                <div style="background:rgba(111,168,220,0.02); padding:15px; border-radius:8px; border:1px solid #333">
                    <strong style="color:#6fa8dc">Chat LETTORE (Frontend)</strong><br>
                    <p style="font-size:11px; color:var(--muted); margin-top:8px"><b>PIPELINE:</b> Spoiler-Free Double Pass.</p>
                    <ul style="font-size:10px; color:#aaa; margin-left:15px; margin-top:5px">
                        <li><b>Step 1 (Reasoning):</b> Identifica cosa il lettore sa già.</li>
                        <li><b>Step 2 (Synthesis):</b> Risponde in modo coinvolgente senza spoiler.</li>
                        <li><b>Target:</b> Massima immersività senza "rivelazioni" accidentali.</li>
                    </ul>
                </div>
                <div style="background:rgba(111,168,220,0.02); padding:15px; border-radius:8px; border:1px solid #333">
                    <strong style="color:#a888ca">Chat AUTORE (Backend)</strong><br>
                    <p style="font-size:11px; color:var(--muted); margin-top:8px"><b>PIPELINE:</b> Strategic Research Pass.</p>
                    <ul style="font-size:10px; color:#aaa; margin-left:15px; margin-top:5px">
                        <li><b>Step 1 (Reasoning):</b> Analizza l'intero archivio per trovare connessioni.</li>
                        <li><b>Step 2 (Synthesis):</b> Supporta l'autore con dati precisi e suggerimenti.</li>
                        <li><b>Target:</b> Coerenza totale della macrotrama.</li>
                    </ul>
                </div>
            </div>
          </div>
        </div>
      </div>

    </div>
    <script>
    // Tabs settings injection
    document.querySelectorAll('.tab[data-group="set"]').forEach(t => {{
      t.addEventListener('click', () => {{
        document.querySelectorAll('.tab[data-group="set"]').forEach(x => x.classList.remove('active'));
        t.classList.add('active');
        document.querySelectorAll('.tab-content[data-tab="set"]').forEach(x => x.classList.remove('active'));
        document.querySelector('.tab-content[data-tab="set"][data-id="'+t.dataset.id+'"]').classList.add('active');
        if (t.dataset.id === "agentic") {{
          agenticLoadRegistry();
        }}
      }});
    }});
    const AGENT_MODELS_CATALOG = {agent_models_catalog_json};
    let AGENT_CACHE = {{}};
    let ENDPOINT_CACHE = [];
    async function agenticApi(url, options = {{}}) {{
      const res = await fetch(url, options);
      let data = {{}};
      try {{
        data = await res.json();
      }} catch (_) {{
        data = {{}};
      }}
      if (!res.ok) {{
        throw new Error(data.message || `Errore HTTP ${{res.status}}`);
      }}
      return data;
    }}
    function providerOptions(selected) {{
      const providers = ["openai", "anthropic", "gemini", "openai_compatible", "lmstudio", "ollama"];
      return providers.map(p => `<option value="${{p}}" ${{p===selected?'selected':''}}>${{p}}</option>`).join('');
    }}
    function endpointOptions(providerType, selectedKey) {{
      const filtered = (ENDPOINT_CACHE || []).filter(e => e.provider_type === providerType);
      const base = ['<option value="">(senza endpoint)</option>'];
      filtered.forEach(e => base.push(`<option value="${{e.endpoint_key}}" ${{e.endpoint_key===selectedKey?'selected':''}}>${{e.endpoint_key}} · ${{e.label}}</option>`));
      return base.join('');
    }}
    function modelOptions(providerType, selectedModel) {{
      const catalog = AGENT_MODELS_CATALOG[providerType] || [];
      const inCatalog = catalog.includes(selectedModel);
      const options = catalog.map(m => `<option value="${{m}}" ${{m===selectedModel?'selected':''}}>${{m}}</option>`);
      options.push(`<option value="__custom__" ${{inCatalog ? '' : 'selected'}}>custom...</option>`);
      return {{ html: options.join(''), customValue: inCatalog ? '' : selectedModel }};
    }}
    function renderAgentRows(items) {{
      if (!items || items.length === 0) return '<div style="color:#999">Nessun agente configurato.</div>';
      return items.map(a => {{
        AGENT_CACHE[a.agent_key] = a;
        const modelSel = modelOptions(a.provider_type, a.model_id || '');
        const status = a.enabled ? '🟢 attivo' : '🔴 disattivo';
        return `<div style="padding:8px 0;border-bottom:1px solid #202630">
          <b>${{a.role_key || 'role?'}}</b> · ${{a.label || a.agent_key}} · <span style="color:#9ca3af">${{status}}</span><br>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr 130px;gap:8px;margin-top:8px;align-items:center">
            <select id="agent-provider-${{a.agent_key}}" onchange="agenticRefreshModelAndEndpoints('${{a.agent_key}}')" style="background:#0b0e13;border:1px solid #2a2f3a;color:#e5e7eb;padding:6px;border-radius:6px">
              ${{providerOptions(a.provider_type)}}
            </select>
            <select id="agent-model-${{a.agent_key}}" onchange="agenticToggleCustomModel('${{a.agent_key}}')" style="background:#0b0e13;border:1px solid #2a2f3a;color:#e5e7eb;padding:6px;border-radius:6px">
              ${{modelSel.html}}
            </select>
            <select id="agent-endpoint-${{a.agent_key}}" style="background:#0b0e13;border:1px solid #2a2f3a;color:#e5e7eb;padding:6px;border-radius:6px">
              ${{endpointOptions(a.provider_type, a.endpoint_key || '')}}
            </select>
            <label style="font-size:12px;color:#9ca3af"><input type="checkbox" id="agent-enabled-${{a.agent_key}}" ${{a.enabled?'checked':''}}> enabled</label>
          </div>
          <input id="agent-custom-model-${{a.agent_key}}" type="text" value="${{modelSel.customValue}}" placeholder="Model ID custom (LM Studio/Ollama/OpenAI-compatible)" style="margin-top:8px;display:${{modelSel.customValue?'block':'none'}};width:100%;background:#0b0e13;border:1px solid #2a2f3a;color:#e5e7eb;padding:7px;border-radius:6px">
          <div style="display:flex;gap:8px;margin-top:8px">
            <button type="button" class="btn btn-primary" style="padding:5px 10px" onclick="agenticSaveAgent('${{a.agent_key}}')">Salva agente</button>
            <button type="button" class="btn" style="padding:5px 10px" onclick="agenticTest('${{a.agent_key}}')">Test</button>
          </div>
        </div>`;
      }}).join('');
    }}
    function renderEndpoints(rows) {{
      if (!rows || rows.length === 0) return '<div style="color:#999">Nessun endpoint registrato.</div>';
      return rows.map(e => `<div style="padding:6px 0;border-bottom:1px solid #202630"><b>${{e.endpoint_key}}</b> · ${{e.provider_type}} · <span style="color:#9ca3af">${{e.base_url || '(n/d)'}} </span></div>`).join('');
    }}
    function renderMcpTokens(rows) {{
      if (!rows || rows.length === 0) return '<div style="color:#999">Nessun token MCP configurato.</div>';
      return rows.map(t => `<div style="padding:6px 0;border-bottom:1px solid #202630">
        <b>${{t.token_id}}</b> · tenant=<span style="color:#9ca3af">${{t.tenant_id}}</span> · scope=<span style="color:#9ca3af">${{t.scope}}</span> · rpm=<span style="color:#9ca3af">${{t.rate_limit_per_minute}}</span> · max_cap=<span style="color:#9ca3af">${{t.max_cap_id || '-'}} </span> · ${{t.enabled ? '🟢 enabled' : '🔴 disabled'}}
      </div>`).join('');
    }}
    function setAgenticStatus(obj) {{
      const box = document.getElementById('agentic-status');
      box.style.display = 'block';
      box.textContent = JSON.stringify(obj, null, 2);
    }}
    async function agenticLoadRegistry() {{
      try {{
        AGENT_CACHE = {{}};
        const [reader, author] = await Promise.all([
          agenticApi('/api/agents?mode=reader'),
          agenticApi('/api/agents?mode=author')
        ]);
        ENDPOINT_CACHE = author.endpoints || reader.endpoints || [];
        document.getElementById('agentic-reader-list').innerHTML = renderAgentRows(reader.agents || []);
        document.getElementById('agentic-author-list').innerHTML = renderAgentRows(author.agents || []);
        document.getElementById('agentic-endpoints-list').innerHTML = renderEndpoints(ENDPOINT_CACHE);
        try {{
          const tok = await agenticApi('/api/mcp/tokens');
          document.getElementById('agentic-mcp-tokens-list').innerHTML = renderMcpTokens(tok.items || []);
        }} catch (tokErr) {{
          document.getElementById('agentic-mcp-tokens-list').innerHTML = `<div style="color:#cf6f6f">${{String(tokErr)}}</div>`;
        }}
      }} catch (err) {{
        setAgenticStatus({{status: 'error', message: String(err)}});
      }}
    }}
    function agenticToggleCustomModel(agentKey) {{
      const select = document.getElementById(`agent-model-${{agentKey}}`);
      const custom = document.getElementById(`agent-custom-model-${{agentKey}}`);
      if (!select || !custom) return;
      custom.style.display = select.value === "__custom__" ? "block" : "none";
    }}
    function agenticRefreshModelAndEndpoints(agentKey) {{
      const providerSelect = document.getElementById(`agent-provider-${{agentKey}}`);
      const modelSelect = document.getElementById(`agent-model-${{agentKey}}`);
      const endpointSelect = document.getElementById(`agent-endpoint-${{agentKey}}`);
      if (!providerSelect || !modelSelect || !endpointSelect) return;
      const provider = providerSelect.value;
      const cached = AGENT_CACHE[agentKey] || {{}};
      const modelSel = modelOptions(provider, cached.model_id || "");
      modelSelect.innerHTML = modelSel.html;
      endpointSelect.innerHTML = endpointOptions(provider, cached.endpoint_key || "");
      const custom = document.getElementById(`agent-custom-model-${{agentKey}}`);
      if (custom) {{
        custom.value = modelSel.customValue || "";
        custom.style.display = modelSel.customValue ? "block" : "none";
      }}
    }}
    async function agenticBootstrap() {{
      try {{
        const data = await agenticApi('/api/agents/bootstrap', {{method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{}})}});
        setAgenticStatus(data);
        agenticLoadRegistry();
      }} catch (err) {{
        setAgenticStatus({{status: 'error', message: String(err)}});
      }}
    }}
    async function agenticReadiness() {{
      try {{
        const data = await agenticApi('/api/agentic/readiness');
        setAgenticStatus(data);
      }} catch (err) {{
        setAgenticStatus({{status: 'error', message: String(err)}});
      }}
    }}
    async function agenticValidate(mode) {{
      try {{
        const data = await agenticApi(`/api/agents/validate?mode=${{encodeURIComponent(mode)}}`);
        setAgenticStatus(data);
      }} catch (err) {{
        setAgenticStatus({{status: 'error', message: String(err)}});
      }}
    }}
    async function agenticTest(agentKey) {{
      try {{
        const data = await agenticApi('/api/agents/test', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{agent_key: agentKey, prompt: 'Rispondi solo con: OK'}})
        }});
        setAgenticStatus(data);
      }} catch (err) {{
        setAgenticStatus({{status: 'error', message: String(err)}});
      }}
    }}
    async function agenticSaveAgent(agentKey) {{
      try {{
        const cached = AGENT_CACHE[agentKey];
        if (!cached) throw new Error(`Agente non trovato in cache: ${{agentKey}}`);
        const provider = document.getElementById(`agent-provider-${{agentKey}}`).value;
        const modelSel = document.getElementById(`agent-model-${{agentKey}}`).value;
        const modelCustom = (document.getElementById(`agent-custom-model-${{agentKey}}`).value || "").trim();
        const endpointKey = document.getElementById(`agent-endpoint-${{agentKey}}`).value;
        const enabled = !!document.getElementById(`agent-enabled-${{agentKey}}`).checked;
        const modelId = modelSel === "__custom__" ? modelCustom : modelSel;
        if (!modelId) throw new Error("Model ID obbligatorio");
        const payload = {{
          agent_key: cached.agent_key,
          label: cached.label,
          mode: cached.mode,
          role_key: cached.role_key,
          provider_type: provider,
          endpoint_key: endpointKey,
          model_id: modelId,
          temperature: cached.temperature,
          max_tokens: cached.max_tokens,
          timeout_sec: cached.timeout_sec,
          priority: cached.priority,
          enabled: enabled
        }};
        const data = await agenticApi('/api/agents/save', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify(payload)
        }});
        setAgenticStatus(data);
        await agenticLoadRegistry();
      }} catch (err) {{
        setAgenticStatus({{status: 'error', message: String(err)}});
      }}
    }}
    async function agenticSaveEndpoint() {{
      try {{
        const payload = {{
          endpoint_key: (document.getElementById('agentic-ep-key').value || '').trim(),
          label: (document.getElementById('agentic-ep-label').value || '').trim(),
          provider_type: document.getElementById('agentic-ep-provider').value,
          base_url: (document.getElementById('agentic-ep-url').value || '').trim(),
          api_key_env: (document.getElementById('agentic-ep-keyenv').value || '').trim(),
          supports_discovery: !!document.getElementById('agentic-ep-discovery').checked,
          is_local: !!document.getElementById('agentic-ep-local').checked,
          enabled: !!document.getElementById('agentic-ep-enabled').checked
        }};
        const data = await agenticApi('/api/provider-endpoints/save', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify(payload)
        }});
        setAgenticStatus(data);
        await agenticLoadRegistry();
      }} catch (err) {{
        setAgenticStatus({{status: 'error', message: String(err)}});
      }}
    }}
    async function mcpSaveToken() {{
      try {{
        const payload = {{
          token_id: (document.getElementById('mcp-token-id').value || '').trim(),
          token: (document.getElementById('mcp-token-secret').value || '').trim(),
          label: (document.getElementById('mcp-token-label').value || '').trim(),
          tenant_id: (document.getElementById('mcp-token-tenant').value || '').trim(),
          scope: document.getElementById('mcp-token-scope').value,
          max_cap_id: (document.getElementById('mcp-token-max-cap').value || '').trim(),
          rate_limit_per_minute: Number(document.getElementById('mcp-token-rpm').value || 60),
          enabled: !!document.getElementById('mcp-token-enabled').checked
        }};
        const data = await agenticApi('/api/mcp/tokens/save', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify(payload)
        }});
        setAgenticStatus(data);
        await agenticLoadRegistry();
      }} catch (err) {{
        setAgenticStatus({{status: 'error', message: String(err)}});
      }}
    }}
    async function mcpRotateToken() {{
      try {{
        const tokenId = (document.getElementById('mcp-token-id').value || '').trim();
        const newToken = (document.getElementById('mcp-token-secret').value || '').trim();
        if (!tokenId || !newToken) throw new Error('token_id e token sono obbligatori per rotazione');
        const data = await agenticApi(`/api/mcp/tokens/${{encodeURIComponent(tokenId)}}/rotate`, {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{new_token: newToken}})
        }});
        setAgenticStatus(data);
      }} catch (err) {{
        setAgenticStatus({{status: 'error', message: String(err)}});
      }}
    }}
    async function mcpDeleteToken() {{
      try {{
        const tokenId = (document.getElementById('mcp-token-id').value || '').trim();
        if (!tokenId) throw new Error('token_id obbligatorio');
        const data = await agenticApi(`/api/mcp/tokens/${{encodeURIComponent(tokenId)}}`, {{ method: 'DELETE' }});
        setAgenticStatus(data);
        await agenticLoadRegistry();
      }} catch (err) {{
        setAgenticStatus({{status: 'error', message: String(err)}});
      }}
    }}
    async function mcpLoadAuditAnalytics() {{
      try {{
        const data = await agenticApi('/api/mcp/audit/analytics?days=7');
        setAgenticStatus(data);
      }} catch (err) {{
        setAgenticStatus({{status: 'error', message: String(err)}});
      }}
    }}
    async function mcpCleanupAudit() {{
      try {{
        const days = prompt('Retention giorni audit MCP (default 30):', '30');
        if (days === null) return;
        const data = await agenticApi('/api/mcp/audit/cleanup', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{retention_days: Number(days || 30)}})
        }});
        setAgenticStatus(data);
      }} catch (err) {{
        setAgenticStatus({{status: 'error', message: String(err)}});
      }}
    }}
    agenticLoadRegistry();
    </script>
    """
    return render_template_string(ADMIN_LAYOUT, title="Settings", content=body, all_caps_html=all_caps_html, BASE_CSS=BASE_CSS, project_title=get_project_title())


@app.route("/admin")
@login_required
def admin_dashboard():
    caps = get_all()
    
    # 1. Ricalcolo Parole Narrativa dai file di testo
    total_words = 0
    for c in caps:
        txt_content = read_txt(c['id'])
        c['real_words'] = len(txt_content.split()) if txt_content else 0
        total_words += c['real_words']
    
    total_summary_words = 0
    total_meta_words = 0
    campi_meta_principali = ['descrizione', 'background', 'scene_outline', 'rischi_incoerenza', 'obiettivi_personaggi']
    
    for c in caps:
        # Conteggio Riassunto
        r = c.get('riassunto', '') or ''
        total_summary_words += len(r.split())
        # Conteggio Metadati Core
        for f in campi_meta_principali:
            val = c.get(f, '') or ''
            total_meta_words += len(str(val).split())
            
    linee = sorted(set(c['linea_narrativa'] for c in caps if c.get('linea_narrativa')))

    cards = ""
    for c in caps:
        pov = c.get('pov') or ''
        color = COLORI_POV.get(pov.split('/')[0].strip(), '#888')
        linea = c.get('linea_narrativa') or ''
        stato = c.get('stato') or 'bozza'
        # Estrazione metadati ricchi per la card
        outline = c.get('scene_outline') or ''
        outline_count = len(outline.split())
        personaggi = c.get('personaggi_capitolo') or ''
        rischi = c.get('rischi_incoerenza') or ''
        
        rich_meta_html = ""
        if outline_count > 0:
            rich_meta_html += f'<div style="font-size:10px;color:#c9a96e;margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">📍 {outline[:60]}...</div>'
        if personaggi:
            rich_meta_html += f'<div style="font-size:10px;color:#a888ca;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">👥 {personaggi[:60]}...</div>'
        if rischi:
            rich_meta_html += f'<div style="font-size:10px;color:#cf6f6f;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">⚠️ {rischi[:60]}...</div>'

        cards += f"""<a href="/cap/{c['id']}" class="cap-card" data-linea="{linea}" style="text-decoration:none; display:flex; flex-direction:column; justify-content:space-between; min-height:140px">
  <div>
    <div class="num">{c['id']:02d} &middot; <span class="badge" style="background:{color}">{pov}</span></div>
    <div class="titolo" style="margin-top:4px">{c['titolo']}</div>
    <div class="meta">{c.get('anno') or ''} &middot; {c.get('luogo_macro') or ''}</div>
    {rich_meta_html}
  </div>
  <div class="words" style="border-top:1px solid #222; padding-top:4px; margin-top:8px">{c['real_words']:,} parole &middot; {stato}</div>
</a>"""

    filter_btns = f'<button class="filter-btn active" data-line="all">Tutti</button>'
    for l in linee:
        filter_btns += f'<button class="filter-btn" data-line="{l}">{l}</button>'

    all_caps_html = get_sidebar_html(is_admin=True)

    msg = request.args.get('msg', '')
    msg_html = ""
    if msg.startswith('ok_import_'):
        try:
            count = msg.split('_')[2]
            msg_html = f'<div class="msg ok">✓ Importati/aggiornati con successo {count} capitoli!</div>'
        except:
            msg_html = '<div class="msg ok">✓ Import JSON completato!</div>'
    elif msg == 'err_import':
        msg_html = '<div class="msg err">✗ Errore durante l import JSON</div>'
    elif msg == 'err_file':
        msg_html = '<div class="msg err">✗ Nessun file o file non valido</div>'
    elif msg == 'ok_sync':
        msg_html = '<div class="msg ok">✓ Sincronizzazione Word Count completata!</div>'
    elif msg == 'err':
        msg_html = '<div class="msg err">✗ Errore imprevisto</div>'

    local_dns = get_env_var('LOCAL_DNS', '192.168.1.52')
    subtitle = get_env_var('PROJECT_SUBTITLE', '')
    timeline = get_env_var('PROJECT_TIMELINE', '')
    
    sub_disp = (subtitle[:50] + "...") if len(subtitle) > 50 else subtitle
    time_disp = (timeline[:50] + "...") if len(timeline) > 50 else timeline
    
    js_subtitle = json.dumps(subtitle)
    js_timeline = json.dumps(timeline)
    
    sub_read_more = '<span class="read-more" onclick="showFullText(\'sub\')">Leggi tutto</span>' if len(subtitle)>50 else ''
    time_read_more = '<span class="read-more" onclick="showFullText(\'time\')">Leggi tutto</span>' if len(timeline)>50 else ''

    body = f"""
<div class="topbar">
  <div style="display:flex; flex-direction:column">
    <h1 style="margin:0; font-size:18px">{get_project_title()}</h1>
    <div style="font-size:11px; color:var(--muted); margin-top:4px">
      🌐 Accesso locale: <a href="http://{local_dns}:5000" target="_blank" style="color:var(--accent); text-decoration:none">http://{local_dns}:5000</a> 
      &middot; IP: <span style="color:#fff">192.168.1.52</span>
    </div>
  </div>
  <div class="actions">
    <form method="POST" action="/cap/add" style="display:inline;">
      <button type="submit" class="btn btn-primary" title="Aggiungi un nuovo capitolo in coda a tutti">➕ Capitolo</button>
    </form>
    <form method="POST" action="/import" enctype="multipart/form-data" style="display:inline;">
      <label class="btn" style="cursor:pointer;background:#1e1e1e;color:var(--fg);border-color:var(--border);" title="Importa file JSON fisico">
        📂 Importa file JSON
        <input type="file" name="file" accept=".json" style="display:none" onchange="this.form.submit()">
      </label>
    </form>
    <button class="btn" style="background:#1e1e1e;color:var(--accent)" onclick="document.getElementById('paste-json-container').style.display='block'">📝 Incolla JSON</button>
    <button class="btn" style="background:var(--accent);color:#1a1a1a;border-color:var(--accent);box-shadow: 0 0 10px rgba(232,213,183,0.3)" onclick="openMetadataModal()">✨ Genera Metadati</button>
    <a href="/flow" class="btn" style="background:#1e1e1e;color:#888;border-color:#333" title="Visualizza il flusso di lavoro AI">⚙️ Flusso</a>
    <button class="btn" style="background:#1a2e1a;color:#6fcf6f;border-color:#2d5a2d" onclick="openExportModal()" title="Esportazione avanzata di metadati e testi">📥 Dati Avanzati</button>
    <a href="/admin/contatti" class="btn" style="background:#1e1e1a;color:var(--accent);border-color:#333">📩 Messaggi</a>
    <a href="/admin/sync" class="btn" style="background:#1e1e1e;color:#6fcf6f;border-color:#2d5a2d" title="Sincronizza i conteggi parole dal disco al database">🔄 Sync Parole</a>
    <a href="/rebuild" class="btn btn-primary" title="Ricostruisce il file HTML">⚡ Rebuild HTML</a>
  </div>
</div>
<div class="content">
  {msg_html}

  <div class="project-card">
    <div class="project-meta-item">
      <span class="project-meta-label">Sottotitolo</span>
      <span class="project-meta-value">{sub_disp} {sub_read_more}</span>
    </div>
    <div class="project-meta-item" style="margin:0">
      <span class="project-meta-label">Riassunto Grande / Timeline</span>
      <span class="project-meta-value">{time_disp} {time_read_more}</span>
    </div>
  </div>

  <!-- Modal Export Dati Avanzato -->
  <div id="export-avanzato-modal" class="full-text-overlay" style="display:none; z-index:2000; cursor:default">
    <div class="full-text-modal" style="max-width:500px" onclick="event.stopPropagation()">
      <span class="close-overlay" onclick="closeExportModal()">&times;</span>
      <h2 style="color:var(--accent); margin-top:0">📥 Esportazione Dati Avanzata</h2>
      <p style="font-size:14px; color:#aaa; margin-bottom:20px">Seleziona il tipo di esportazione per scaricare i dati del progetto PRIMA VIVI POI SPIEGHI.</p>
      
      <form id="export-form" method="GET" action="/export/advanced/full_relational">
          <div class="form-group" style="margin-bottom:15px">
            <label>Formato di Esportazione</label>
            <select id="export-mode" onchange="toggleExportFields()" style="width:100%; padding:10px; background:#111; color:#fff; border:1px solid #333; border-radius:6px;">
              <option value="testo">Solo Testo Puro (Archivio ZIP)</option>
              <option value="meta_singolo">Singolo Tipo di Metadato (JSON)</option>
              <option value="full_relational" selected>Export Completo Relazionale (JSON Master)</option>
            </select>
          </div>
          
          <div id="export-single-field" class="form-group" style="margin-bottom:15px; display:none">
            <label>Seleziona Entità da Esportare</label>
            <select id="export-entity" name="entity" style="width:100%; padding:10px; background:#111; color:#fff; border:1px solid #333; border-radius:6px;">
              <option value="capitoli">Capitoli</option>
              <option value="timeline">Timeline Temporale</option>
              <option value="personaggi">Tabella Personaggi</option>
              <option value="personaggi_capitoli">Presenze Personaggi (Log Relazionale)</option>
            </select>
          </div>
          
          <div style="margin-top:30px; text-align:right">
            <button type="button" class="btn" onclick="closeExportModal()" style="margin-right:10px">Annulla</button>
            <button type="button" class="btn btn-primary" onclick="submitExport()">Scarica File</button>
          </div>
      </form>
    </div>
  </div>

  <script>
    function openExportModal() {{ document.getElementById('export-avanzato-modal').style.display = 'flex'; }}
    function closeExportModal() {{ document.getElementById('export-avanzato-modal').style.display = 'none'; }}
    function toggleExportFields() {{
        const mode = document.getElementById('export-mode').value;
        const form = document.getElementById('export-form');
        document.getElementById('export-single-field').style.display = (mode === 'meta_singolo') ? 'block' : 'none';
        
        form.action = '/export/advanced/' + mode;
    }}
    document.getElementById('export-entity').addEventListener('change', toggleExportFields);
    function submitExport() {{
        toggleExportFields(); 
        document.getElementById('export-form').submit();
        closeExportModal();
    }}
  </script>

  <!-- Modal Generazione Metadati -->
  <div id="meta-gen-modal" class="full-text-overlay" style="display:none; z-index:2000; cursor:default">
    <div class="full-text-modal" style="max-width:500px" onclick="event.stopPropagation()">
      <span class="close-overlay" onclick="closeMetadataModal()">&times;</span>
      <h2 style="color:var(--accent); margin-top:0">✨ Generatore Metadati AI</h2>
      <p style="font-size:14px; color:#aaa; margin-bottom:20px">L'AI genererà Titolo, POV, Luogo e Riassunti in stile GoT basandosi sulla timeline globale.</p>
      
      <div class="form-group" style="margin-bottom:15px">
        <label>Modello AI</label>
        <select id="gen-model-select" style="width:100%; padding:10px; background:#111; color:#fff; border:1px solid #333; border-radius:6px;">
          <optgroup label="OpenAI">
            {''.join(f'<option value="openai|{m[0]}">{m[1]}</option>' for m in MODELS_CONFIG['openai'])}
          </optgroup>
          <optgroup label="Anthropic">
            {''.join(f'<option value="anthropic|{m[0]}">{m[1]}</option>' for m in MODELS_CONFIG['anthropic'])}
          </optgroup>
          <optgroup label="Google Gemini">
            {''.join(f'<option value="google|{m[0]}">{m[1]}</option>' for m in MODELS_CONFIG['google'])}
          </optgroup>
        </select>
      </div>

      <div class="form-group">
        <label>Modalità</label>
        <select id="gen-mode" onchange="toggleGenFields()" style="width:100%; padding:10px; background:#111; color:#fff; border:1px solid #333; border-radius:6px;">
          <option value="single">Capitolo Singolo</option>
          <option value="range">Intervallo Capitoli</option>
          <option value="all">Tutta l'Opera (1-66)</option>
        </select>
      </div>
      
      <div id="field-single" class="form-group" style="margin-top:15px">
        <label>ID Capitolo</label>
        <input type="number" id="gen-cap-id" placeholder="Es. 1" style="width:96%; padding:10px; background:#111; color:#fff; border:1px solid #333; border-radius:6px;">
      </div>
      
      <div id="field-range" class="form-group" style="margin-top:15px; display:none; gap:10px">
        <div style="flex:1">
          <label>Da (ID)</label>
          <input type="number" id="gen-start" placeholder="11" style="width:92%; padding:10px; background:#111; color:#fff; border:1px solid #333; border-radius:6px;">
        </div>
        <div style="flex:1">
          <label>A (ID)</label>
          <input type="number" id="gen-end" placeholder="20" style="width:92%; padding:10px; background:#111; color:#fff; border:1px solid #333; border-radius:6px;">
        </div>
      </div>

      <div class="form-group" style="margin-top:15px">
        <label>Prompt Dedicato / Note (Opzionale)</label>
        <textarea id="gen-extra-prompt" placeholder="Aggiungi istruzioni specifiche (es: Fokus su tradimento, stile più noir...)" style="width:100%; height:60px; padding:10px; background:#111; color:#fff; border:1px solid #333; border-radius:6px; resize:none"></textarea>
      </div>
      
      <div id="gen-status" style="margin-top:20px; padding:15px; background:#111; border-radius:6px; font-family:monospace; font-size:12px; display:none; max-height:100px; overflow-y:auto; border:1px solid #222">
      </div>
      
      <div style="margin-top:30px; text-align:right">
        <button class="btn" onclick="closeMetadataModal()" style="margin-right:10px">Annulla</button>
        <button id="btn-start-gen" class="btn btn-primary" onclick="startMetadataGen()">Avvia Generazione</button>
      </div>
    </div>
  </div>

  <script>
    // Logica Generazione Metadati
    function openMetadataModal() {{
        document.getElementById('meta-gen-modal').style.display = 'flex';
    }}
    function closeMetadataModal() {{
        document.getElementById('meta-gen-modal').style.display = 'none';
        document.getElementById('gen-status').style.display = 'none';
        document.getElementById('gen-status').innerHTML = '';
        document.getElementById('btn-start-gen').disabled = false;
    }}
    function toggleGenFields() {{
        const mode = document.getElementById('gen-mode').value;
        document.getElementById('field-single').style.display = (mode === 'single') ? 'block' : 'none';
        document.getElementById('field-range').style.display = (mode === 'range') ? 'flex' : 'none';
    }}
    function startMetadataGen() {{
        const mode = document.getElementById('gen-mode').value;
        const model = document.getElementById('gen-model-select').value;
        const extra = document.getElementById('gen-extra-prompt').value;
        const btn = document.getElementById('btn-start-gen');
        const statusDiv = document.getElementById('gen-status');
        
        let target_ids = [];
        if(mode === 'single') {{
            target_ids.push(parseInt(document.getElementById('gen-cap-id').value));
        }} else if(mode === 'range') {{
            const start = parseInt(document.getElementById('gen-start').value);
            const end = parseInt(document.getElementById('gen-end').value);
            for(let i=start; i<=end; i++) target_ids.push(i);
        }} else if(mode === 'all') {{
            for(let i=1; i<=66; i++) target_ids.push(i);
        }}
        
        btn.disabled = true;
        btn.innerText = "⏳ Generazione in corso...";
        statusDiv.style.display = 'block';
        statusDiv.innerHTML = '> Richiesta inviata all\'AI...\\n';
        
        // Costruzione payload per API Interna Sicura
        const payload = {{
            mode: mode,
            target_ids: target_ids,
            model_provider: model,
            extra_prompt: extra
        }};
        if(mode === 'single') payload.cap_id = document.getElementById('gen-cap-id').value;
        if(mode === 'range') {{
            payload.start_cap = document.getElementById('gen-start').value;
            payload.end_cap = document.getElementById('gen-end').value;
        }}
        
        fetch('/generate_metadata', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify(payload)
        }})
        .then(r => r.json())
        .then(data => {{
            if(data.status === 'success') {{
                statusDiv.innerHTML += `<span style="color:#6fcf6f">> Successo: ${{data.message}}</span>\\n`;
                setTimeout(() => window.location.reload(), 2000);
            }} else {{
                statusDiv.innerHTML += `<span style="color:#cf6f6f">> Errore: ${{data.message}}</span>\\n`;
                btn.disabled = false;
                btn.innerText = "Riprova";
            }}
        }})
        .catch(err => {{
            statusDiv.innerHTML += `<span style="color:#cf6f6f">> Errore di rete: ${{err}}</span>\\n`;
            btn.disabled = false;
            btn.innerText = "Riprova";
        }});
    }}
  </script>
  
  <div id="paste-json-container" class="card" style="display:none; margin-bottom:24px; border-color:var(--accent)">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <h2 style="margin:0;color:var(--accent)">📝 Incolla il testo del JSON qui</h2>
      <button class="btn" style="padding:2px 8px;font-size:10px" onclick="document.getElementById('paste-json-container').style.display='none'">Chiudi</button>
    </div>
    
    <div style="background:#1e1e1e;border:1px solid var(--border);border-radius:6px;padding:12px;margin-bottom:16px;font-size:12px;line-height:1.6">
      <strong style="color:var(--accent)">💡 Come funziona l'Importazione e l'Override?</strong><br>
      Inserisci un <strong>Array di oggetti</strong> (es: <code>[{...}, {...}]</code>) oppure un <strong>Oggetto Singolo</strong>.<br>
      Attenzione alla chiave <code>"id"</code> (oppure <code>"numero_capitolo"</code>) all'interno di ogni oggetto:<br>
      <ul style="margin-top:6px;padding-left:20px;color:var(--muted)">
        <li><span style="color:#6fcf6f">Se l'ID <strong>non esiste</strong> nel database:</span> Il sistema <strong>creerà un nuovo capitolo</strong> con quel numero e imposterà tutti i campi forniti. (Ottimo per generare nuovi capitoli).</li>
        <li><span style="color:#cf6f6f">Se l'ID <strong>esiste già</strong>:</span> Il sistema farà l'<strong>OVERRIDE (Aggiornamento parziale)</strong>. Modificherà solo i campi presenti nel tuo JSON e lascerà intatti quelli che ometti (es. il testo effettivo o i vecchi metadati).</li>
      </ul>
      <em>Puoi scaricare il file "Template JSON" dal pulsante in alto a destra per avere l'elenco esatto di tutte le 25 chiavi utilizzabili.</em>
    </div>
    <form method="POST" action="/import" style="display:flex;flex-direction:column;gap:12px">
      <div class="field" style="margin:0">
        <textarea name="json_text" class="tall" style="min-height:200px;font-family:monospace;font-size:12px" placeholder="Incolla l'intero oggetto o array JSON qui..."></textarea>
      </div>
      <button type="submit" class="btn btn-primary" style="align-self:flex-start">Importa i dati incollati</button>
    </form>
  </div>

  <div class="card" style="margin-bottom:24px">
    <h2 style="margin-bottom:12px; font-family:'Inter',sans-serif">📥 Esporta Opera Completa</h2>
    <div style="display:flex; gap:12px; flex-wrap:wrap">
      <a href="/export/all/full" class="btn btn-primary" style="background:#2a1f0a">ZIP Testi + Metadati</a>
      <a href="/export/all/txt" class="btn" style="background:#1e1e1e">ZIP Solo Testi</a>
      <a href="/export/all/meta" class="btn" style="background:#1e1e1e">Metadati JSON</a>
    </div>
  </div>

  <div class="stat-row">
    <div class="stat"><span class="stat-label">Parole Narrativa</span><span class="stat-val">{total_words:,}</span></div>
    <div class="stat"><span class="stat-label">Parole Riassunti</span><span class="stat-val" style="color:#6fcf6f">{total_summary_words:,}</span></div>
    <div class="stat"><span class="stat-label">Parole Metadati Core</span><span class="stat-val" style="color:#a888ca">{total_meta_words:,}</span></div>
    <div class="stat"><span class="stat-label">Capitoli</span><span class="stat-val">66</span></div>
    <div class="stat"><span class="stat-label">Target Finale</span><span class="stat-val">{sum(int(c.get('parole_target') or 0) for c in caps):,}</span></div>
    <div class="stat"><span class="stat-label">Completamento</span><span class="stat-val">{min(100,round(total_words/max(1, sum(int(c.get('parole_target') or 1) for c in caps))*100))}%</span></div>
  </div>
  <div class="filter-bar">{filter_btns}</div>
  <div class="home-grid">{cards}</div>
</div>"""

    return render_template_string(ADMIN_LAYOUT,
        title="Dashboard", content=body, all_caps_html=all_caps_html, BASE_CSS=BASE_CSS, 
        project_title=get_project_title(),
        fullSubtitle=subtitle, fullTimeline=timeline)

@app.route("/cap/<int:cap_id>", methods=["GET"])
@login_required
def view_cap(cap_id):
    cap = get_cap(cap_id)
    if not cap: return "Capitolo non trovato", 404
    testo = read_txt(cap_id)
    parole = len(testo.split())
    pov = cap.get('pov') or ''
    color = COLORI_POV.get(pov.split('/')[0].strip(), '#888')
    all_caps_html = get_sidebar_html(active_id=cap_id, is_admin=True)
    timeline_events = get_timeline()

    msg = request.args.get('msg', '')
    msg_html = ""
    if msg == "ok": msg_html = '<div class="msg ok">✓ Salvato con successo</div>'
    if msg == "err": msg_html = '<div class="msg err">✗ Errore nel salvataggio</div>'

    # Costruisci i campi del form metadati
    meta_fields = ""
    for fname, flabel, ftype in CAMPI_META:
        val = cap.get(fname) or ''
        if ftype == "text":
            meta_fields += f'<div class="field"><label>{flabel}</label><input type="text" name="{fname}" value="{val}"></div>'
        elif ftype == "select":
            opts = "".join(f'<option {"selected" if val==s else ""}>{s}</option>' for s in ["bozza","espanso","finale"])
            meta_fields += f'<div class="field"><label>{flabel}</label><select name="{fname}">{opts}</select></div>'
        elif ftype == "textarea":
            meta_fields += f'<div class="field"><label>{flabel}</label><textarea name="{fname}" rows="3">{val}</textarea></div>'

    body = f"""
<div class="topbar">
  <h1><span class="badge" style="background:{color};margin-right:8px">{pov}</span>
  {cap['id']:02d}. {cap['titolo']}</h1>
  <div class="actions">
    <a href="/export/cap/{cap_id}/full" class="btn" title="Scarica txt con metadati in testa">📥 Testo + Metadati</a>
    <a href="/export/cap/{cap_id}/txt" class="btn" title="Scarica solo la narrativa">📥 Solo Testo</a>
    <a href="/export/cap/{cap_id}/meta" class="btn" title="Scarica i campi del DB in JSON">📋 Solo Metadati</a>
    <span style="color:var(--muted);font-size:12px;margin-left:8px">{parole:,} parole</span>
    <a href="/admin" class="btn" style="margin-left:8px">← Lista</a>
  </div>
</div>
<div class="content">
{msg_html}
<div class="tabs">
  <div class="tab active" data-group="main" data-id="meta">📋 Metadati</div>
  <div class="tab" data-group="main" data-id="testo">📝 Testo</div>
  <div class="tab" data-group="main" data-id="json">⚙️ Incolla JSON Obiettivo</div>
  <div class="tab" data-group="main" data-id="vista">👁 Vista</div>
  <div class="tab" data-group="main" data-id="revisione" style="color:#6fcf6f">🤖 Revisione AI</div>
  <div class="tab" data-group="main" data-id="gen_single" style="color:var(--accent)">🔥 Generazione</div>
  <div class="tab" data-group="main" data-id="wordpress" style="color:#21759b">🌐 WordPress</div>
  <div class="tab" data-group="main" data-id="personaggi" style="color:#e8b7d4">👥 Personaggi</div>
</div>

<!-- TAB METADATI -->
<div class="tab-content active" data-tab="main" data-id="meta">
  <form method="POST" action="/cap/{cap_id}/salva/meta">
    <div class="field">
      <label>Evento Timeline Associato</label>
      <select name="timeline_event_id">
        <option value="">-- Nessun evento --</option>
        {"".join(f'<option value="{e["id"]}" {"selected" if cap.get("timeline_event_id")==e["id"] else ""}>{e["arco_inizio"]}: {e["descrizione"][:50]}...</option>' for e in timeline_events)}
      </select>
    </div>
    {meta_fields}
    <button type="submit" class="btn btn-primary">💾 Salva metadati</button>
  </form>
</div>

<!-- TAB TESTO -->
<div class="tab-content" data-tab="main" data-id="testo">
  <form id="form-testo" method="POST" action="/cap/{cap_id}/salva/testo">
    <div style="display:flex; gap:20px">
      <div style="flex:1">
        <div class="field">
          <label>Testo del capitolo — {parole:,} parole</label>
          <textarea id="editor-testo" name="testo" class="tall" rows="35" style="line-height:1.7">{testo}</textarea>
        </div>
        <div style="display:flex; gap:10px">
          <button type="submit" class="btn btn-primary">💾 Salva testo</button>
          <button type="button" onclick="runAICheck()" class="btn" style="border-color:#a888ca; color:#a888ca">🔍 Analisi AI su Save</button>
        </div>
      </div>
      
      <!-- AI CHECK SIDEBAR -->
      <div style="width:300px; display:flex; flex-direction:column; gap:15px">
        <div class="card" style="margin:0; padding:15px; border-color:#a888ca">
          <h2 style="color:#a888ca; font-size:11px">Analisi Coerenza AI</h2>
          <div class="field">
            <label>Tipo di Controllo</label>
            <select id="ai-check-scope" onchange="loadValidationPrompt()" style="font-size:12px">
              <option value="coerenza_narrativa">Coerenza Narrativa</option>
              <option value="coerenza_stilistica">Coerenza Stilistica</option>
              <option value="coerenza_caratteriale">Coerenza Caratteriale</option>
              <option value="analisi_sensoriale">Analisi Sensoriale</option>
            </select>
          </div>
          <div class="field">
            <label>System Prompt (Editabile)</label>
            <textarea id="ai-validation-prompt" rows="8" style="font-size:11px; font-family:monospace"></textarea>
          </div>
          <div style="display:flex; gap:5px">
             <button type="button" onclick="savePromptPermanently()" class="btn" style="flex:1; font-size:10px; padding:4px">💾 Salva Prompt</button>
             <button type="button" onclick="loadValidationPrompt()" class="btn" style="flex:1; font-size:10px; padding:4px">🔄 Ripristina</button>
          </div>
        </div>
        
        <div id="ai-check-results" style="background:#111; padding:10px; border-radius:6px; font-size:12px; min-height:100px; border:1px solid #222; overflow-y:auto; display:none">
           <div id="ai-check-status" style="color:var(--muted)">In attesa di analisi...</div>
        </div>
      </div>
    </div>
  </form>
</div>

<script>
function loadValidationPrompt() {{
    const scopo = document.getElementById('ai-check-scope').value;
    fetch('/api/prompts/' + scopo)
    .then(r => r.json())
    .then(data => {{
        document.getElementById('ai-validation-prompt').value = data.prompt;
    }});
}}

function savePromptPermanently() {{
    const scopo = document.getElementById('ai-check-scope').value;
    const prompt = document.getElementById('ai-validation-prompt').value;
    fetch('/api/prompts/save', {{
        method: 'POST',
        headers: {{'Content-Type':'application/json'}},
        body: JSON.stringify({{scopo: scopo, prompt: prompt}})
    }})
    .then(r => r.json())
    .then(data => {{
        if(data.status === 'ok') alert("Prompt salvato per " + scopo);
    }});
}}

function runAICheck() {{
    const statusDiv = document.getElementById('ai-check-results');
    const statusText = document.getElementById('ai-check-status');
    const text = document.getElementById('editor-testo').value;
    const prompt = document.getElementById('ai-validation-prompt').value;
    const scope = document.getElementById('ai-check-scope').value;

    statusDiv.style.display = 'block';
    statusText.innerHTML = '<span style="color:var(--accent)">⏳ Analisi in corso...</span>';
    
    // Mostriamo in anteprima che stiamo inviando i dati
    fetch('/api/ai-check', {{
        method: 'POST',
        headers: {{'Content-Type':'application/json'}},
        body: JSON.stringify({{
            cap_id: {cap_id},
            testo: text,
            custom_prompt: prompt,
            scope: scope
        }})
    }})
    .then(r => r.json())
    .then(data => {{
        if(data.error) {{
            statusText.innerHTML = '<span style="color:#cf6f6f">Errore: ' + data.error + '</span>';
        }} else {{
            // Formattazione minima
            let html = data.feedback.replace(/\\n/g, '<br>').replace(/\\*\\*(.*?)\\*\\*/g, '<b>$1</b>');
            statusText.innerHTML = '<div style="color:#eee">' + html + '</div>';
            statusText.innerHTML += '<hr style="margin:10px 0; border:0; border-top:1px solid #333">';
            statusText.innerHTML += '<button onclick="document.getElementById(\\'form-testo\\').submit()" class="btn btn-primary" style="width:100%; font-size:11px">✓ Tutto Chiaro, Salva Testo</button>';
        }}
    }})
    .catch(err => {{
        statusText.innerHTML = '<span style="color:#cf6f6f">Errore tecnico: ' + err + '</span>';
    }});
}}
// Carica il primo prompt all'avvio
document.addEventListener('DOMContentLoaded', loadValidationPrompt);
</script>

<!-- TAB JSOn -->
<div class="tab-content" data-tab="main" data-id="json">
  <div style="background:#1e1e1e;border:1px solid var(--border);border-radius:6px;padding:12px;margin-bottom:16px;font-size:12px;line-height:1.6">
    <strong style="color:var(--accent)">💡 Come sostituire metadati da JSON (Override Parziale)</strong><br>
    Incolla qui il JSON specifico di questo capitolo. <strong>Nota bene:</strong> verranno aggiornati solo i campi presenti nel JSON. Quelli che ometti (es. il testo o altri metadati) resteranno invariati.<br>
    Puoi incollare il singolo oggetto <code>{{ "id": {cap_id}, "pov": "...", ... }}</code> oppure un intero pacchetto array.
  </div>
  <form method="POST" action="/import" style="display:flex;flex-direction:column;gap:12px">
    <input type="hidden" name="fallback_id" value="{cap_id}">
    <div class="field" style="margin:0">
      <textarea name="json_text" class="tall" style="min-height:300px;font-family:monospace;font-size:12px" placeholder="Incolla l'oggetto JSON per questo capitolo..."></textarea>
    </div>
    <button type="submit" class="btn btn-primary" style="align-self:flex-start">Sovrascrivi dati con JSON incollato</button>
  </form>
</div>

<!-- TAB VISTA -->
<div class="tab-content" data-tab="main" data-id="vista">
  <div class="card">
    <div style="font-size:11px;color:var(--muted);text-transform:uppercase;margin-bottom:8px">{cap.get('luogo') or ''} &mdash; {cap.get('data_narrativa') or ''}</div>
    <h2 style="font-size:24px;color:var(--accent);margin-bottom:16px">{cap['titolo']}</h2>
    <div style="font-family:'Georgia',serif;line-height:1.9;font-size:15px">
      {"".join(f"<p style='margin-bottom:1rem'>{p}</p>" for p in testo.split(chr(10)+chr(10)) if p.strip())}
    </div>
  </div>
  <div class="card" style="margin-top:16px">
    <h2>Metadati</h2>
    <table style="width:100%;font-size:12px;border-collapse:collapse">
      {"".join(f'<tr><td style="padding:6px;color:var(--muted);width:35%;border-bottom:1px solid var(--border)">{fname.upper().replace("_"," ")}</td><td style="padding:6px;border-bottom:1px solid var(--border)">{cap.get(fname) or "<em style=color:var(--muted)>—</em>"}</td></tr>' for fname,_,_ in CAMPI_META)}
    </table>
  </div>
</div>

<!-- TAB REVISIONE -->
<div class="tab-content" data-tab="main" data-id="revisione">
  <div class="card" style="border-color:#6fcf6f">
    <h2 style="color:#6fcf6f">🤖 Revisione Intelligente del Capitolo</h2>
    <p style="font-size:12px; color:var(--muted); margin-bottom:16px">
      L'AI analizzerà il testo attuale applicando gli Obiettivi Generali e le tue Istruzioni Specifiche.
    </p>
    
    <form action="/generazione/revisione/{cap_id}" method="POST">
        <div class="field">
          <label style="color:#6fcf6f">🎯 Obiettivi Globali (Vengono salvati nelle Impostazioni)</label>
          <textarea name="global_goals" rows="2" style="font-size:13px">{get_env_var('PROJECT_REVISION_GOALS') or ''}</textarea>
        </div>

        <div class="field">
          <label style="color:#c9a96e">📝 Istruzioni Specifiche per questo Capitolo (Salvate nei Metadati)</label>
          <textarea name="cap_instructions" rows="2" style="font-size:13px">{cap.get('revisione_istruzioni') or ''}</textarea>
        </div>

        <div style="background:rgba(111,207,111,0.05); padding:12px; border-radius:6px; border:1px solid rgba(111,207,111,0.2); margin-bottom:16px; display:flex; align-items:center; gap:10px">
          <span style="font-size:20px">🔗</span>
          <div style="font-size:12px"><b>Continuità attiva:</b> Il sistema caricherà il contesto dal Capitolo {cap_id-1 if cap_id > 1 else 'Inizio'}.</div>
        </div>

        <div style="display:flex; gap:12px; align-items:flex-end">
          <div class="field" style="flex:1; margin-bottom:0">
              <label>Seleziona Modello</label>
              <select name="model" class="btn" style="background:#1a1a1a; width:100%; text-align:left">
                  <optgroup label="Local / Custom (LM Studio)">
                      <option value="lmstudio|{get_env_var('ADMIN_CHAT_MODEL', 'custom')}">LM Studio Predefinito</option>
                  </optgroup>
                  <optgroup label="OpenAI">
                      {''.join(f'<option value="openai|{m[0]}" {"selected" if get_env_var("ADMIN_CHAT_MODEL")==m[0] else ""}>{m[1]}</option>' for m in MODELS_CONFIG['openai'])}
                  </optgroup>
                  <optgroup label="Anthropic">
                      {''.join(f'<option value="anthropic|{m[0]}" {"selected" if get_env_var("ADMIN_CHAT_MODEL")==m[0] else ""}>{m[1]}</option>' for m in MODELS_CONFIG['anthropic'])}
                  </optgroup>
                  <optgroup label="Google Gemini">
                      {''.join(f'<option value="google|{m[0]}" {"selected" if get_env_var("ADMIN_CHAT_MODEL")==m[0] else ""}>{m[1]}</option>' for m in MODELS_CONFIG['google'])}
                  </optgroup>
              </select>
          </div>
          <button type="submit" class="btn btn-primary" style="background:#2d5a2d; border-color:#6fcf6f; height:42px">🔥 Avvia Revisione AI</button>
        </div>
    </form>
    
    <div style="margin-top:20px; font-size:11px; color:var(--muted); line-height:1.4">
      <b>Nota:</b> La revisione sostituirà il testo attuale del capitolo. Fai un backup se necessario.
    </div>
  </div>
</div>

<!-- TAB GENERAZIONE SINGOLA -->
<div class="tab-content" data-tab="main" data-id="gen_single">
  <div class="card" style="border-color:var(--accent)">
    <h2 style="color:var(--accent)">🔥 Generazione Narrativa Capitolo {cap_id:02d}</h2>
    <p style="color:var(--muted); font-size:12px; margin-bottom:16px">
      Lancia la scrittura del capitolo da zero usando la pipeline multi-step.
    </p>

    <div class="field">
      <label>Prompt di Personalizzazione (Opzionale)</label>
      <textarea id="single_custom_prompt" placeholder="Es. 'Aggiungi più tensione alla fine'" style="height:60px"></textarea>
    </div>

    <div style="display:flex; gap:12px; align-items:flex-end; margin-bottom:20px">
        <div class="field" style="flex:1; margin-bottom:0">
            <label>Seleziona Modello</label>
            <select id="single_gen_model" class="btn" style="background:#1a1a1a; width:100%">
                 <option value="lmstudio|{get_env_var('ADMIN_CHAT_MODEL', 'custom')}">LM Studio (Locale)</option>
                {''.join(f'<option value="openai|{m[0]}">{m[1]}</option>' for m in MODELS_CONFIG['openai'])}
                {''.join(f'<option value="anthropic|{m[0]}">{m[1]}</option>' for m in MODELS_CONFIG['anthropic'])}
            </select>
        </div>
        <button onclick="startSingleGen({cap_id})" class="btn btn-primary" style="height:42px">🚀 Avvia Generazione</button>
    </div>

    <div id="single-ai-status" style="background:#111; padding:12px; border-radius:6px; border:1px solid #333; display:none">
        <div id="single-status-text" style="font-family:monospace; font-size:12px; color:#aaa; margin-bottom:8px">Ready...</div>
        <div style="width:100%; height:8px; background:#222; border-radius:4px; overflow:hidden">
            <div id="single-progress-bar" style="width:0%; height:100%; background:var(--accent); transition: width 0.5s"></div>
        </div>
    </div>
    <script>
    function startSingleGen(id) {{
        if(!confirm("Vuoi rigenerare integralmente questo capitolo?")) return;
        const statusBox = document.getElementById('single-ai-status');
        const statusText = document.getElementById('single-status-text');
        const pBar = document.getElementById('single-progress-bar');
        
        statusBox.style.display = 'block';
        statusText.textContent = "Inizializzazione...";
        
        const prompt = document.getElementById('single_custom_prompt').value;
        const model = document.getElementById('single_gen_model').value;

        fetch('/api-book/ai/execute', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json', 'Authorization': 'Bearer {get_env_var("API_TOKEN", "123456789")}' }},
            body: JSON.stringify({{
                user_code: '{get_env_var("API_USER_CODE", "admin99")}',
                action: 'generate-narrative',
                target_ids: [id],
                base_prompt: prompt,
                model_provider: model
            }})
        }})
        .then(r => r.json())
        .then(data => {{
            if(data.status === 'success') {{ pollSingleStatus(); }}
            else {{ alert("Errore: " + data.message); }}
        }});
    }}

    function pollSingleStatus() {{
        fetch('/api-book/ai/execute', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json', 'Authorization': 'Bearer {get_env_var("API_TOKEN", "123456789")}' }},
            body: JSON.stringify({{ user_code: '{get_env_var("API_USER_CODE", "admin99")}', action: 'get-ai-status' }})
        }})
        .then(r => r.json())
        .then(res => {{
            const d = res.data;
            if(d.status !== 'idle') {{
                document.getElementById('single-status-text').textContent = d.message || "Working...";
                document.getElementById('single-progress-bar').style.width = d.progress + '%';
                if(d.status !== 'completed' && d.status !== 'error') {{ setTimeout(pollSingleStatus, 2000); }}
                else if(d.status === 'completed') {{ 
                    document.getElementById('single-status-text').textContent = "COMPLETATO! Ricarica la pagina."; 
                    setTimeout(() => location.reload(), 1500);
                }}
            }}
        }});
    }}
    </script>
  </div>
</div>

<!-- TAB WORDPRESS -->
<div class="tab-content" data-tab="main" data-id="wordpress">
  <div class="card" style="border-color:#21759b">
    <h2 style="color:#21759b">🌐 Pubblicazione su WordPress</h2>
    <p style="font-size:12px; color:var(--muted); margin-bottom:20px">
        Invia questo capitolo come articolo al tuo sito WordPress. Assicurati che le <b>Application Passwords</b> siano abilitate.
    </p>

    <form action="/cap/{cap_id}/publish/wordpress" method="POST">
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px; margin-bottom:24px">
            <div class="field_group">
                <h3 style="font-size:14px; color:#21759b; margin-bottom:12px">Parametri Connessione</h3>
                <div class="field"><label>URL Sito (es: https://miosito.it)</label><input type="text" name="wp_url" value="{load_wp_settings().get('wp_url', '')}" required></div>
                <div class="field"><label>Nome Utente WP</label><input type="text" name="wp_user" value="{load_wp_settings().get('wp_user', '')}" required></div>
                <div class="field"><label>Application Password</label><input type="password" name="wp_app_pass" value="{load_wp_settings().get('wp_app_pass', '')}" required></div>
                <div class="field"><label><input type="checkbox" name="save_settings" checked> Salva questi dati come predefiniti</label></div>
            </div>
            
            <div class="field_group">
                <h3 style="font-size:14px; color:#21759b; margin-bottom:12px">Tassonomie & Riassunto</h3>
                <div class="field"><label>Categoria (Singola - Nome)</label><input type="text" name="wp_category" value="{cap.get('linea_narrativa', '')}"></div>
                <div class="field"><label>Tags (Separati da virgola)</label><input type="text" name="wp_tags" value="{cap.get('pov', '').split('/')[0] if '/' in cap.get('pov', '') else cap.get('pov', '')}"></div>
                <div class="field"><label>Excerpt (Riassunto WP)</label><textarea name="wp_excerpt" rows="3">{cap.get('riassunto', '')}</textarea></div>
            </div>
        </div>

        <div class="card" style="background:rgba(33, 117, 155, 0.05); border:1px solid rgba(33, 117, 155, 0.2); margin-bottom:24px">
            <h3 style="font-size:14px; color:#21759b; margin-bottom:12px">Impostazioni SEO (RankMath / Yoast)</h3>
            <div style="display:flex; gap:20px; margin-bottom:15px">
                <label><input type="radio" name="seo_plugin" value="rankmath" {'checked' if load_wp_settings().get('seo_plugin') == 'rankmath' else ''}> RankMath</label>
                <label><input type="radio" name="seo_plugin" value="yoast" {'checked' if load_wp_settings().get('seo_plugin') == 'yoast' else ''}> Yoast SEO</label>
            </div>
            <div class="field"><label>SEO Title (Focus Keyword)</label><input type="text" name="seo_title" value="{cap['titolo']}"></div>
            <div class="field"><label>SEO Description</label><textarea name="seo_description" rows="2">{cap.get('riassunto', '')[:160]}</textarea></div>
        </div>

        <div style="text-align:right">
            <button type="submit" class="btn btn-primary" style="background:#21759b; border-color:#21759b; padding:12px 30px">🚀 Pubblica/Aggiorna su WordPress</button>
        </div>
    </form>
  </div>
</div>

<!-- TAB PERSONAGGI -->
<div class="tab-content" data-tab="main" data-id="personaggi">
  <div class="card" style="border-color:#e8b7d4">
    <h2 style="color:#e8b7d4">👥 Personaggi — Capitolo {cap_id:02d}</h2>
    <p style="font-size:12px;color:var(--muted);margin-bottom:16px">
      Stato e azioni di ogni personaggio in questo capitolo. <a href="/personaggi" style="color:#e8b7d4">Gestisci tutti i personaggi →</a>
    </p>
    <div id="cap-personaggi-list" style="display:grid;gap:10px">
      <div style="color:var(--muted);font-size:12px;text-align:center;padding:20px">⏳ Caricamento...</div>
    </div>
  </div>
</div>

<script>
(function loadCapPersonaggi() {{
  fetch('/api/cap/{cap_id}/personaggi')
  .then(r => r.json())
  .then(data => {{
    const container = document.getElementById('cap-personaggi-list');
    if(!data || !data.length) {{
      container.innerHTML = '<p style="color:var(--muted);text-align:center;padding:20px">Nessun personaggio. <a href="/personaggi/nuovo" style="color:#e8b7d4">Crea il primo →</a></p>';
      return;
    }}
    container.innerHTML = data.map(p => {{
      const color = p.colore || '#888';
      const presente = p.presente;
      const fields = presente ? `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;margin-top:10px">
          ${{p.luogo ? `<div><b style="color:var(--muted)">Luogo:</b> ${{p.luogo}}</div>` : ''}}
          ${{p.stato_emotivo ? `<div><b style="color:var(--muted)">Stato:</b> ${{p.stato_emotivo}}</div>` : ''}}
          ${{p.obiettivo ? `<div><b style="color:var(--muted)">Obiettivo:</b> ${{p.obiettivo}}</div>` : ''}}
          ${{p.sviluppo ? `<div style="grid-column:1/-1"><b style="color:var(--muted)">Sviluppo:</b> ${{p.sviluppo}}</div>` : ''}}
        </div>` : `<div style="font-size:11px;color:var(--muted);margin-top:6px">${{p.azione_parallela ? `Altrove: ${{p.azione_parallela}}` : '— non presente in scena'}}</div>`;
      return `<div style="border:1px solid ${{color}}33;border-left:4px solid ${{color}};border-radius:8px;padding:12px;background:${{presente ? color+'11' : 'transparent'}}">
        <div style="display:flex;align-items:center;gap:10px">
          <span style="width:9px;height:9px;border-radius:50%;background:${{color}};flex-shrink:0"></span>
          <strong style="color:${{color}}">${{p.nome}}</strong>
          <span style="font-size:11px;color:var(--muted)">${{p.ruolo || ''}}</span>
          <span style="margin-left:auto;font-size:10px;padding:2px 8px;border-radius:4px;background:${{presente?'#1a2e1a':'#1a1a1a'}};color:${{presente?'#6fcf6f':'var(--muted)'}}">${{presente?'● Presente':'○ Assente'}}</span>
          <a href="/personaggio/${{p.id}}" style="font-size:11px;color:var(--accent);text-decoration:none;border:1px solid var(--border);padding:2px 8px;border-radius:4px">Scheda →</a>
        </div>
        ${{fields}}
      </div>`;
    }}).join('');
  }})
  .catch(() => {{
    document.getElementById('cap-personaggi-list').innerHTML = '<p style="color:#cf6f6f">Errore caricamento personaggi.</p>';
  }});
}})();
</script>
</div>"""

    return render_template_string(ADMIN_LAYOUT,
        title=f"Cap {cap_id:02d} — {cap['titolo']}",
        content=body, all_caps_html=all_caps_html, BASE_CSS=BASE_CSS, project_title=get_project_title())

@app.route("/cap/<int:cap_id>/salva/meta", methods=["POST"])
@login_required
def salva_meta(cap_id):
    campi = [f[0] for f in CAMPI_META]
    updates = {k: request.form.get(k, '') or None for k in campi}
    try:
        conn = get_conn()
        set_clause = ", ".join(f"{k}=?" for k in updates)
        vals = list(updates.values()) + [cap_id]
        conn.execute(f"UPDATE capitoli SET {set_clause} WHERE id=?", vals)
        conn.commit()
        conn.close()
        return redirect(url_for('view_cap', cap_id=cap_id, msg='ok'))
    except Exception as e:
        print(e)
        return redirect(url_for('view_cap', cap_id=cap_id, msg='err'))

@app.route("/cap/<int:cap_id>/salva/testo", methods=["POST"])
@login_required
def salva_testo(cap_id):
    testo = request.form.get('testo', '')
    try:
        words = write_txt(cap_id, testo)
        conn = get_conn()
        conn.execute("UPDATE capitoli SET parole_file=? WHERE id=?", (words, cap_id))
        conn.commit()
        conn.close()
        return redirect(url_for('view_cap', cap_id=cap_id, msg='ok'))
    except Exception as e:
        print(e)
        return redirect(url_for('view_cap', cap_id=cap_id, msg='err'))

@app.route("/cap/add", methods=["POST"])
@login_required
def add_cap():
    try:
        conn = get_conn()
        # count the current max ID
        row = conn.execute("SELECT MAX(id) as max_id FROM capitoli").fetchone()
        new_id = (row['max_id'] or 0) + 1
        titolo = f"Capitolo {new_id}"
        conn.execute("INSERT INTO capitoli (id, titolo, stato) VALUES (?, ?, ?)", (new_id, titolo, "bozza"))
        conn.commit()
        conn.close()
        # Initialize an empty txt file
        write_txt(new_id, "")
        return redirect(url_for('view_cap', cap_id=new_id, msg='ok'))
    except Exception as e:
        print(e)
        return redirect(url_for('admin_dashboard', msg='err'))

@app.route("/import", methods=["POST"])
@login_required
def import_json_route():
    data = None
    if 'file' in request.files and request.files['file'].filename != '':
        try:
            data = json.load(request.files['file'])
        except Exception as e:
            print("Errore formato file:", e)
            return redirect(url_for('index', msg='err_file'))
    elif 'json_text' in request.form and request.form['json_text'].strip() != '':
        try:
            data = json.loads(request.form['json_text'])
        except Exception as e:
            print("Errore parsing testo JSON:", e)
            return redirect(url_for('index', msg='err_import'))
            
    if data is None:
        return redirect(url_for('index', msg='err_file'))
        
    try:
        # data è già stato caricato sopra (json.load o json.loads)
        logger.info(f"Inizio importazione JSON...")
        items = []
        if isinstance(data, dict):
            if "capitoli" in data and isinstance(data["capitoli"], list):
                items = data["capitoli"]
            else:
                items = [data]
        elif isinstance(data, list):
            items = data
            
        conn = get_conn()
        campi_db = [f[0] for f in CAMPI_META]
        
        count = 0
        for item in items:
            num = item.get('numero_capitolo')
            if not num:
                raw_id = item.get('id')
                if isinstance(raw_id, int): num = raw_id
                elif isinstance(raw_id, str):
                    import re
                    match = re.search(r'\d+', raw_id)
                    if match: num = int(match.group())
            
            if not num:
                # Fallback al cap_id passato dal form se presente
                num = request.form.get('fallback_id')
            
            num = int(num)
            row = conn.execute("SELECT id FROM capitoli WHERE id=?", (num,)).fetchone()
            
            updates = {}
            for k in campi_db:
                if k in item:
                    val = item[k]
                    if isinstance(val, list):
                        val = "\n".join(str(v) for v in val)
                    updates[k] = val
                    
            if not row:
                if not updates.get('titolo'): updates['titolo'] = f"Capitolo {num}"
                if not updates.get('stato'): updates['stato'] = "bozza"
                cols = ['id'] + list(updates.keys())
                vals = [num] + list(updates.values())
                placeholders = ",".join(["?"] * len(cols))
                conn.execute(f"INSERT INTO capitoli ({','.join(cols)}) VALUES ({placeholders})", vals)
            else:
                if updates:
                    set_clause = ", ".join(f"{k}=?" for k in updates.keys())
                    vals = list(updates.values()) + [num]
                    conn.execute(f"UPDATE capitoli SET {set_clause} WHERE id=?", vals)
            
            # Gestione del campo 'testo' o 'content' separatamente (Filesystem)
            testo_json = item.get('testo') or item.get('content')
            if testo_json:
                words = write_txt(num, testo_json)
                conn.execute("UPDATE capitoli SET parole_file=? WHERE id=?", (words, num))
                
            count += 1
            
        conn.commit()
        conn.close()
        logger.info(f"Importazione completata: {count} capitoli.")
        return redirect(url_for('admin_dashboard', msg=f'ok_import_{count}'))
    except Exception as e:
        logger.error(f"Errore durante l'import JSON: {e}", exc_info=True)
        return redirect(url_for('admin_dashboard', msg='err_import'))

@app.route("/flow")
@login_required
def flow_page():
    # Pagina di spiegazione del flusso di lavoro
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Flusso di Lavoro - {{ p_title }}</title>
        <link rel="stylesheet" href="{{ url_for('static', filename='style.css') if static_exists else '' }}">
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #1a1a1a; color: #eee; line-height: 1.6; padding: 40px; }
            .container { max-width: 900px; margin: 0 auto; background: #252525; padding: 40px; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
            h1 { color: #e8d5b7; border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 30px; }
            .step { margin-bottom: 40px; position: relative; padding-left: 60px; }
            .step-num { position: absolute; left: 0; top: 0; width: 40px; height: 40px; background: #e8d5b7; color: #1a1a1a; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 20px; }
            .step-title { font-size: 22px; font-weight: bold; color: #fff; margin-bottom: 10px; }
            .step-desc { color: #ccc; }
            .arrow { text-align: center; font-size: 30px; color: #444; margin: 20px 0; }
            code { background: #333; padding: 2px 6px; border-radius: 4px; color: #e8d5b7; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>⚙️ Flusso Narrazione AI</h1>
            
            <div class="step">
                <div class="step-num">1</div>
                <div class="step-title">Configurazione Globale (.env)</div>
                <div class="step-desc">Definisci il <code>Titolo</code>, il <code>Sottotitolo</code> (tema) e la <code>Timeline Globale</code> dell'opera. Questi sono i pilastri su cui poggia l'intera coerenza del romanzo.</div>
            </div>
            <div class="arrow">↓</div>
            
            <div class="step">
                <div class="step-num">2</div>
                <div class="step-title">Generazione Metadati & Adaptive Splitting</div>
                <div class="step-desc">L'AI genera i metadati (POV, Luogo) e divide il capitolo in <b>Parti</b>. Questa scomposizione (Adaptive Splitter) previene il collasso della memoria nei capitoli lunghi.</div>
            </div>
            <div class="arrow">↓</div>
            
            <div class="step">
                <div class="step-num">3</div>
                <div class="step-title">Pianificazione Scene (Planner)</div>
                <div class="step-desc">Per ogni parte, l'AI crea una scaletta di mini-beat (1000-1500 parole totali per parte). Ogni beat ha un obiettivo sensoriale specifico.</div>
            </div>
            <div class="arrow">↓</div>
            
            <div class="step">
                <div class="step-num">4</div>
                <div class="step-title">Ciclo Scrittura & Revisione (Drafter + Reviewer)</div>
                <div class="step-desc">L'AI scrive un beat (Drafter) e lo passa immediatamente a un Editor (Reviewer) che controlla lo stile. Questo ciclo si ripete finché il capitolo non è completo.</div>
            </div>
            
            <div style="margin-top: 50px; text-align: center;">
                <a href="/" style="color: #e8d5b7; text-decoration: none;">← Torna alla Dashboard</a>
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, p_title=get_project_title())

@app.route("/rebuild")
@login_required
def rebuild():
    import subprocess
    subprocess.run(["python", "build_from_db.py"], cwd=os.getcwd())
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/sync")
@login_required
def admin_sync():
    """Sincronizza i conteggi parole dei file fisici nel database."""
    caps = get_all()
    conn = get_conn()
    for c in caps:
        txt = read_txt(c['id'])
        words = len(txt.split())
        conn.execute("UPDATE capitoli SET parole_file=? WHERE id=?", (words, c['id']))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard', msg='ok_sync'))

def cap_to_meta_text(cap, testo):
    lines = [
        f"PRIMA VIVI POI SPIEGHI — Capitolo {cap['id']:02d}",
        f"Titolo: {cap['titolo']}",
        f"POV: {cap['pov'] or ''}",
        f"Luogo: {cap['luogo'] or ''}",
        f"Data: {cap['data_narrativa'] or ''}",
        f"Stato: {cap['stato'] or ''}",
        f"Parole: {len(testo.split())}",
        ""
    ]
    for k, v in cap.items():
        if k not in ('id','titolo','pov','luogo','data_narrativa','stato') and v is not None:
            lines.extend([f"{k.upper()}", str(v), ""])
    lines.extend(["="*60, "TESTO", "="*60, "", testo])
    return "\\n".join(lines)

@app.route("/generazione/revisione/<int:cap_id>", methods=["POST"])
@login_required
def ai_revisione(cap_id):
    selected = request.form.get('model', 'openai|gpt-4o')
    global_goals = request.form.get('global_goals', '')
    cap_instructions = request.form.get('cap_instructions', '')
    
    # Persistenza Obiettivi Globali
    if global_goals:
        set_env_var("PROJECT_REVISION_GOALS", global_goals)
    
    # Persistenza Istruzioni Capitolo nel DB
    try:
        conn = get_conn()
        conn.execute("UPDATE capitoli SET revisione_istruzioni=? WHERE id=?", (cap_instructions, cap_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Errore salvataggio istruzioni revisione: {e}")

    if '|' in selected:
        provider, model = selected.split('|')
    else:
        provider = "openai"
        model = selected

    api_key = ""
    if provider == "openai": api_key = get_env_var("OPENAI_API_KEY")
    elif provider == "anthropic": api_key = get_env_var("CLAUDE_API_KEY")
    elif provider == "google": api_key = get_env_var("GEMINI_API_KEY")
    elif provider == "lmstudio": api_key = get_env_var("LMSTUDIO_API_KEY", "no-key")
    
    if not api_key:
        return redirect(url_for('view_cap', cap_id=cap_id, msg='err_no_key'))

    cap = get_cap(cap_id)
    if not cap: return "Capitolo non trovato", 404
    original_text = read_txt(cap_id)
    
    prompts = load_prompts()
    
    # --- DEEP ANALYSIS (Universal Flight Manual) ---
    logger.info(f"Revision: Running Deep Context Analysis (Multi-Message) for Cap {cap_id}")
    context_messages = run_deep_context_pipeline(cap_id, provider, model, api_key, admin_mode=True)

    sys_instr = prompts.get("system_instruction", "")
    rev_prompt_tpl = prompts.get("revisione_prompt", "")
    
    # Formattazione sicura del prompt
    prompt = rev_prompt_tpl.replace("{cap_id}", str(cap_id))\
                           .replace("{prev_id}", "MULTI_MESSAGE_CONTEXT")\
                           .replace("{previous_text}", "Incorporato nella history.")\
                           .replace("{titolo}", str(cap.get('titolo','')))\
                           .replace("{pov}", str(cap.get('pov','')))\
                           .replace("{descrizione}", str(cap.get('descrizione','')))\
                           .replace("{riassunto}", str(cap.get('riassunto','')))\
                           .replace("{revision_goals}", str(global_goals))\
                           .replace("{cap_instructions}", str(cap_instructions))\
                           .replace("{original_text}", str(original_text))
    
    # Aggiungiamo il prompt di revisione come ultimo messaggio
    context_messages.append({"role": "user", "content": prompt})
    
    try:
        from llm_client import generate_chapter_text, extract_narrative
        resp_text = generate_chapter_text("", provider, model, api_key, system=sys_instr, messages=context_messages)
        new_text = extract_narrative(resp_text)
        
        # Salvataggio
        words = write_txt(cap_id, new_text)
        
        conn = get_conn()
        conn.execute("UPDATE capitoli SET parole_file=?, stato='bozza' WHERE id=?", (words, cap_id))
        conn.commit()
        conn.close()
        
        return redirect(url_for('view_cap', cap_id=cap_id, msg='ok'))
    except Exception as e:
        logger.error(f"Errore revisione AI cap {cap_id}: {e}")
        return redirect(url_for('view_cap', cap_id=cap_id, msg='err'))

@app.route("/export/cap/<int:cap_id>/meta")
@login_required
def export_cap_meta(cap_id):
    cap = get_cap(cap_id)
    if not cap: return "Not found", 404
    return jsonify(cap)

@app.route("/export/cap/<int:cap_id>/txt")
@login_required
def export_cap_txt(cap_id):
    cap = get_cap(cap_id)
    if not cap: return "Not found", 404
    testo = read_txt(cap_id)
    bio = io.BytesIO(testo.encode('utf-8'))
    norm_title = cap['titolo'].replace(' ', '_')
    return send_file(bio, as_attachment=True, download_name=f"cap{cap_id:02d}_{norm_title}.txt", mimetype="text/plain")

@app.route("/export/cap/<int:cap_id>/full")
@login_required
def export_cap_full(cap_id):
    cap = get_cap(cap_id)
    if not cap: return "Not found", 404
    testo = read_txt(cap_id)
    content = cap_to_meta_text(cap, testo)
    bio = io.BytesIO(content.encode('utf-8'))
    norm_title = cap['titolo'].replace(' ', '_')
    return send_file(bio, as_attachment=True, download_name=f"cap{cap_id:02d}_{norm_title}_con_metadati.txt", mimetype="text/plain")

@app.route("/export/template")
@login_required
def export_template():
    sample_data = {
        "_istruzioni": "usa 'id' o 'numero_capitolo' per indicare il capitolo. Se ESISTE, i campi verranno AGGIORNATI sovrascrivendo solo quelli forniti. Se NON ESISTE, verrà creato un NUOVO capitolo. Puoi omettere i campi che non vuoi modificare.",
        "capitoli": [
            {
                "id": 99,
                "numero_capitolo": 99,
                "titolo": "Esempio Testo Completo",
                "pov": "Lin",
                "anno": 2026,
                "luogo": "Tetto dell'Ambasciata",
                "luogo_macro": "Roma",
                "linea_narrativa": "Lin",
                "data_narrativa": "2026-03-05",
                "stato": "bozza",
                "parole_target": 1500,
                "personaggi_capitolo": [
                    "Lin",
                    "Michael"
                ],
                "personaggi_precedenti": [
                    "Info da ricordare sul passato di Lin"
                ],
                "personaggi_successivi": [
                    "Info da agganciare per il prossimo capitolo"
                ],
                "scene_outline": [
                    "Scena 1: Lin osserva la folla.",
                    "Scena 2: Michael arriva alle sue spalle."
                ],
                "oggetti_simbolo": "Orologio rotto",
                "tensione_capitolo": "Alta",
                "hook_finale": "Un'esplosione udita in lontananza.",
                "rischi_incoerenza": "Controllare che Lin non sappia ancora di Neda.",
                "transizione_prossimo_capitolo": "Passaggio immediato al POV di Neda nella metro.",
                "descrizione": "Una descrizione veloce per referenza interna.",
                "background": "Nel frattempo, Artem sta cercando i file a Kiev.",
                "parallelo": "Neda è braccata nella metro.",
                "obiettivi_personaggi": "Lin: fuggire / Michael: catturarlo",
                "timeline_capitolo": "14:00 - 14:15",
                "timeline_opera": "Giorno 3",
                "riassunto": "Riassunto compatto degli eventi.",
                "riassunto_capitolo_precedente": "Il capitolo prima, Lin era scappato.",
                "riassunto_capitolo_successivo": "Il capitolo dopo si vede lo schianto."
            }
        ]
    }
    bio = io.BytesIO(json.dumps(sample_data, indent=4, ensure_ascii=False).encode('utf-8'))
    return send_file(bio, as_attachment=True, download_name="template_import_capitoli.json", mimetype="application/json")


@app.route("/export/advanced/<mode>")
@login_required
def export_advanced(mode):
    conn = get_conn()
    
    if mode == "testo":
        caps = conn.execute("SELECT * FROM capitoli ORDER BY id").fetchall()
        mem_zip = io.BytesIO()
        with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for c in caps:
                testo = read_txt(c['id'])
                fname = f"cap{c['id']:02d}_{c['titolo'].replace(' ', '_')}.txt"
                zf.writestr(fname, testo.encode('utf-8'))
        mem_zip.seek(0)
        conn.close()
        return send_file(mem_zip, mimetype="application/zip", as_attachment=True, download_name="prima-vivi-poi-spieghi_solo_testo.zip")

    elif mode == "meta_singolo":
        entity = request.args.get("entity", "capitoli")
        if entity not in ["capitoli", "timeline", "personaggi", "personaggi_capitoli"]:
            conn.close()
            return "Invalid entity", 400
        
        order_by = "id"
        if entity == "timeline": order_by = "arco_inizio"
        elif entity == "personaggi_capitoli": order_by = "capitolo_id, personaggio_id"
        
        rows = conn.execute(f"SELECT * FROM {entity} ORDER BY {order_by}").fetchall()
        data = [dict(r) for r in rows]
        conn.close()
        bio = io.BytesIO(json.dumps(data, indent=2, ensure_ascii=False).encode('utf-8'))
        return send_file(bio, as_attachment=True, download_name=f"export_{entity}.json", mimetype="application/json")

    elif mode == "full_relational":
        capitoli_rows = conn.execute("SELECT * FROM capitoli ORDER BY id").fetchall()
        timeline_rows = conn.execute("SELECT * FROM timeline ORDER BY arco_inizio").fetchall()
        personaggi_rows = conn.execute("SELECT * FROM personaggi ORDER BY id").fetchall()
        pers_cap_rows = conn.execute("SELECT * FROM personaggi_capitoli ORDER BY capitolo_id, personaggio_id").fetchall()
        conn.close()
        
        # COSTRUZIONE STRUTTURA RELAZIONALE
        timeline_dict = {t['id']: dict(t) for t in timeline_rows}
        for t_id in timeline_dict: timeline_dict[t_id]['capitoli_associati'] = []
            
        pers_dict = {p['id']: dict(p) for p in personaggi_rows}
        
        presenze_per_capitolo = {}
        for pc in pers_cap_rows:
            cid = pc['capitolo_id']
            if cid not in presenze_per_capitolo: presenze_per_capitolo[cid] = []
            pers_data = pers_dict.get(pc['personaggio_id'], {})
            
            presenze_per_capitolo[cid].append({
                "personaggio": pers_data.get('nome', 'Sconosciuto'),
                "ruolo_nel_romanzo": pers_data.get('ruolo', ''),
                "presente_in_scena": bool(pc['presente']),
                "luogo_azione": pc['luogo'],
                "stato_emotivo": pc['stato_emotivo'],
                "obiettivo_scena": pc['obiettivo'],
                "azione_parallela": pc['azione_parallela'],
                "sviluppo_personaggio": pc['sviluppo'],
                "note_regia": pc['note']
            })

        capitoli_list = []
        for c in capitoli_rows:
            cap_dict = dict(c)
            cap_dict['testo_narrativo'] = read_txt(c['id'])
            cap_dict['personaggi_coinvolti'] = presenze_per_capitolo.get(c['id'], [])
            capitoli_list.append(cap_dict)
            
            t_id = cap_dict.get('timeline_event_id')
            if t_id and t_id in timeline_dict:
                timeline_dict[t_id]['capitoli_associati'].append({
                    "id": cap_dict['id'],
                    "titolo": cap_dict['titolo'],
                    "pov": cap_dict['pov']
                })
        
        master_json = {
            "_documentazione_software": {
                "descrizione": "Export master relazionale del progetto PRIMA VIVI POI SPIEGHI. Questa struttura consolida l'intero database e i file testuali dell'opera in un unico documento navigabile.",
                "struttura": {
                    "timeline_eventi": "Lista cronologica degli eventi (archi creati per dare contesto globale all'AI). Ogni evento lista i capitoli associati in 'capitoli_associati'.",
                    "capitoli_completati": "La struttura portante. Oltre ai metadati del DB (POV, luogo, riassunto, tensioni, obiettivi), include il 'testo_narrativo' (il romanzo testuale effettivo) e l'array 'personaggi_coinvolti' che documenta chi era in scena, cosa provava e l'azione parallela di chi era assente.",
                    "anagrafica_personaggi": "Anagrafica completa e background profondo dei personaggi strutturati nel DB."
                },
                "motore_ai": "L'app Flask utilizza questo stesso formato relazionale frammentando i dati per iniettare contesto mirato (Timeline, Riassunti precedenti, Obiettivi dei personaggi) negli LLM (GPT, Claude, Gemini) quando rigenerano i testi o analizzano la correttezza della trama (pipeline multi-messaggio).",
                "versione": "Export Finale Relazionale Unificato"
            },
            "opera": {
                "titolo": get_project_title(),
                "sottotitolo": get_env_var('PROJECT_SUBTITLE', ''),
                "totale_capitoli": len(capitoli_list)
            },
            "timeline_eventi": list(timeline_dict.values()),
            "anagrafica_personaggi": list(pers_dict.values()),
            "capitoli_completati": capitoli_list
        }
        
        bio = io.BytesIO(json.dumps(master_json, indent=2, ensure_ascii=False).encode('utf-8'))
        return send_file(bio, as_attachment=True, download_name="prima-vivi-poi-spieghi_MASTER_EXPORT.json", mimetype="application/json")
        
    return "Invalid mode", 400

@app.route("/export/all/meta")
@login_required
def export_all_meta():
    caps = get_all()
    bio = io.BytesIO(json.dumps(caps, indent=2, ensure_ascii=False).encode('utf-8'))
    return send_file(bio, as_attachment=True, download_name="prima-vivi-poi-spieghi_metadati_completi.json", mimetype="application/json")

@app.route("/export/all/<mode>")
@login_required
def export_all_zip(mode):
    if mode not in ("txt", "full"): return "Invalid mode", 400
    caps = get_all()
    mem_zip = io.BytesIO()
    with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for c in caps:
            testo = read_txt(c['id'])
            fname = f"cap{c['id']:02d}_{c['titolo'].replace(' ', '_')}.txt"
            if mode == "txt":
                content = testo
            else:
                content = cap_to_meta_text(c, testo)
            zf.writestr(fname, content.encode('utf-8'))
            
    mem_zip.seek(0)
    suffix = "testi_puri" if mode == "txt" else "testi_e_metadati"
    return send_file(mem_zip, as_attachment=True, download_name=f"prima-vivi-poi-spieghi_{suffix}.zip", mimetype="application/zip")

@app.route("/cap/<int:cap_id>/publish/wordpress", methods=["POST"])
@login_required
def oh_my_book_wp_publish(cap_id):
    cap = get_cap(cap_id)
    if not cap: return "Capitolo non trovato", 404
    testo = read_txt(cap_id)
    
    # Dati dal Form
    wp_url = request.form.get('wp_url', '').rstrip('/')
    wp_user = request.form.get('wp_user', '')
    wp_pass = request.form.get('wp_app_pass', '')
    save_settings = request.form.get('save_settings') == 'on'
    
    wp_cat_name = request.form.get('wp_category', '').strip()
    wp_tags_str = request.form.get('wp_tags', '').strip()
    wp_excerpt = request.form.get('wp_excerpt', '').strip()
    
    seo_plugin = request.form.get('seo_plugin', 'rankmath')
    seo_title = request.form.get('seo_title', '').strip()
    seo_desc = request.form.get('seo_description', '').strip()
    
    # Salvataggio settings se richiesto
    if save_settings:
        save_wp_settings({
            "wp_url": wp_url,
            "wp_user": wp_user,
            "wp_app_pass": wp_pass,
            "seo_plugin": seo_plugin
        })
        
    # Preparazione Auth
    token = base64.b64encode(f"{wp_user}:{wp_pass}".encode('utf-8')).decode('utf-8')
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json"
    }
    
    try:
        # 1. Gestione Categoria (ID)
        cat_ids = []
        if wp_cat_name:
            r_cat = requests.get(f"{wp_url}/wp-json/wp/v2/categories", params={"search": wp_cat_name}, headers=headers)
            r_cat_data = r_cat.json()
            found_cat = next((c for c in r_cat_data if c['name'].lower() == wp_cat_name.lower()), None)
            if found_cat:
                cat_ids.append(found_cat['id'])
            else:
                r_create = requests.post(f"{wp_url}/wp-json/wp/v2/categories", json={"name": wp_cat_name}, headers=headers)
                if r_create.status_code == 201:
                    cat_ids.append(r_create.json()['id'])
                    
        # 2. Gestione Tags (ID)
        tag_ids = []
        if wp_tags_str:
            tag_names = [t.strip() for t in wp_tags_str.split(',') if t.strip()]
            for tname in tag_names:
                r_tag = requests.get(f"{wp_url}/wp-json/wp/v2/tags", params={"search": tname}, headers=headers)
                r_tag_data = r_tag.json()
                found_tag = next((t for t in r_tag_data if t['name'].lower() == tname.lower()), None)
                if found_tag:
                    tag_ids.append(found_tag['id'])
                else:
                    r_create = requests.post(f"{wp_url}/wp-json/wp/v2/tags", json={"name": tname}, headers=headers)
                    if r_create.status_code == 201:
                        tag_ids.append(r_create.json()['id'])
                        
        # 3. Preparazione Meta SEO
        meta = {}
        if seo_plugin == 'rankmath':
            meta["rank_math_title"] = seo_title
            meta["rank_math_description"] = seo_desc
            meta["rank_math_focus_keyword"] = seo_title
        else: # Yoast
            meta["_yoast_wpseo_title"] = seo_title
            meta["_yoast_wpseo_metadesc"] = seo_desc
            meta["_yoast_wpseo_focuskw"] = seo_title
            
        # 4. Creazione Post
        post_data = {
            "title": cap['titolo'],
            "content": testo.replace('\n', '<br>'), # Semplice conversione newline
            "excerpt": wp_excerpt,
            "status": "draft", # Sempre inviato come bozza per sicurezza
            "categories": cat_ids,
            "tags": tag_ids,
            "meta": meta
        }
        
        r_post = requests.post(f"{wp_url}/wp-json/wp/v2/posts", json=post_data, headers=headers)
        if r_post.status_code == 201:
            post_link = r_post.json().get('link', '#')
            return f"""
            <div style="background:#1a2e1a; color:#6fcf6f; padding:20px; border-radius:8px; font-family:sans-serif; text-align:center">
                <h2>✅ Capitolo Inviato a WordPress!</h2>
                <p>Il post è stato creato con successo come <b>Bozza</b>.</p>
                <div style="margin-top:20px">
                    <a href="{post_link}" target="_blank" style="background:#6fcf6f; color:#1a2e1a; padding:10px 20px; text-decoration:none; border-radius:4px; font-weight:bold">Apri Anteprima WP</a>
                    <a href="/cap/{cap_id}" style="color:#6fcf6f; margin-left:20px">Torna al Capitolo</a>
                </div>
            </div>
            """
        else:
            return f"Errore WordPress ({r_post.status_code}): {r_post.text}", 400
            
    except Exception as e:
        return f"Errore di connessione: {str(e)}", 500
def oh_my_book_api():
    # 1. Verifica Autenticazione HEADER
    auth_mode = get_env_var('API_AUTH_MODE', 'bearer')
    api_token = get_env_var('API_TOKEN', '123456789')
    
    if auth_mode == 'bearer':
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer ') or auth_header.split(' ')[1] != api_token:
            return jsonify({"status": "error", "message": "Unauthorized: Invalid Bearer Token"}), 401
    else:
        custom_key = get_env_var('API_CUSTOM_HEADER_KEY', 'x-api-key')
        header_val = request.headers.get(custom_key)
        if header_val != api_token:
            return jsonify({"status": "error", "message": f"Unauthorized: Invalid {custom_key}"}), 401

    # 2. Verifica Body JSON e USER_CODE
    try:
        req = request.get_json(force=True)
    except:
        return jsonify({"status": "error", "message": "Bad Request: requires JSON body"}), 400
        
    user_code = get_env_var('API_USER_CODE', 'admin99')
    if req.get('user_code') != user_code:
        return jsonify({"status": "error", "message": "Unauthorized: Invalid user_code"}), 401

    action = req.get('action')
    if not action:
        return jsonify({"status": "error", "message": "Missing 'action' field"}), 400

    # 3. Routing delle action
    try:
        conn = get_conn()
        
        if action == "search-capitolo":
            q = req.get('q', '').lower()
            rows = conn.execute("SELECT * FROM capitoli ORDER BY id").fetchall()
            caps = [dict(r) for r in rows]
            if q:
                caps = [c for c in caps if q in str(c.values()).lower()]
            return jsonify({"status": "success", "data": caps})
                
        elif action == "read-capitolo":
            c_id = req.get('id')
            if not c_id: return jsonify({"status":"error", "message":"Missing 'id'"}), 400
            row = conn.execute("SELECT * FROM capitoli WHERE id=?", (c_id,)).fetchone()
            if not row: return jsonify({"status":"error", "message":"Not found"}), 404
            cap = dict(row)
            cap['testo'] = read_txt(c_id)
            return jsonify({"status": "success", "data": cap})
            
        elif action == "update-capitolo":
            c_id = req.get('id')
            if not c_id: return jsonify({"status":"error", "message":"Missing 'id'"}), 400
            # update testo se presente
            if 'testo' in req:
                w_count = write_txt(c_id, req['testo'])
                conn.execute("UPDATE capitoli SET parole_file=? WHERE id=?", (w_count, c_id))
            
            # update metadati
            campi_db = [f[0] for f in CAMPI_META]
            updates = {}
            for k in campi_db:
                if k in req:
                    val = req[k]
                    if isinstance(val, list):
                        val = "\n".join(str(v) for v in val)
                    updates[k] = val
            if updates:
                set_c = ", ".join(f"{k}=?" for k in updates)
                vals = list(updates.values()) + [c_id]
                conn.execute(f"UPDATE capitoli SET {set_c} WHERE id=?", vals)
            conn.commit()
            return jsonify({"status": "success", "message": f"Capitolo {c_id} aggiornato"})
            
        elif action == "add-capitolo":
            c_id = req.get('id')
            if not c_id:
                row = conn.execute("SELECT MAX(id) as max_id FROM capitoli").fetchone()
                c_id = (row['max_id'] or 0) + 1
                
            campi_db = [f[0] for f in CAMPI_META]
            inserts = {k: req.get(k) for k in campi_db if k in req}
            if 'titolo' not in inserts: inserts['titolo'] = f"Capitolo {c_id}"
            if 'stato' not in inserts: inserts['stato'] = "bozza"
            
            cols = ["id"] + list(inserts.keys())
            places = ["?"] * len(cols)
            vals = [c_id] + list(inserts.values())
            
            conn.execute(f"INSERT OR REPLACE INTO capitoli ({','.join(cols)}) VALUES ({','.join(places)})", vals)
            if 'testo' in req:
                words = write_txt(c_id, req['testo'])
                conn.execute("UPDATE capitoli SET parole_file=? WHERE id=?", (words, c_id))
            else:
                write_txt(c_id, "") # crea vuoto
            conn.commit()
            return jsonify({"status": "success", "message": "Capitolo aggiunto/sostituito", "id": c_id})
            
        elif action == "delete-capitolo":
            c_id = req.get('id')
            if not c_id: return jsonify({"status":"error", "message":"Missing 'id'"}), 400
            conn.execute("DELETE FROM capitoli WHERE id=?", (c_id,))
            conn.commit()
            # delete file se esiste
            path = os.path.join(CAPITOLI_DIR, f"cap{c_id:02d}.txt")
            if os.path.exists(path): os.remove(path)
            return jsonify({"status": "success", "message": f"Capitolo {c_id} eliminato"})
            
        elif action == "modify-book-title":
            n_titolo = req.get('project_title')
            if not n_titolo: return jsonify({"status":"error", "message":"Missing 'project_title'"}), 400
            set_env_var("PROJECT_TITLE", n_titolo)
            return jsonify({"status": "success", "message": "Title updated"})
            
        else:
            return jsonify({"status": "error", "message": "Unknown action"}), 400
    
    except Exception as e:
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500
    finally:
        conn.close()

@app.route("/api-book/ai/execute", methods=["POST"])
def api_ai_dispatcher():
    # 1. Verifica Autenticazione HEADER (Condividerà la stessa logica)
    auth_mode = get_env_var('API_AUTH_MODE', 'bearer')
    api_token = get_env_var('API_TOKEN', '123456789')
    
    if auth_mode == 'bearer':
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer ') or auth_header.split(' ')[1] != api_token:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
    else:
        custom_key = get_env_var('API_CUSTOM_HEADER_KEY', 'x-api-key')
        header_val = request.headers.get(custom_key)
        if header_val != api_token:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401

    # 2. Verifica Body JSON
    try:
        req = request.get_json(force=True)
    except:
        return jsonify({"status": "error", "message": "Bad Request: requires JSON body"}), 400
        
    user_code = get_env_var('API_USER_CODE', 'admin99')
    if req.get('user_code') != user_code:
        return jsonify({"status": "error", "message": "Unauthorized: Invalid user_code"}), 401

    action = req.get('action')
    if not action:
        return jsonify({"status": "error", "message": "Missing 'action' field"}), 400

    # 3. Routing delle action AI
    try:
        # Recupero Parametri Comuni
        target_ids = req.get("target_ids", [])
        model_provider = req.get("model_provider", "")
        extra_prompt = req.get("extra_prompt", "").strip()
        
        provider = "openai"
        model = req.get("model")
        
        if "|" in model_provider:
            provider, model = model_provider.split("|")
        elif model_provider:
            provider = model_provider
            
        if not model:
            if provider == "openai": model = os.getenv("OPENAI_MODEL", "gpt-5")
            elif provider == "anthropic": model = os.getenv("CLAUDE_MODEL", "claude-3-7-sonnet-20250219")
            elif provider in ("google", "gemini"): 
                provider = "google"
                model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
            else: model = "gpt-5"
        
        if action == "generate-metadata":
            if not target_ids:
                return jsonify({"status": "error", "message": "Nessun target_ids fornito per generate-metadata"}), 400
                
            prompts = load_prompts()
            gen_prompt_tpl = prompts.get("metadata_generator_prompt", "")
            sys_instr = prompts.get("system_instruction", "")
            
            p_title = get_project_title()
            p_subtitle = os.getenv("PROJECT_SUBTITLE", "")
            p_timeline = os.getenv("PROJECT_TIMELINE", "")
            
            api_key = os.getenv(f"{provider.upper()}_API_KEY", "")
            
            if provider == "anthropic": api_key = os.getenv("CLAUDE_API_KEY", "")
                
            conn = get_conn()
            campi_db = [f[0] for f in CAMPI_META]
            linee_str = ", ".join(LINEE)
            
            count = 0
            for tid in target_ids:
                logger.info(f"[API Execute] Metadati per cap {tid} con {provider}...")
                prev_riassunto = ""
                if tid > 1:
                    prev = conn.execute("SELECT riassunto FROM capitoli WHERE id=?", (tid-1,)).fetchone()
                    if prev and prev['riassunto']: prev_riassunto = prev['riassunto']
                
                p_canon = get_full_canon()
                awareness_prefix = f"### STAGE: ARCHITETTURA METADATI E COERENZA\n### PROGRESSO OPERA: Capitolo {tid} di 66\n### OBIETTIVO: Generare i binari strutturali del capitolo garantendo il rispetto del CANONE DEFINITIVO.\n\n"
                prompt = awareness_prefix + gen_prompt_tpl.replace("{{p_title}}", p_title).replace("{{p_subtitle}}", p_subtitle).replace("{{timeline}}", p_timeline).replace("{{cap_id}}", str(tid)).replace("{{linee}}", linee_str).replace("{{full_canon}}", p_canon)
                if prev_riassunto: prompt += f"\n\nCONTESTO CAPITOLO PRECEDENTE:\n{prev_riassunto}"
                if extra_prompt: prompt += f"\n\nISTRUZIONI ADDIZIONALI UTENTE:\n{extra_prompt}"
                
                try:
                    from llm_client import generate_chapter_text
                    response_text = generate_chapter_text(prompt, provider, model, api_key, system=sys_instr)
                    if "```json" in response_text: response_text = response_text.split("```json")[1].split("```")[0].strip()
                    elif "```" in response_text: response_text = response_text.split("```")[1].split("```")[0].strip()
                    
                    meta_data = json.loads(response_text)
                    updates = {k: ("\n".join(str(v) for v in meta_data[k]) if isinstance(meta_data[k], list) else meta_data[k]) for k in campi_db if k in meta_data}
                    
                    if updates:
                        set_clause = ", ".join(f"{k}=?" for k in updates.keys())
                        vals = list(updates.values()) + [tid]
                        conn.execute(f"UPDATE capitoli SET {set_clause} WHERE id=?", vals)
                        conn.commit()
                        count += 1
                except Exception as e:
                    logger.error(f"[API Execute] Errore metadati cap {tid}: {e}")
                    continue
            conn.close()
            return jsonify({"status": "success", "message": f"Metadati generati per {count} capitoli."})
            
        elif action == "generate-narrative":
            if not target_ids:
                return jsonify({"status": "error", "message": "Nessun target_ids fornito per generate-narrative"}), 400
                
            act = ai_queue.get_active_job()
            if act and act['status'] in ('queued', 'running'):
                return jsonify({"status": "error", "message": "Un processo di generazione narrativa è già in corso."}), 400
                
            target_ids.sort() # Forza sequenzialità
            job_id = ai_queue.enqueue_generation(target_ids, provider, model, extra_prompt=extra_prompt)
            return jsonify({"status": "success", "job_id": job_id, "message": f"Generazione avviata per {len(target_ids)} capitoli."})
            
        elif action == "get-ai-status":
            act = ai_queue.get_active_job()
            if act: return jsonify({"status": "success", "data": act})
            else: return jsonify({"status": "success", "data": {"status": "idle"}})
            
        else:
            return jsonify({"status": "error", "message": f"Unknown action: {action}"}), 400

    except Exception as e:
        logger.error(f"[API Execute] Errore globale: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500


# ---------------------------------------------------------
# START AI INTEGRATION LOGIC (MULTI-STEP DYNAMIC)
# ---------------------------------------------------------

def process_ai_generation(cap_id, provider, model, update_status_func, extra_prompt="", use_chat=None):
    """
    Orchestrazione avanzata (Tentativo #19: Causal Anchor & Loop Detection).
    Previene la ripetizione della 'sveglia' e dei beat iniziali tramite cronologia fatti.
    """
    import llm_client
    import sqlite3
    import re
    import json
    
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cap_row = conn.execute("SELECT * FROM capitoli WHERE id=?", (cap_id,)).fetchone()
    if not cap_row: return "Capitolo non trovato."
    cap = dict(cap_row)

    api_key = get_env_var(f"{provider.upper()}_API_KEY")
    all_prompts = json.load(open("prompts.json", "r", encoding="utf-8"))
    
    # --- 0. DEEP ANALYSIS (Universal Flight Manual) ---
    update_status_func(f"Cap {cap_id}: Deep Context (Multi-Message)...")
    context_history = run_deep_context_pipeline(cap_id, provider, model, api_key, admin_mode=True)
    
    # --- 1. ADAPTIVE SPLITTING ---
    update_status_func(f"Cap {cap_id}: Analisi e Suddivisione Adattiva...")
    splitter_prompt = all_prompts.get("chapter_splitter_prompt", "").format(
        cap_id=cap_id, descrizione=cap['descrizione'], full_canon="Incorporato nella history."
    )
    
    # Append splitter prompt
    chat_split = context_history + [{"role": "user", "content": splitter_prompt}]
    resp_split = llm_client.generate_chapter_text("", provider, model, api_key, messages=chat_split, max_tokens=1500)
    parts_summaries = re.findall(r'<div[^>]*>(.*?)</div>', resp_split, re.DOTALL | re.IGNORECASE)
    if not parts_summaries:
        parts_summaries = [cap['descrizione'][:len(cap['descrizione'])//2], cap['descrizione'][len(cap['descrizione'])//2:]]
    
    testo_finale_accumulato = ""
    ultimo_testo_prosa = ""
    cronologia_fatti = [] # CAUSAL ANCHOR

    # --- 2. LOOP PARTI (ADAPTIVE PLANNING) ---
    for p_idx, p_summary in enumerate(parts_summaries):
        part_num = p_idx + 1
        update_status_func(f"Cap {cap_id}: Pianificazione Parte {part_num} di {len(parts_summaries)}...")
        
        continuità_msg = "Inizio capitolo." if not testo_finale_accumulato else "Continuità narrativa garantita."
        planner_prompt = all_prompts.get("scene_planner_html_prompt", "").format(
            cap_id=cap_id,
            parte_num=part_num,
            argomento_parte=p_summary,
            base_prompt=build_prompt(cap, None, None),
            num_scene=4,
            continuità_msg=continuità_msg
        )
        
        resp_plan = llm_client.generate_chapter_text("", provider, model, api_key, messages=[{"role": "user", "content": planner_prompt}], max_tokens=1500)
        scene_divs = re.findall(r'<div[^>]*>(.*?)</div>', resp_plan, re.DOTALL | re.IGNORECASE)
        
        part_steps = []
        for s_div in scene_divs:
            t_m = re.search(r'<h3>(.*?)</h3>', s_div, re.DOTALL | re.IGNORECASE)
            d_m = re.search(r'<em>(.*?)</em>', s_div, re.DOTALL | re.IGNORECASE)
            if t_m and d_m: part_steps.append({"titolo": t_m.group(1).strip(), "desc": d_m.group(1).strip()})
        
        if not part_steps: part_steps = [{"titolo": f"Scena {part_num}", "desc": p_summary}]

        # --- 3. DRAFTER LOOP CON ELASTIC RETRY & LOOP DETECTION ---
        for s_idx, step in enumerate(part_steps):
            scene_num = s_idx + 1
            update_status_func(f"Cap {cap_id} [P{part_num} S{scene_num}]: Scrittura...")
            
            testo_scena_finale = ""
            for attempt in range(1, 4):
                try:
                    tpl_key = "drafter_prompt" if attempt == 1 else "drafter_hardened_retry_prompt"
                    d_prompt = all_prompts.get(tpl_key, "").replace("[[POV]]", cap['pov'])
                    d_prompt = d_prompt.replace("[[FULL_CANON]]", "Incorporato nella history.")
                    d_prompt = d_prompt.replace("[[CAPITOLO_DESC]]", cap['riassunto'])
                    d_prompt = d_prompt.replace("[[STEP_TITOLO]]", step['titolo'])
                    d_prompt = d_prompt.replace("[[STEP_DESCRIZIONE]]", step['desc'])
                    d_prompt = d_prompt.replace("[[STEP_MOOD]]", "Crudo, Sensoriale")
                    d_prompt = d_prompt.replace("[[STEP_SENSORIALE]]", "Odori, Suoni, Tatto")

                    # INSERIMENTO CAUSAL ANCHOR
                    if cronologia_fatti:
                        history_str = "\n".join([f"- {f}" for f in cronologia_fatti[-5:]])
                        d_prompt += f"\n\n[[CRONOLOGIA_FATTI_AVVENUTI]]:\n{history_str}"
                        d_prompt = d_prompt + "\n\nATTENZIONE: NON ripetere le scene descritte sopra. Avanza nel tempo."

                    if ultimo_testo_prosa:
                        snippet_clean = ultimo_testo_prosa[-500:].replace('\n', ' ')
                        d_prompt = d_prompt + f"\n\n[[CONTINUITÀ_ULTIME_PAROLE]]: ...{snippet_clean}"

                    # Chiamata con contesto multi-messaggio + prompt specifico
                    chat_draft = context_history + [{"role": "user", "content": d_prompt}]
                    resp_draft = llm_client.generate_chapter_text("", provider, model, api_key, messages=chat_draft, max_tokens=2500)
                    draft_clean = llm_client.extract_narrative(resp_draft)
                    
                    # --- LOOP DETECTION (Tentativo #19) ---
                    bad_starters = ["mi sveglio", "il mattino", "il sole era", "la casa era fredda", "alba"]
                    is_loop = any(draft_clean.lower().startswith(b) for b in bad_starters) and len(cronologia_fatti) > 0
                    
                    if len(draft_clean) > 200 and not is_loop:
                        testo_scena_finale = draft_clean
                        cronologia_fatti.append(step['titolo']) # Mark as done
                        break
                    else:
                        reason = "LOOP DETECTED" if is_loop else "TOO SHORT"
                        print(f"WARNING: Scena {step['titolo']} scartata ({reason}) (Attempt {attempt}).")
                        update_status_func(f"Loop Detection attiva: riprovo scena {scene_num}...")
                except Exception as e:
                    print(f"Errore Draft: {e}")

            # REVISIONE
            if testo_scena_finale:
                update_status_func(f"Cap {cap_id} [P{part_num} S{scene_num}]: Revisione...")
                rev_prompt = all_prompts.get("step_reviewer_prompt", "").format(
                    prev_context=ultimo_testo_prosa[-1000:], draft_testo=testo_scena_finale, pov=cap['pov'],
                    extra_hook_instruction=f"CHIUDI CON HOOK: {cap['hook_finale']}" if (p_idx == len(parts_summaries)-1 and s_idx == len(part_steps)-1) else ""
                )
                resp_rev = llm_client.generate_chapter_text("", provider, model, api_key, messages=[{"role": "user", "content": rev_prompt}], max_tokens=2500)
                testo_rev = llm_client.extract_narrative(resp_rev)
                if len(testo_rev) > 200: testo_scena_finale = testo_rev.strip()

            if not testo_scena_finale:
                testo_scena_finale = f"[Scena saltata per errore tecnico: {step['titolo']}]"

            testo_finale_accumulato += f"\n\n{testo_scena_finale}"
            ultimo_testo_prosa = testo_scena_finale

    # --- SALVATAGGIO FINALE ---
    testo_finale_accumulato = testo_finale_accumulato.strip()
    parole = write_txt(cap_id, testo_finale_accumulato)
    conn.execute("UPDATE capitoli SET parole_file=? WHERE id=?", (parole, cap_id))
    conn.commit()
    conn.close()
    
    return testo_finale_accumulato


# Registra la funzione di processamento nella coda
ai_queue.set_job_callback(process_ai_generation)

@app.route("/generazione")
@login_required
def generazione_dashboard():
    all_caps = get_all()
    all_caps_html = get_sidebar_html(active_id=None, is_admin=True)
    
    body = f"""
    <div class="topbar">
      <h1>🧠 Generazione Narrativa AI (Flusso Loop & Retry)</h1>
      <div class="actions">
        <a href="/admin" class="btn">← Dashboard</a>
      </div>
    </div>
    <div class="content">
      <div class="card" style="border-color:var(--accent)">
        <h2 style="color:var(--accent)">Pannello Generazione Narrativa Avanzato</h2>
        <p style="color:var(--muted); font-size:12px; margin-bottom:20px">
          Seleziona i capitoli da generare (o rigenerare). La pipeline utilizzerà l'architettura <b>Audit #20</b>.
        </p>
        
        <div style="display:flex; gap:20px; flex-wrap:wrap">
            <!-- Colonna Sinistra: Selezione Capitoli -->
            <div style="flex:1; min-width:300px">
                <div class="field">
                    <label>Seleziona Capitoli</label>
                    <div style="background:#111; border:1px solid #333; border-radius:6px; max-height:400px; overflow-y:auto; padding:10px">
                        {"".join(f'''
                        <label style="display:flex; align-items:center; gap:10px; padding:6px; cursor:pointer; border-bottom:1px solid #222" class="cap-row">
                            <input type="checkbox" name="target_cap" value="{c['id']}" style="width:18px; height:18px">
                            <span style="font-family:monospace; color:var(--accent)">{c['id']:02d}</span>
                            <span style="font-size:13px">{c['titolo']}</span>
                        </label>
                        ''' for c in all_caps)}
                    </div>
                </div>
            </div>

            <!-- Colonna Destra: Parametri e Status -->
            <div style="flex:1.5; min-width:300px">
                <div class="field">
                    <label>Prompt di Personalizzazione (Opzionale)</label>
                    <textarea id="custom_base_prompt" placeholder="Aggiungi istruzioni extra... (es. 'Aggiungi più dialoghi', 'Stile più cupo')" style="height:80px"></textarea>
                </div>

                <div class="field">
                    <label>Modello AI</label>
                    <select id="gen_model_selector" class="btn" style="background:#1a1a1a; width:100%">
                         <optgroup label="Local (LM Studio)">
                             <option value="lmstudio|{get_env_var('ADMIN_CHAT_MODEL', 'custom')}">LM Studio (Locale)</option>
                         </optgroup>
                         <optgroup label="Cloud Providers">
                             {''.join(f'<option value="openai|{m[0]}">{m[1]}</option>' for m in MODELS_CONFIG['openai'])}
                             {''.join(f'<option value="anthropic|{m[0]}">{m[1]}</option>' for m in MODELS_CONFIG['anthropic'])}
                         </optgroup>
                    </select>
                </div>

                <div style="background:#111; padding:15px; border-radius:8px; border:1px solid #333; margin-bottom:20px">
                    <div id="ai-status-text" style="font-family:monospace; font-size:13px; color:#aaa; margin-bottom:10px">Stato: Pronto.</div>
                    <div id="progress-container" style="width:100%; height:12px; background:#222; border-radius:6px; overflow:hidden; display:none">
                        <div id="progress-bar" style="width:0%; height:100%; background:linear-gradient(90deg, #c9a96e, #a888ca); transition: width 0.5s"></div>
                    </div>
                    <div id="progress-pct" style="font-size:10px; color:var(--muted); margin-top:5px; text-align:right; display:none">0%</div>
                </div>

                <div style="display:flex; gap:10px">
                    <button onclick="startMultiGen()" class="btn btn-primary" style="flex:1; padding:12px">🚀 AVVIA GENERAZIONE SELEZIONATI</button>
                </div>
            </div>
        </div>
      </div>
    </div>

    <script>
    function startMultiGen() {{
        const selected = Array.from(document.querySelectorAll('input[name="target_cap"]:checked')).map(cb => parseInt(cb.value));
        if(selected.length === 0) {{
            alert("Seleziona almeno un capitolo.");
            return;
        }}
        
        if(!confirm(`Confermi la generazione di ${{selected.length}} capitoli? Il testo esistente verrà sovrascritto.`)) return;
        
        document.getElementById('progress-container').style.display = 'block';
        document.getElementById('progress-pct').style.display = 'block';
        document.getElementById('ai-status-text').textContent = "Avvio processo...";
        
        const customPrompt = document.getElementById('custom_base_prompt').value;
        const model = document.getElementById('gen_model_selector').value;

        fetch('/api-book/ai/execute', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json', 'Authorization': 'Bearer {get_env_var("API_TOKEN", "123456789")}' }},
            body: JSON.stringify({{
                user_code: '{get_env_var("API_USER_CODE", "admin99")}',
                action: 'generate-narrative',
                target_ids: selected,
                base_prompt: customPrompt,
                model_provider: model
            }})
        }})
        .then(r => r.json())
        .then(data => {{
            if(data.status === 'success') {{
                pollStatus();
            }} else {{
                alert("Errore: " + data.message);
            }}
        }});
    }}

    let isPolling = false;
    function pollStatus() {{
        if(isPolling) return;
        isPolling = true;
        
        fetch('/api-book/ai/execute', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json', 'Authorization': 'Bearer {get_env_var("API_TOKEN", "123456789")}' }},
            body: JSON.stringify({{
                user_code: '{get_env_var("API_USER_CODE", "admin99")}',
                action: 'get-ai-status'
            }})
        }})
        .then(r => r.json())
        .then(res => {{
            isPolling = false;
            const d = res.data;
            if(d.status === 'idle') {{
                document.getElementById('progress-container').style.display = 'none';
                document.getElementById('progress-pct').style.display = 'none';
            }} else {{
                document.getElementById('progress-container').style.display = 'block';
                document.getElementById('progress-pct').style.display = 'block';
                document.getElementById('ai-status-text').style.color = '#fff';
                document.getElementById('ai-status-text').textContent = d.message || "Interrogazione modello...";
                
                document.getElementById('progress-bar').style.width = d.progress + '%';
                document.getElementById('progress-pct').textContent = d.progress + '%';
                
                if(d.status !== 'completed' && d.status !== 'error') {{
                    setTimeout(pollStatus, 2000);
                }} else if(d.status === 'error') {{
                    document.getElementById('progress-bar').style.background = '#c0392b';
                    document.getElementById('ai-status-text').style.color = '#e74c3c';
                }} else if(d.status === 'completed') {{
                    document.getElementById('progress-bar').style.width = '100%';
                    document.getElementById('progress-pct').textContent = '100% FATTO!';
                }}
            }}
        }}).catch(() => {{ isPolling = false; }});
    }}
    // Start interval trigger for tracking when we reload the page
    pollStatus();
    </script>
    """
    
    return render_template_string(ADMIN_LAYOUT, title="AI Generation", content=body, all_caps_html=all_caps_html, BASE_CSS=BASE_CSS, project_title=get_project_title())


# ═══════════════════════════════════════════════════════════
# SISTEMA PERSONAGGI - Helper + Routes
# ═══════════════════════════════════════════════════════════

def get_personaggi():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM personaggi ORDER BY ordine, nome").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_personaggio(pid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM personaggi WHERE id=?", (pid,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_personaggio_capitolo(pid, cid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM personaggi_capitoli WHERE personaggio_id=? AND capitolo_id=?", (pid, cid)).fetchone()
    conn.close()
    return dict(row) if row else {}

def get_all_personaggi_for_cap(cid):
    """Restituisce tutti i personaggi con i loro dati per un dato capitolo."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT p.id, p.nome, p.colore, p.ruolo,
               pc.presente, pc.luogo, pc.stato_emotivo, pc.obiettivo,
               pc.azione_parallela, pc.sviluppo, pc.note
        FROM personaggi p
        LEFT JOIN personaggi_capitoli pc ON pc.personaggio_id=p.id AND pc.capitolo_id=?
        WHERE p.attivo=1
        ORDER BY p.ordine, p.nome
    """, (cid,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def ensure_personaggi_capitoli(pid):
    """Assicura che esistano entry per tutti i capitoli per un personaggio."""
    conn = get_conn()
    caps = conn.execute("SELECT id FROM capitoli").fetchall()
    for cap in caps:
        conn.execute(
            "INSERT OR IGNORE INTO personaggi_capitoli (personaggio_id, capitolo_id) VALUES (?,?)",
            (pid, cap[0])
        )
    conn.commit()
    conn.close()

def get_personaggi_sidebar_html(active_id=None):
    """Genera HTML sidebar per la pagina Personaggi."""
    personaggi = get_personaggi()
    html = ""
    for p in personaggi:
        active = "active" if p['id'] == active_id else ""
        color = p.get('colore') or '#888'
        html += f"""<a href="/personaggio/{p['id']}" class="cap-link {active}">
      <span class="pov-dot" style="background:{color}"></span>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{p['nome']}</span>
      <span style="font-size:10px;color:var(--muted)">{p.get('ruolo','')[:20]}</span>
    </a>"""
    html += """<a href="/personaggi/nuovo" class="cap-link" style="color:#6fcf6f;border-top:1px solid var(--border);margin-top:4px">
      <span>＋ Nuovo Personaggio</span>
    </a>"""
    return html

# ─── PAGINA LISTA PERSONAGGI ───────────────────────────
@app.route("/personaggi")
@login_required
def page_personaggi():
    personaggi = get_personaggi()

    cards_html = ""
    for p in personaggi:
        color = p.get('colore') or '#888'
        cards_html += f"""
        <a href="/personaggio/{p['id']}" class="cap-card" style="border-left:4px solid {color};text-decoration:none">
            <div class="num">#{p['id']:02d} · {p.get('nazionalita','')}</div>
            <div class="titolo">{p['nome']}</div>
            <div class="meta">{p.get('ruolo','')}</div>
            <div class="words" style="color:{color}">{p.get('eta_iniziale','')} anni</div>
        </a>"""

    body = f"""
    <div class="topbar">
      <h1>👥 Personaggi</h1>
      <div class="actions">
        <a href="/personaggi/nuovo" class="btn btn-primary">＋ Nuovo Personaggio</a>
      </div>
    </div>
    <div class="content">
      <div class="home-grid">{cards_html}</div>
    </div>
    """

    sidebar_html = get_personaggi_sidebar_html()
    # Sovrascriviamo la sidebar col rendering personaggi
    all_caps_html = f"""
    <div style="display:flex;border-bottom:1px solid var(--border)">
      <a href="/admin" style="flex:1;text-align:center;padding:8px 0;font-size:11px;color:var(--muted);border-bottom:2px solid transparent;text-decoration:none">📖 Capitoli</a>
      <span style="flex:1;text-align:center;padding:8px 0;font-size:11px;color:var(--accent);border-bottom:2px solid var(--accent)">👥 Personaggi</span>
    </div>
    {sidebar_html}"""

    return render_template_string(ADMIN_LAYOUT, title="Personaggi",
        content=body, all_caps_html=all_caps_html,
        BASE_CSS=BASE_CSS, project_title=get_project_title())

# ─── FORM NUOVO PERSONAGGIO ────────────────────────────
@app.route("/personaggi/nuovo", methods=["GET","POST"])
@login_required
def page_personaggio_nuovo():
    if request.method == "POST":
        nome = request.form.get("nome","").strip()
        if not nome:
            return redirect(url_for("page_personaggi"))
        conn = get_conn()
        cur = conn.execute("""
            INSERT INTO personaggi (nome, colore, eta_iniziale, nazionalita, ruolo,
                background, tratti_fisici, tratti_psicologici, relazioni,
                arco_narrativo, note, attivo, ordine)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,1,
                (SELECT COALESCE(MAX(ordine),0)+1 FROM personaggi))
        """, (nome,
              request.form.get("colore","#c9a96e"),
              request.form.get("eta_iniziale",""),
              request.form.get("nazionalita",""),
              request.form.get("ruolo",""),
              request.form.get("background",""),
              request.form.get("tratti_fisici",""),
              request.form.get("tratti_psicologici",""),
              request.form.get("relazioni",""),
              request.form.get("arco_narrativo",""),
              request.form.get("note",""),
        ))
        new_id = cur.lastrowid
        conn.commit()
        conn.close()
        ensure_personaggi_capitoli(new_id)
        return redirect(url_for("page_personaggio", pid=new_id))

    form_html = """
    <div class="topbar"><h1>Nuovo Personaggio</h1>
      <div class="actions"><a href="/personaggi" class="btn">← Lista</a></div>
    </div>
    <div class="content"><form method="POST" class="card" style="max-width:800px">
    """ + _personaggio_form_fields({}) + """
      <button type="submit" class="btn btn-primary" style="width:100%">Crea Personaggio</button>
    </form></div>"""

    sidebar_html = get_personaggi_sidebar_html()
    all_caps_html = _personaggi_sidebar_wrapper(sidebar_html)
    return render_template_string(ADMIN_LAYOUT, title="Nuovo Personaggio",
        content=form_html, all_caps_html=all_caps_html,
        BASE_CSS=BASE_CSS, project_title=get_project_title())

# ─── SCHEDA SINGOLO PERSONAGGIO ────────────────────────
@app.route("/personaggio/<int:pid>", methods=["GET","POST"])
@login_required
def page_personaggio(pid):
    p = get_personaggio(pid)
    if not p:
        return redirect(url_for("page_personaggi"))

    msg = None
    if request.method == "POST":
        action = request.form.get("action","save")
        if action == "delete":
            conn = get_conn()
            conn.execute("DELETE FROM personaggi_capitoli WHERE personaggio_id=?", (pid,))
            conn.execute("DELETE FROM personaggi WHERE id=?", (pid,))
            conn.commit()
            conn.close()
            return redirect(url_for("page_personaggi"))

        conn = get_conn()
        conn.execute("""
            UPDATE personaggi SET nome=?, colore=?, eta_iniziale=?, nazionalita=?, ruolo=?,
                background=?, tratti_fisici=?, tratti_psicologici=?, relazioni=?,
                arco_narrativo=?, note=?
            WHERE id=?
        """, (
            request.form.get("nome", p["nome"]),
            request.form.get("colore", p.get("colore","#888")),
            request.form.get("eta_iniziale",""),
            request.form.get("nazionalita",""),
            request.form.get("ruolo",""),
            request.form.get("background",""),
            request.form.get("tratti_fisici",""),
            request.form.get("tratti_psicologici",""),
            request.form.get("relazioni",""),
            request.form.get("arco_narrativo",""),
            request.form.get("note",""),
            pid
        ))
        conn.commit()
        conn.close()
        p = get_personaggio(pid)
        msg = "Salvato con successo."

    # Capitoli per questo personaggio
    conn = get_conn()
    caps_data = conn.execute("""
        SELECT c.id, c.titolo, c.pov, c.luogo, c.data_narrativa,
               pc.presente, pc.luogo as p_luogo, pc.stato_emotivo, pc.obiettivo,
               pc.azione_parallela, pc.sviluppo, pc.note as p_note, pc.id as pc_id
        FROM capitoli c
        LEFT JOIN personaggi_capitoli pc ON pc.capitolo_id=c.id AND pc.personaggio_id=?
        ORDER BY c.id
    """, (pid,)).fetchall()
    conn.close()

    caps_rows = ""
    for cap in caps_data:
        cd = dict(cap)
        presente_checked = "checked" if cd.get("presente") else ""
        row_bg = "rgba(201,169,110,0.07)" if cd.get("presente") else ""
        caps_rows += f"""
        <div class="card" style="margin-bottom:10px;background:{row_bg};border-left:3px solid {p.get('colore','#888')}">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">
            <b style="color:var(--accent);min-width:32px">Cap {cd['id']:02d}</b>
            <span style="font-weight:500">{cd['titolo']}</span>
            <span style="color:var(--muted);font-size:11px">{cd.get('pov','')} · {cd.get('data_narrativa','')}</span>
            <label style="margin-left:auto;display:flex;align-items:center;gap:6px;cursor:pointer;font-size:12px">
              <input type="checkbox" {presente_checked} onchange="saveCapPersonaggio({pid},{cd['id']},this)" style="accent-color:var(--accent)">
              Presente
            </label>
          </div>
          <div id="pc-fields-{cd['id']}" style="display:{'grid' if cd.get('presente') else 'none'};grid-template-columns:1fr 1fr;gap:10px">
            <div class="field">
              <label>Luogo nel cap.</label>
              <input type="text" id="pc-luogo-{cd['id']}" value="{cd.get('p_luogo','') or ''}" onblur="saveCapPersonaggioField({pid},{cd['id']})" placeholder="Dove si trova...">
            </div>
            <div class="field">
              <label>Stato emotivo</label>
              <input type="text" id="pc-emotivo-{cd['id']}" value="{cd.get('stato_emotivo','') or ''}" onblur="saveCapPersonaggioField({pid},{cd['id']})" placeholder="Come si sente...">
            </div>
            <div class="field">
              <label>Obiettivo nel cap.</label>
              <input type="text" id="pc-obiettivo-{cd['id']}" value="{cd.get('obiettivo','') or ''}" onblur="saveCapPersonaggioField({pid},{cd['id']})" placeholder="Cosa vuole...">
            </div>
            <div class="field">
              <label>Azione parallela (se assente)</label>
              <input type="text" id="pc-parallela-{cd['id']}" value="{cd.get('azione_parallela','') or ''}" onblur="saveCapPersonaggioField({pid},{cd['id']})" placeholder="Cosa sta facendo altrove...">
            </div>
            <div class="field" style="grid-column:1/-1">
              <label>Sviluppo personaggio in questo cap.</label>
              <textarea id="pc-sviluppo-{cd['id']}" rows="2" onblur="saveCapPersonaggioField({pid},{cd['id']})" placeholder="Come cambia, cosa impara, cosa decide...">{cd.get('sviluppo','') or ''}</textarea>
            </div>
            <div class="field" style="grid-column:1/-1">
              <label>Note AI (contesto per la generazione)</label>
              <textarea id="pc-note-{cd['id']}" rows="2" onblur="saveCapPersonaggioField({pid},{cd['id']})" placeholder="Informazioni extra per coerenza AI...">{cd.get('p_note','') or ''}</textarea>
            </div>
          </div>
        </div>"""

    color = p.get('colore','#c9a96e')
    body = f"""
    <div class="topbar">
      <span class="pov-dot" style="background:{color};width:14px;height:14px;border-radius:50%;display:inline-block"></span>
      <h1 style="color:{color}">{p['nome']}</h1>
      <div class="actions">
        <a href="/personaggi" class="btn">← Lista</a>
        <button form="pform" class="btn btn-primary">💾 Salva</button>
        <button onclick="if(confirm('Eliminare {p['nome']}?')){{document.getElementById('del-form').submit()}}" class="btn btn-danger">🗑 Elimina</button>
      </div>
    </div>
    <div class="content">
      {f'<div class="msg ok">{msg}</div>' if msg else ''}
      <form id="pform" method="POST" style="margin-bottom:24px">
        <input type="hidden" name="action" value="save">
        <div class="card">
          <h2>Scheda Personaggio</h2>
          {_personaggio_form_fields(p)}
        </div>
      </form>
      <form id="del-form" method="POST">
        <input type="hidden" name="action" value="delete">
      </form>

      <div class="card">
        <h2>Timeline Capitoli</h2>
        <p style="color:var(--muted);font-size:12px;margin-bottom:16px">
          Spunta i capitoli in cui il personaggio è presente e compila i campi.
          Per i capitoli in cui è assente, indica cosa sta facendo in parallelo.
        </p>
        {caps_rows}
      </div>
    </div>

    <script>
    function saveCapPersonaggio(pid, cid, checkbox) {{
        const presente = checkbox.checked ? 1 : 0;
        const fields = document.getElementById('pc-fields-' + cid);
        fields.style.display = presente ? 'grid' : 'none';
        saveCapPersonaggioField(pid, cid, presente);
    }}

    function saveCapPersonaggioField(pid, cid, presenteOverride) {{
        const presente = (presenteOverride !== undefined) ? presenteOverride :
            (document.querySelector('#pc-fields-' + cid).style.display !== 'none' ? 1 : 0);
        const data = {{
            presente: presente,
            luogo: (document.getElementById('pc-luogo-' + cid) || {{}}).value || '',
            stato_emotivo: (document.getElementById('pc-emotivo-' + cid) || {{}}).value || '',
            obiettivo: (document.getElementById('pc-obiettivo-' + cid) || {{}}).value || '',
            azione_parallela: (document.getElementById('pc-parallela-' + cid) || {{}}).value || '',
            sviluppo: (document.getElementById('pc-sviluppo-' + cid) || {{}}).value || '',
            note: (document.getElementById('pc-note-' + cid) || {{}}).value || '',
        }};
        fetch('/api/personaggio/' + pid + '/capitolo/' + cid, {{
            method: 'POST',
            headers: {{'Content-Type':'application/json'}},
            body: JSON.stringify(data)
        }}).then(r => r.json()).then(d => {{
            if(!d.ok) console.warn('Save error', d);
        }});
    }}
    </script>
    """

    sidebar_html = get_personaggi_sidebar_html(active_id=pid)
    all_caps_html = _personaggi_sidebar_wrapper(sidebar_html)
    return render_template_string(ADMIN_LAYOUT, title=p['nome'],
        content=body, all_caps_html=all_caps_html,
        BASE_CSS=BASE_CSS, project_title=get_project_title())

# ─── API SAVE PER-CAP DATA ─────────────────────────────
@app.route("/api/personaggio/<int:pid>/capitolo/<int:cid>", methods=["POST"])
@login_required
def api_personaggio_capitolo_save(pid, cid):
    data = request.json or {}
    conn = get_conn()
    conn.execute("""
        INSERT INTO personaggi_capitoli (personaggio_id, capitolo_id, presente, luogo,
            stato_emotivo, obiettivo, azione_parallela, sviluppo, note)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(personaggio_id, capitolo_id) DO UPDATE SET
            presente=excluded.presente, luogo=excluded.luogo,
            stato_emotivo=excluded.stato_emotivo, obiettivo=excluded.obiettivo,
            azione_parallela=excluded.azione_parallela, sviluppo=excluded.sviluppo,
            note=excluded.note
    """, (pid, cid,
          1 if data.get("presente") else 0,
          data.get("luogo",""), data.get("stato_emotivo",""),
          data.get("obiettivo",""), data.get("azione_parallela",""),
          data.get("sviluppo",""), data.get("note","")
    ))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

# ─── API GET PERSONAGGI PER CAPITOLO ──────────────────
@app.route("/api/cap/<int:cap_id>/personaggi")
@login_required
def api_cap_personaggi(cap_id):
    data = get_all_personaggi_for_cap(cap_id)
    return jsonify(data)

# ─── HELPER: form fields HTML ─────────────────────────
def _personaggio_form_fields(p):
    def f(key, label, typ="text", placeholder=""):
        val = p.get(key, '') or ''
        if typ == "color":
            return f'<div class="field"><label>{label}</label><input type="color" name="{key}" value="{val or "#c9a96e"}"></div>'
        if typ == "textarea":
            return f'<div class="field"><label>{label}</label><textarea name="{key}" rows="3" placeholder="{placeholder}">{val}</textarea></div>'
        return f'<div class="field"><label>{label}</label><input type="text" name="{key}" value="{val}" placeholder="{placeholder}"></div>'

    return f"""
    <div class="grid2">
      {f('nome','Nome *', placeholder='Es: Lin, Neda...')}
      {f('colore','Colore POV','color')}
      {f('nazionalita','Nazionalità / Provenienza', placeholder='Es: Cinese, Iraniana...')}
      {f('eta_iniziale','Età (inizio storia)', placeholder='Es: 35, ~27...')}
    </div>
    {f('ruolo',"Ruolo nell'opera", placeholder='Es: Protagonista – Il mentore')}
    {f('background','Background / Storia personale','textarea',"Cosa ha vissuto prima dell'opera...")}
    {f('tratti_fisici','Tratti fisici distintivi','textarea','Cicatrice, corporatura, modo di muoversi...')}
    {f('tratti_psicologici','Psicologia e tratti caratteriali','textarea','Punti di forza, debolezze, paure...')}
    {f('relazioni','Relazioni con altri personaggi','textarea','Chi conosce e come...')}
    {f('arco_narrativo','Arco narrativo (trasformazione)','textarea','Da dove parte a dove arriva come personaggio...')}
    {f('note','Note libere','textarea','Qualsiasi informazione aggiuntiva...')}
    """

def _personaggi_sidebar_wrapper(inner_html):
    return f"""
    {inner_html}"""

# --- DASHBOARD TIMELINE ---
TIMELINE_LAYOUT = """
<div class="topbar">
  <h1>⏳ Timeline Temporale</h1>
  <div class="actions">
    <button onclick="openTimelineModal()" class="btn btn-primary">＋ Nuovo Evento</button>
  </div>
</div>
<div class="content">
  <div class="card" style="border-color:var(--accent)">
    <h2 style="color:var(--accent)">Eventi Cronologici</h2>
    <div class="home-grid">
      {% for e in events %}
      <div class="cap-card" style="border-left:4px solid var(--accent); position:relative">
        <div class="num">{{ e.arco_inizio }} — {{ e.arco_fine }}</div>
        <div class="titolo">{{ e.descrizione[:60] }}{{ '...' if e.descrizione|length > 60 else '' }}</div>
        <div class="meta"><b>Motivo:</b> {{ e.motivo[:40] }}...</div>
        <div style="margin-top:10px; display:flex; gap:8px">
          <button onclick='editEvent({{ e | tojson }})' class="btn" style="padding:2px 8px; font-size:11px">Edit</button>
          <a href="/timeline/delete/{{ e.id }}" onclick="return confirm('Sicuro?')" class="btn btn-danger" style="padding:2px 8px; font-size:11px">Elimina</a>
        </div>
      </div>
      {% endfor %}
    </div>
  </div>
</div>

<!-- Modal Evento -->
<div id="timeline-modal" class="full-text-overlay" style="display:none">
  <div class="full-text-modal" style="max-width:600px">
    <span class="close-overlay" onclick="closeTimelineModal()">&times;</span>
    <h2 id="modal-title" style="color:var(--accent); margin-bottom:20px">Evento Timeline</h2>
    <form action="/timeline/save" method="POST">
      <input type="hidden" name="id" id="event-id">
      <div class="grid2">
        <div class="field"><label>Arco Inizio (Giorno/Mese/Anno)</label><input type="text" name="arco_inizio" id="event-inizio" required></div>
        <div class="field"><label>Arco Fine (Giorno/Mese/Anno)</label><input type="text" name="arco_fine" id="event-fine" required></div>
      </div>
      <div class="field"><label>Descrizione Evento</label><textarea name="descrizione" id="event-desc" rows="3" required></textarea></div>
      <div class="field"><label>Motivo dell'Evento</label><textarea name="motivo" id="event-motivo" rows="2"></textarea></div>
      <div class="grid2">
        <div class="field"><label>Personaggi Coinvolti</label><input type="text" name="personaggi_coinvolti" id="event-coinvolti" placeholder="Lin, Neda..."></div>
        <div class="field"><label>Personaggi Esclusi</label><input type="text" name="personaggi_esclusi" id="event-esclusi" placeholder="Artem..."></div>
      </div>
      <div class="field"><label>Motivo Esclusione</label><textarea name="motivo_esclusione" id="event-motivo-escl" rows="2"></textarea></div>
      <button type="submit" class="btn btn-primary" style="width:100%; margin-top:10px">Salva Evento</button>
    </form>
  </div>
</div>

<script>
function openTimelineModal() {
    document.getElementById('timeline-modal').style.display = 'flex';
    document.getElementById('modal-title').textContent = 'Nuovo Evento';
    document.getElementById('event-id').value = '';
}
function closeTimelineModal() {
    document.getElementById('timeline-modal').style.display = 'none';
}
function editEvent(e) {
    openTimelineModal();
    document.getElementById('modal-title').textContent = 'Modifica Evento';
    document.getElementById('event-id').value = e.id;
    document.getElementById('event-inizio').value = e.arco_inizio;
    document.getElementById('event-fine').value = e.arco_fine;
    document.getElementById('event-desc').value = e.descrizione;
    document.getElementById('event-motivo').value = e.motivo;
    document.getElementById('event-coinvolti').value = e.personaggi_coinvolti;
    document.getElementById('event-esclusi').value = e.personaggi_esclusi;
    document.getElementById('event-motivo-escl').value = e.motivo_esclusione;
}
</script>
"""

@app.route('/timeline')
@login_required
def timeline_dashboard():
    events = get_timeline()
    personaggi = get_personaggi()
    all_caps_html = get_sidebar_html()
    return render_template_string(ADMIN_LAYOUT, title="Timeline", 
                                  content=render_template_string(TIMELINE_LAYOUT, events=events), 
                                  all_caps_html=all_caps_html, BASE_CSS=BASE_CSS, project_title=get_project_title())

@app.route('/timeline/save', methods=['POST'])
@login_required
def timeline_save():
    data = request.form.to_dict()
    save_timeline_event(data)
    return redirect(url_for('timeline_dashboard'))

@app.route('/timeline/delete/<int:id>')
@login_required
def timeline_delete(id):
    conn = get_conn()
    conn.execute("DELETE FROM timeline WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('timeline_dashboard'))

# --- API PROMPTS ---
@app.get('/api/prompts/<scopo>')
@login_required
def api_get_prompt(scopo):
    return jsonify({"scopo": scopo, "prompt": get_validation_prompt(scopo)})

@app.post('/api/prompts/save')
@login_required
def api_save_prompt():
    data = request.json
    update_validation_prompt(data['scopo'], data['prompt'])
    return jsonify({"status": "ok"})

@app.post('/api/ai-check')
@login_required
def api_ai_check():
    data = request.json
    cap_id = data.get('cap_id')
    testo_delta = data.get('testo', '')
    custom_prompt = data.get('custom_prompt', '')
    # scope = data.get('scope', 'coerenza_narrativa') # User prompt can be specific

    # Configurazione LLM (usiamo il predefinito)
    ui = load_ui_settings()
    provider = get_env_var("LLM_PROVIDER", "openai")
    model_name = ui.get("admin_chat_model", "claude-3-5-sonnet-20241022")
    if "|" in model_name: provider, model_name = model_name.split("|")
    api_key = get_env_var(f"{provider.upper()}_API_KEY")

    try:
        # 1. Recupero Contesto Deep
        messages = run_deep_context_pipeline(cap_id, provider, model_name, api_key, user_msg="VALIDAZIONE COERENZA")
        
        # 2. Aggiunta Delta Testo e Prompt di Validazione
        validation_instr = f"""
### OBIETTIVO: VALIDAZIONE E AUDIT COERENZA
Analizza il seguente testo (modificato o nuovo) del Capitolo {cap_id} applicando rigorosamente questo prompt di sistema:
---
{custom_prompt}
---

TESTO DA ANALIZZARE:
{testo_delta[:10000]} # Limitiamo per sicurezza

Fornisci un feedback puntuale, segnalando eventuali 'Red Flags' (incoerenze gravi) o suggerimenti di miglioramento stilistico.
"""
        messages.append({"role": "user", "content": validation_instr})
        
        from llm_client import generate_chapter_text
        feedback = generate_chapter_text("", provider, model_name, api_key, messages=messages, max_tokens=1500)
        
        return jsonify({"feedback": feedback})
    except Exception as e:
        logger.error(f"Errore AI Check: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=5000)
    embedding_provider = (data.get("embedding_provider") or get_env_var("VECTOR_EMBEDDING_PROVIDER", "hash_local")).strip() or "hash_local"
    embedding_model = (data.get("embedding_model") or get_env_var("VECTOR_EMBEDDING_MODEL", "")).strip()
    embedding_base_url = (data.get("embedding_base_url") or get_env_var("VECTOR_EMBEDDING_BASE_URL", "")).strip()
    embedding_api_key = (data.get("embedding_api_key") or get_env_var("VECTOR_EMBEDDING_API_KEY", "")).strip()
