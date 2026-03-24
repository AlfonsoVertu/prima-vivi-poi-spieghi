# Fase 2 — Registry agenti, tool backend e pannello

## Outcome della fase

Rendere la chat backend capace di leggere e modificare l'opera tramite tool reali, con agenti configurabili dal pannello.

## Task 2.1 — Introdurre il registry agenti persistente

### Obiettivo

Spostare la definizione degli agenti da costanti hardcoded a record salvati in SQLite.

### File da creare/toccare

- nuovo `agent_registry.py`
- `app.py`
- `roman.db` tramite migrazione SQL

### Implementazione operativa

1. Creare tabella `chat_agents`.
2. Creare tabella `chat_agent_prompts`.
3. Creare tabella `provider_endpoints`.
4. Salvare per ogni agente:
   - ruolo logico;
   - provider;
   - modello;
   - base URL;
   - api key ref;
   - runtime settings;
   - scope tool;
   - fallback.

### Criterio di accettazione

Gli agenti della pipeline vengono risolti da DB e non più solo dal codice.

---

## Task 2.2 — Provider discovery dal pannello

### Obiettivo

Permettere all'admin di vedere i modelli disponibili su backend locali o custom.

### File da creare/toccare

- nuovo `provider_discovery.py`
- `app.py`
- UI HTML dentro `app.py`

### Implementazione operativa

1. Estrarre discovery LM Studio in un adapter dedicato.
2. Aggiungere discovery Ollama via `/api/tags`.
3. Aggiungere discovery OpenAI-compatible custom via `/v1/models`.
4. Normalizzare il risultato per la UI.
5. Aggiungere test connessione per il singolo agente.

### Criterio di accettazione

Dal pannello si può selezionare un agente, scegliere il provider e visualizzare la lista modelli scoperti.

---

## Task 2.3 — Tool registry interno per la chat autore

### Stato attuale nel repository

- È ora presente un primo executor backend via endpoint (`/api/chat/tools`, `/api/chat/tools/execute`) con logging su `chat_tool_runs`.
- `/api/chat/tools` ora supporta anche `?detailed=1` per restituire catalogo tool con descrizione/argomenti.
- Sono state aggiunte API backend per salvataggio config dinamica (`/api/agents/save`, `/api/provider-endpoints/save`).
- Sono presenti API di manutenzione configurazione (`/api/agents/validate`, enable/disable e delete agent, get/delete endpoint con protezione su endpoint in uso).
- Aggiunte API di portabilità configurazione (`/api/agents/export`, `/api/agents/import`) per backup/restore o bootstrap multi-ambiente.
- Aggiunte API centralizzate di discovery/test endpoint dal registry (`/api/provider-endpoints/discover`, `/api/provider-endpoints/test`) con cache locale interrogabile (`/api/provider-endpoints/discovery-cache`).
- Aggiunte API di readiness/boot completo (`/api/agentic/readiness`, `/api/agentic/bootstrap-full`) per checklist go-live Fase 1+2.
- Tool coperti: retrieval principali + `list_chapters_range` + audit con `get_recent_tool_runs` + `update_chapter_fields` (anche `dry_run`) in admin mode.
- Aggiunta base test automatizzata (`tests/test_agentic_backend.py`) per smoke/regressione su registry + tool executor.


### Obiettivo

Permettere alla chat backend di agire sull'opera senza scrivere direttamente SQL o testo libero.

### File da creare/toccare

- nuovo `chat_tools.py`
- `app.py`
- eventuale refactor di API funzionali esistenti

### Implementazione operativa

Creare wrapper JSON-safe per almeno questi tool:

- `get_chapter_metadata(cap_id)`
- `get_chapter_text(cap_id)`
- `get_character_state(name, max_cap_id=None)`
- `get_timeline_until(cap_id)`
- `update_chapter_fields(cap_id, patch)`
- `rewrite_chapter(cap_id, instruction)`
- `revise_chapter(cap_id, instruction)`
- `regenerate_metadata(target_ids, instruction)`
- `enrich_metadata(cap_id, fields)`
- `validate_chapter_consistency(cap_id)`

### Criterio di accettazione

La chat autore può eseguire operazioni reali tramite tool dichiarati e risultati strutturati.

---

## Task 2.4 — UI di configurazione agenti

### Obiettivo

Esporre nel pannello admin una gestione reale degli agenti.

### File da creare/toccare

- `app.py`
- `ui_settings.json` se ancora utile come default legacy

### Implementazione operativa

La UI deve permettere almeno di:

- creare/duplicare/disattivare un agente;
- modificare prompt di sistema e prompt task;
- scegliere provider e modello;
- impostare `temperature`, `max_tokens`, `timeout_sec`;
- associare tool consentiti;
- assegnare fallback provider/modello;
- riordinare gli agenti per pipeline reader e author.

### Criterio di accettazione

La definizione di un agente può essere cambiata da interfaccia senza editare file Python.

---

## Task 2.5 — Stack author realmente tool-based

### Obiettivo

Sostituire l'attuale pattern di sub-agent prompt-driven con agenti che usano retrieval e tool execution.

### File da creare/toccare

- `ai_orchestrator.py`
- `chat_tools.py`
- `chat_retrieval.py`
- `agent_registry.py`

### Implementazione operativa

1. `AuthorTaskRouter` classifica il task.
2. `CanonRetriever` recupera le fonti minime necessarie.
3. `TimelineChecker` e `CharacterConsistencyChecker` fanno validazione mirata.
4. `ToolExecutor` lancia i tool consentiti.
5. `AnswerSynthesizer` produce output grounded.

### Criterio di accettazione

Una richiesta tipo “rigenera i metadati del capitolo 22 mantenendo il POV” produce tool-call reale + esito strutturato + risposta finale.
