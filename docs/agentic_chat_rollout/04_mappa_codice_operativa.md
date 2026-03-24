# Mappa codice operativa (agentic chat) — guida di manutenzione completa

Questo documento è la reference operativa per capire **dove** è implementato ogni comportamento dell’agentic chat, **come** viene controllato, e **cosa verificare prima di toccare il codice**.

> Obiettivo: ridurre regressioni su safety, coerenza canone e integrazioni provider durante evoluzioni future.

---

## 1) Mappa componenti principali

### `app.py` (orchestrazione API/runtime)
- Punto di ingresso Flask.
- Espone endpoint agenti/provider/tool/memory/spoiler-audit.
- Coordina:
  - risoluzione agent/model runtime dal registry;
  - chiamata tool executor e logging `chat_tool_runs`;
  - iniezione history/memory;
  - enforcement safety reader post-sintesi;
  - bridge MCP con policy token/rate-limit/audit persistenti.

**Attenzione**
- Modifiche qui hanno impatto trasversale (auth, DB, safety, UX API).
- Ogni nuovo endpoint dovrebbe rispettare pattern:
  - `ensure_agent_registry_schema(conn)`
  - gestione errori con status HTTP coerente
  - `conn.close()` in `finally`.

### `agent_registry.py` (stato persistente agentico)
- Definisce schema SQLite runtime:
  - `provider_endpoints`
  - `chat_agents`
  - `chat_agent_prompts`
  - `chat_sessions`
  - `chat_session_memory`
  - `chat_tool_runs`
  - `provider_discovery_cache`
  - `mcp_bridge_tokens`
  - `mcp_bridge_rate_limits`
  - `mcp_bridge_audit`
- Gestisce seed, CRUD, validazioni, import/export bundle, readiness report.

**Attenzione**
- Cambi schema = aggiornare anche SQL docs in `docs/agentic_chat_rollout/sqlite/`.
- Mantenere compatibilità key (`agent_key`, `endpoint_key`) con pattern validation.

### `chat_tools.py` (tool registry/executor)
- Tool read-only e mutating con controllo `admin_mode`.
- Validazione argomenti (`_to_int`) e catalogo (`TOOL_SPECS`).
- Esecuzione centralizzata via `execute_tool`.

**Attenzione**
- Ogni tool mutante deve restare bloccato in reader mode.
- Qualsiasi nuova mutazione deve avere guardrail su campi ammessi.

### `chat_memory.py` (session memory)
- Normalizza history e persiste snapshot compatto sessione.
- Sostiene continuità conversazionale senza sovraccarico di contesto.

**Attenzione**
- Modifiche ai campi memory richiedono migrazione schema + fallback.

### `spoiler_guard.py` (safety reader)
- Audit risposta reader rispetto a confine di conoscenza.
- Supporta rewrite/fallback safe.

**Attenzione**
- Ogni allentamento regole è ad alto rischio prodotto.

### `provider_discovery.py` / `llm_client.py`
- Discovery e test endpoint provider.
- Adattatori chiamata LLM per provider supportati.

**Attenzione**
- Timeout e gestione errori devono restare espliciti.
- Non introdurre branch provider “silenziosi” (fallimenti non loggati).

---

## 2) Tracciato endpoint → funzione → controllo

## 2.1 Registry agenti
- `GET /api/agents` → listing agenti/endpoints dal registry.
- `POST /api/agents/bootstrap` → `seed_defaults`.
- `POST /api/agents/save` → `upsert_agent`.
- `GET /api/agents/<agent_key>` → `get_agent`.
- `POST /api/agents/<agent_key>/enabled` → `set_agent_enabled`.
- `DELETE /api/agents/<agent_key>` → `delete_agent`.
- `GET /api/agents/validate` → `validate_agent_configuration`.
- `GET /api/agents/export` → `export_registry_bundle`.
- `POST /api/agents/import` → `import_registry_bundle`.
- `GET /api/agentic/readiness` → `readiness_report`.
- `POST /api/agentic/bootstrap-full` → seed + readiness.

Controlli chiave:
- validazione chiavi `agent_key`/`endpoint_key`;
- provider/mode ammessi;
- blocco endpoint delete se in uso;
- import con `overwrite` e `import_disabled`.

## 2.2 Provider endpoint & discovery
- `POST /api/provider-endpoints/save`
- `GET /api/provider-endpoints/<endpoint_key>`
- `DELETE /api/provider-endpoints/<endpoint_key>`
- `POST /api/provider-endpoints/discover`
- `POST /api/provider-endpoints/test`
- `GET /api/provider-endpoints/discovery-cache`

Controlli chiave:
- risoluzione provider/base URL/API key dal registry;
- persistenza modelli scoperti in `provider_discovery_cache`.

## 2.3 Tool runtime
- `GET /api/chat/tools` (`?detailed=1`)
- `POST /api/chat/tools/execute`
- `GET /api/chat/tool-runs`

Controlli chiave:
- blocco tool mutanti fuori admin mode;
- validazione argomenti tool;
- logging `chat_tool_runs` con `duration_ms`;
- auto-creazione `chat_sessions` se `session_key` nuova.

## 2.4 Memory e safety
- `GET /api/chat/memory` (snapshot lettura)
- `POST /api/chat/spoiler-audit`
- `POST /api/chat/<cap_id>` (flow completo)

Controlli chiave:
- history normalizzata e persistita;
- audit spoiler non-stream + streaming;
- fallback safe in caso di output non conforme.

## 2.5 Vector/MCP
- `GET /api/vector-index/stats`
- `GET /api/vector-index/versions`
- `POST /api/vector-index/rebuild`
- `POST /api/vector-index/refresh`
- `GET /api/vector-index/search`
- `GET /api/mcp/health`
- `GET /api/mcp/capabilities`
- `GET /api/mcp/list_vector_index_versions`
- `POST /api/mcp/vector-search`
- `GET /api/mcp/tokens`
- `POST /api/mcp/tokens/save`
- `POST /api/mcp/tokens/<token_id>/rotate`
- `POST /api/mcp/tokens/<token_id>/enabled`
- `DELETE /api/mcp/tokens/<token_id>`
- `GET /api/mcp/audit/analytics`
- `POST /api/mcp/audit/cleanup`

Controlli chiave:
- `mode=reader` con `cap_id` obbligatorio;
- policy token MCP (`scope`, `tenant_id`, `max_cap_id`, `rate_limit_per_minute`);
- rate-limit persistente SQLite (`mcp_bridge_rate_limits`);
- audit strutturato (`mcp_bridge_audit`) per esito/latency/client/token.
- delta indexing per capitoli specifici (riduce costo rebuild totale).

---

## 3) Regole invarianti (da NON rompere)

1. **Reader safety first**: nessuna risposta reader deve saltare audit/fallback.
2. **Mutazioni capitolo in admin mode only**.
3. **Session/tool logging sempre persistito quando applicabile**.
4. **Schema compatibile backward**: evitare rename distruttive senza migrazione.
5. **Provider discovery robusta**: timeout + errore esplicito al client.
6. **Auth su endpoint sensibili** (`@login_required`).

---

## 4) Checklist pre-modifica (obbligatoria)

Prima di modificare:
1. Individua endpoint/funzione impattata in questa mappa.
2. Verifica se tocca:
   - safety reader
   - mutazioni DB
   - compatibilità schema
   - routing provider.
3. Definisci come testare:
   - unit test locale su `tests/test_agentic_backend.py`
   - smoke endpoint interessati.
4. Aggiorna documentazione:
   - `README.md`
   - `docs/D_piano_implementazione_chat_agentica_locale.md`
   - `docs/agentic_chat_rollout/README.md`
   - `docs/agentic_chat_rollout/PROGRESS.md`
   - questo file se cambia la mappa.

Dopo modifica:
1. `python -m py_compile ...`
2. `python -m pytest tests/test_agentic_backend.py -q`
3. Verifica percentuali/progresso se cambia la maturità fase.

---

## 5) Checklist potenziamenti futuri (safe-by-design)

### Se aggiungi un nuovo tool
- Inserire in `TOOL_SPECS`.
- Decidere read-only vs mutating.
- Validare argomenti in `execute_tool`.
- Aggiungere test dedicato.
- Aggiornare docs API.

### Se aggiungi un nuovo provider
- Aggiornare set provider ammessi in registry.
- Implementare discover/test adapter.
- Gestire credenziali via env/endpoint config.
- Estendere test e docs.

### Se modifichi logica spoiler
- Testare casi limite (frasi allusive, spoiler indiretti).
- Verificare comportamento streaming e non-stream.
- Conservare logging eventi audit.

### Se cambi schema registry
- Aggiornare SQL docs e fallback runtime.
- Assicurare idempotenza `ensure_schema`.
- Evitare rotture su database esistenti.

---

## 6) Cosa considerare prima del go-live

Usare `GET /api/agentic/readiness`:
- `summary.go_live_ready` deve essere true.
- Nessun `error` bloccante in validation.
- Copertura ruoli minima:
  - `ReaderAnswerer`
  - `SpoilerJudge`
  - `AnswerSynthesizer`.

Usare `POST /api/agentic/bootstrap-full` per:
- seed defaults;
- report readiness immediato.

---

## 7) Nota su Fase 3

Fase 3 (Vector DB/MCP) è un acceleratore importante, ma **non è bloccante** per avvio operativo base se Fase 1+2 sono green.
