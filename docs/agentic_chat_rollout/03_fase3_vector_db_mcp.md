# Fase 3 — Vector DB locale e interoperabilità MCP

## Outcome della fase

Preparare l'opera finita e i metadati per retrieval semantico locale e interrogazione da server MCP esterno.

## Stato implementativo corrente (aggiornato)

### ✅ Completato nel codice

- Indicizzazione locale con `vector_index_local.py`:
  - chunking + embedding locale/fallback;
  - rebuild/search/stats;
  - versioning indice (`vector_index_versions`, `active_version`, `list_index_versions`).
- Endpoint vector:
  - `GET /api/vector-index/stats`
  - `GET /api/vector-index/versions`
  - `POST /api/vector-index/rebuild`
  - `POST /api/vector-index/refresh` (delta per `cap_ids`)
  - `GET /api/vector-index/search`
- MCP bridge hardening:
  - `POST /api/mcp/vector-search` con auth bearer policy-based;
  - rate-limit persistente SQLite;
  - audit avanzato su token/client (`mcp_bridge_audit`);
  - policy token scope `reader/author/both`, `tenant_id`, `max_cap_id`.
- Endpoint meta MCP:
  - `GET /api/mcp/health`
  - `GET /api/mcp/capabilities`
  - `GET /api/mcp/list_vector_index_versions` (bearer).
- Operatività enterprise MCP:
  - CRUD token + rotazione: `/api/mcp/tokens*`;
  - analytics audit: `GET /api/mcp/audit/analytics`;
  - cleanup retention: `POST /api/mcp/audit/cleanup`.

### 🔄 Residuo fase 3

- Alerting e KPI operativi (p95 latency, unauthorized spike, saturation rate-limit).
- Test E2E runtime HTTP/streaming in ambiente completo.

## Task 3.1 — Pipeline di export dell'opera

### Implementazione operativa

1. Estrarre bundle per:
   - capitolo pubblico;
   - capitolo completo;
   - stato personaggio pubblico;
   - stato personaggio completo;
   - timeline event;
   - symbol thread.
2. Serializzare in JSONL o SQLite secondario dedicato all'indice.
3. Versionare gli export.

### Criterio di accettazione

L'opera può essere ricostruita in forma indicizzabile senza dipendere dal prompt builder runtime.

---

## Task 3.2 — Builder vector index locale

### File da creare

- `vector_index_builder.py`

### Implementazione operativa

1. Chunking controllato per tipo documento.
2. Attributi minimi per ogni chunk:
   - `doc_type`
   - `cap_start`
   - `cap_end`
   - `spoiler_level`
   - `characters`
   - `themes`
   - `source_ref`
3. Embedding locale.
4. Persistenza con manifest versione indice.

### Criterio di accettazione

Esiste un indice locale versionato ricostruibile offline.

---

## Task 3.3 — Query layer riusabile da MCP

### Implementazione operativa

Definire query stabili, ad esempio:

- `search_work_canon(query, scope, max_cap_id)`
- `get_chapter_bundle(cap_id, mode)`
- `get_character_bundle(name, mode, max_cap_id)`
- `get_timeline_bundle(range_or_cap_id)`
- `list_vector_index_versions()`

### Criterio di accettazione

Lo stesso contratto può essere usato sia dalla chat interna sia da un server MCP esterno.

### Stato attuale task 3.3

Parzialmente completato e operativo:

- query semantica condivisa via `vector_search_*` e `search_index(...)`;
- `list_vector_index_versions()` disponibile;
- endpoint bridge/read-only disponibili e documentati.

Da estendere in futuro:

- query bundle dedicate (`get_chapter_bundle`, `get_character_bundle`, `get_timeline_bundle`).

---

## Task 3.4 — Boundary spoiler anche su MCP

### Implementazione operativa

1. Rendere obbligatorio `max_cap_id` per tutte le query reader-facing.
2. Etichettare ogni chunk con `spoiler_level`.
3. Bloccare retrieval incompatibili col profilo reader.

### Criterio di accettazione

L'apertura verso MCP non reintroduce spoiler leakage nel ramo lettore.

### Stato attuale task 3.4

Completato a livello policy endpoint:

- `mode=reader` richiede `cap_id` valido;
- policy token con `scope` e limite `max_cap_id`;
- blocco 403 su scope/cap non compatibili;
- audit degli esiti (unauthorized, forbidden_scope, forbidden_cap, rate_limited, ok/error).
