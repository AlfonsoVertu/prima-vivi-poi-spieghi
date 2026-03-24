# Fase 3 — Vector DB locale e interoperabilità MCP

## Outcome della fase

Preparare l'opera finita e i metadati per retrieval semantico locale e interrogazione da server MCP esterno.

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

---

## Task 3.4 — Boundary spoiler anche su MCP

### Implementazione operativa

1. Rendere obbligatorio `max_cap_id` per tutte le query reader-facing.
2. Etichettare ogni chunk con `spoiler_level`.
3. Bloccare retrieval incompatibili col profilo reader.

### Criterio di accettazione

L'apertura verso MCP non reintroduce spoiler leakage nel ramo lettore.
