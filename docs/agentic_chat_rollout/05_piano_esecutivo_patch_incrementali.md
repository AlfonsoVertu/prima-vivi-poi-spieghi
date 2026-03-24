# Piano tecnico esecutivo (patch incrementali) — Chat agentica

Obiettivo: passare dall'attuale foundation (registry + UI + endpoint tool separati) a una vera orchestrazione multi-agente runtime per chat **reader** e **author**, mantenendo compatibilità con l'architettura attuale.

## Stato di partenza (oggi)

- `/api/chat/<cap_id>` risolve dal registry un solo ruolo per modalità (`ReaderAnswerer` / `AnswerSynthesizer`).
- L'orchestratore streaming usa sub-agent prompt-based (`architetto/storico/lettore`) ma senza tool-calling automatico per ruolo registry.
- I tool sono disponibili via `/api/chat/tools*`, con permessi reader/admin, ma non ancora integrati in auto dentro il loop di risposta.

---

## Fase 1 — Runtime multi-role minimo (senza rompere API esistenti)

### Obiettivo
Attivare davvero 2 agenti per reader e 2 agenti per author nel percorso `/api/chat`, mantenendo fallback al comportamento attuale.

### Patch 1.1 — Resolver multi-ruolo da registry
**File:** `app.py`, `agent_registry.py`

1. Aggiungere in `app.py` una funzione `resolve_agents_for_mode(admin_mode)` che recupera più ruoli abilitati per modalità:
   - reader: `ReaderAnswerer`, `SpoilerJudge`
   - author: `AuthorTaskRouter`, `AnswerSynthesizer`
2. Usare `registry_resolve_agent_for_role(...)` per ogni ruolo necessario.
3. Se manca un ruolo critico, fallback al comportamento single-agent attuale e log warning.

**Acceptance criteria**
- `/api/chat` continua a rispondere anche con registry incompleto.
- In log è chiaro quali ruoli sono stati risolti.

### Patch 1.2 — Pipeline reader runtime (2 step)
**File:** `app.py`

1. Nel ramo reader (`admin_mode=false`):
   - Step A: `ReaderAnswerer` produce bozza.
   - Step B: `SpoilerJudge` valuta bozza.
2. Se unsafe:
   - riscrittura con prompt di rewrite del giudice (o guard prompt) e secondo audit.
3. Conservare `enforce_reader_safety(...)` come hard fallback finale.

**Acceptance criteria**
- Reader usa sempre almeno Answerer + Judge quando configurati.
- Nessuna regressione sull'anti-spoiler.

### Patch 1.3 — Pipeline author runtime (router + synth)
**File:** `app.py`

1. Nel ramo author (`admin_mode=true`):
   - Step A: `AuthorTaskRouter` produce piano task JSON (intent, tool suggeriti, priorità evidenze).
   - Step B: `AnswerSynthesizer` sintetizza risposta da piano + evidenze.
2. Se router assente/fallisce, fallback alla pipeline attuale.

**Acceptance criteria**
- In output interno (debug/log) è presente il piano router.
- Risposta finale resta invariata lato API (compatibile con frontend).

---

## Fase 2 — Tool-calling agentico automatico (reader/author)

### Obiettivo
Permettere agli agenti di invocare tool automaticamente durante `/api/chat` con guardrail e audit.

### Patch 2.1 — Tool planner + executor interno
**File:** `app.py`, `chat_tools.py`

1. Introdurre un formato intermedio per tool call (es. JSON: `[{tool, arguments}]`).
2. Implementare `execute_tool_plan(conn, plan, admin_mode, session_key)`:
   - valida nomi/argomenti
   - applica permessi (`update_chapter_fields` solo admin)
   - registra ogni run in `chat_tool_runs`.
3. Integrare nel loop chat:
   - reader: massimo N tool read-only
   - author: N tool read-only + mutating opzionale (con `dry_run` default true).

**Acceptance criteria**
- Tool run visibili in `/api/chat/tool-runs` per la sessione.
- Blocco automatico dei mutating tool in reader mode.

### Patch 2.2 — Prompt contract per tool
**File:** `prompts.json`, `agent_registry.py`

1. Definire prompt contract per i ruoli che possono chiedere tool.
2. Salvare versioni prompt agenti in `chat_agent_prompts` (kind `task/guard/rewrite/summary`).
3. Aggiungere validazione minima schema output tool-plan.

**Acceptance criteria**
- Se output non valido, fallback a no-tool + warning.
- Prompt versionati e tracciabili per ruolo.

### Patch 2.3 — UI gestione agenti: tool scope operativo
**File:** `app.py` (tab settings agenti)

1. Nella tab agenti, esporre `tool_scope` per agente (multi-select).
2. Salvataggio via `/api/agents/save` includendo `tool_scope`.
3. Visualizzazione strumenti concessi per ruolo.

**Acceptance criteria**
- Possibile limitare, da UI, quali tool ogni agente può invocare.

---

## Fase 3 — Locale-first completo + vector DB locale + MCP

### Obiettivo
Chiudere il ciclo “opera finita -> indicizzazione locale -> interrogazione esterna MCP” mantenendo sicurezza reader.

### Patch 3.1 — Build indice vettoriale locale
**File:** nuovo modulo `vector_index_local.py`, script in `docs/agentic_chat_rollout/sqlite/` se serve

1. Pipeline offline:
   - chunk capitoli
   - embedding locale
   - metadati (cap_id, personaggi, linea, timeline_event_id)
2. Persistenza locale (SQLite + blob/FAISS/alternativa locale già disponibile).

**Acceptance criteria**
- Comando rebuild idempotente.
- Query top-k con filtro `cap_id <= frontier` per reader.

### Patch 3.2 — Retriever tool su vector DB
**File:** `chat_tools.py`, `app.py`

1. Nuovi tool read-only:
   - `vector_search_reader(query, cap_id, k)`
   - `vector_search_author(query, k)`
2. Reader tool sempre con frontier anti-spoiler.
3. Logging run e tempi come gli altri tool.

**Acceptance criteria**
- Risultati grounded con metadati di provenienza.

### Patch 3.3 — Endpoint MCP bridge (solo read)
**File:** nuovo `mcp_bridge.py` + route in `app.py`

1. Esporre endpoint read-only per interrogare vector DB da server MCP esterno.
2. Auth forte (token dedicato) + rate limit + audit.
3. Policy separata reader/author anche lato MCP.

**Acceptance criteria**
- MCP esterno interroga local DB senza accesso diretto al core write.

---

## Piano di rilascio consigliato

1. **Release A (Fase 1):** multi-role runtime senza tool-calling automatico.
2. **Release B (Fase 2):** tool-calling automatico con audit e scope.
3. **Release C (Fase 3):** vector DB locale + MCP read bridge.

Ogni release con feature flag:
- `AGENTIC_MULTIROLE_ENABLED`
- `AGENTIC_AUTOTOOLS_ENABLED`
- `LOCAL_VECTOR_DB_ENABLED`
- `MCP_BRIDGE_ENABLED`

---

## Smoke test operativo per fase

### Fase 1
- Reader: domanda ambigua su cap alto -> risposta + audit judge attivo.
- Author: richiesta analisi coerenza -> router plan + sintesi finale.

### Fase 2
- Reader: tool mutante richiesto -> blocco autorizzativo.
- Author: tool plan valido -> esecuzione + traccia in `chat_tool_runs`.

### Fase 3
- Rebuild indice locale -> query reader filtrata -> query author full.
- Query MCP esterna autenticata -> risposta con evidenze.
