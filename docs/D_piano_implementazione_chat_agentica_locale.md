# Piano concreto di implementazione della chat agentica locale-first

## Obiettivo

Potenziare le due chat esistenti del software — lettore/frontend e autore/backend — trasformandole da pipeline principalmente prompt-driven a sistema agentico grounded, locale-first e compatibile con modelli serviti da LM Studio.

Il piano qui proposto è ancorato all'implementazione reale del repository:

- endpoint chat unificato su `/api/chat/<cap_id>`;
- pipeline di orchestrazione in `app.py` + `ai_orchestrator.py`;
- base conoscitiva strutturata in SQLite (`capitoli`, `timeline`, `personaggi`, `personaggi_capitoli`);
- API funzionali già presenti per aggiornare capitoli e metadati;
- supporto provider locale tramite endpoint OpenAI-compatible di LM Studio.

## Stato implementativo corrente

Per un tracking operativo quantitativo dell'avanzamento, vedi anche `docs/agentic_chat_rollout/PROGRESS.md`.
Per la mappa manutentiva dettagliata endpoint/codice/controlli, vedi `docs/agentic_chat_rollout/04_mappa_codice_operativa.md`.


Oltre alla documentazione, il repository contiene ora una prima foundation concreta per la roadmap:

- `agent_registry.py` per creare/seedare il registry agenti e gli endpoint provider in SQLite;
- `provider_discovery.py` per discovery/test di LM Studio, Ollama e OpenAI-compatible;
- endpoint Flask `/api/agents`, `/api/agents/bootstrap`, `/api/agents/save`, `/api/agents/validate`, `/api/agents/export`, `/api/agents/import`, `/api/agents/<agent_key>`, `/api/agents/<agent_key>/enabled`, `/api/provider-endpoints/save`, `/api/provider-endpoints/<endpoint_key>`, `/api/provider-endpoints/discover`, `/api/provider-endpoints/test`, `/api/provider-endpoints/discovery-cache`, `/api/agentic/readiness`, `/api/agentic/bootstrap-full`, `/api/agents/test`, `/api/ollama/discover`, `/api/ollama/test`, `/api/openai-compatible/discover`, `/api/openai-compatible/test`, `/api/chat/memory`, `/api/chat/spoiler-audit`, `/api/chat/tools`, `/api/chat/tools/execute`, `/api/chat/tool-runs`.

Questa base non sostituisce ancora la pipeline chat attuale, ma riduce il gap fra piano e implementazione.

In più, lato chat API è stata avviata una prima iniezione controllata della history recente (normalizzazione ultimi turni), utile come ponte verso la memoria conversazionale strutturata.

È stato introdotto anche un primo guardrail applicativo `spoiler-audit` con fallback di riscrittura sicura (non-stream e post-sintesi streaming), con logging eventi su `chat_tool_runs`.

## Stato attuale sintetico

### Backend chat

Oggi entrambe le modalità chat passano da `/api/chat/<cap_id>`, distinguendo il comportamento solo tramite `admin_mode`.

La pipeline reale è composta da:

1. costruzione del contesto (`run_deep_context_pipeline` in `app.py`);
2. reasoning/sintesi oppure orchestrazione iterativa (`run_orchestrator_stream` in `ai_orchestrator.py`);
3. chiamata finale al modello con il provider selezionato.

### Dati già riusabili come strumenti interni

Il repository contiene già dati adatti a retrieval selettivo senza introdurre subito sistemi esterni:

- metadati di capitolo;
- riassunti e timeline per capitolo;
- anagrafica personaggi;
- stato personaggio per capitolo;
- testo integrale dei capitoli.

### Vincoli emersi

1. La chat lettore non è hard spoiler-safe: il canone completo entra ancora nel contesto lato orchestratore.
2. La `history` inviata dal frontend non viene realmente riutilizzata per memoria di sessione.
3. L'orchestrazione usa sotto-agenti, ma i tool reali sono ancora simulati da prompt su grandi blocchi di testo.
4. Il routing LM Studio è pensato come override unico, non come pool di modelli specializzati.
5. Le API funzionali esistono, ma non sono ancora esposte come tool della chat backend.

## Visione target

### Chat lettore

Una chat spoiler-safe che:

- conosce solo ciò che è accessibile fino al capitolo corrente;
- usa memoria di sessione per consolidare ciò che il lettore ha già capito;
- recupera fonti interne mirate invece di ricevere il canone completo;
- subisce un audit spoiler finale prima della risposta.

### Chat autore/backend

Una chat analitica che:

- conosce tutta l'opera e i metadati completi;
- può interrogare, confrontare e modificare il libro tramite tool interni;
- aiuta a riscrivere, revisionare, rigenerare capitoli e metadati;
- prepara in prospettiva un layer RAG locale dell'opera interrogabile anche da un server MCP esterno.

## Principi architetturali

1. **Knowledge frontier hard**: la chat lettore non deve mai ricevere il canone completo.
2. **Tool-first, non dump-first**: prima recupero selettivo, poi sintesi.
3. **Ruoli agentici separati**: router, retriever, synthesizer, auditor.
4. **Locale-first**: i task semplici e medi vanno su modelli locali; fallback cloud opzionale.
5. **Groundedness esplicita**: ogni risposta backend deve poter indicare le fonti interne usate.
6. **Compatibilità con vector DB locale futuro**: i contratti dei tool vanno definiti già ora per non dover riscrivere la chat dopo.
7. **Configurabilità per agente**: ogni agente deve avere prompt, provider, modello e capability configurabili da pannello.

## Configurazione dinamica degli agenti dal pannello

Questa è la richiesta aggiuntiva più importante da incorporare nel design: gli agenti non devono essere cablati solo nel codice, ma gestibili dall'interfaccia di configurazione.

### Obiettivo funzionale

Dal pannello admin deve essere possibile, per ogni agente del sistema:

- attivarlo/disattivarlo;
- cambiarne nome e ruolo operativo;
- modificare i prompt usati;
- selezionare provider e modello;
- scegliere se usa un modello cloud, un endpoint OpenAI-compatible custom, LM Studio oppure Ollama;
- impostare priorità, timeout, temperatura e fallback;
- decidere quali tool può usare.

### Tipi di provider da supportare

Per ogni agente configurabile, il piano deve supportare almeno questi target:

- **OpenAI** (modelli cloud)
- **Anthropic / Claude**
- **Google / Gemini**
- **OpenAI-compatible custom** (base URL + API key + model id)
- **LM Studio** con discovery dei modelli caricati
- **Ollama** con discovery dei modelli locali disponibili

### Implicazione architetturale

Il routing non può più dipendere solo da env globali come `LLM_PROVIDER` o `ADMIN_CHAT_MODEL`. Serve un registro persistente degli agenti con configurazione per ruolo e per provider.

---

## Fase 1 — Hardening immediato dell'architettura attuale

### Obiettivo

Correggere i problemi più urgenti senza riscrivere tutto il sistema.

### 1.1 Blindare il perimetro spoiler-free

#### Modifiche

- Estrarre da `run_deep_context_pipeline()` e da `run_orchestrator_stream()` una funzione condivisa `build_reader_frontier(cap_id)`.
- La funzione dovrà restituire solo:
  - metadati capitoli `<= cap_id`;
  - riassunti `<= cap_id`;
  - timeline ed eventi già accessibili;
  - personaggi introdotti fino a `cap_id`;
  - stato dei personaggi fino a `cap_id`;
  - testo capitolo corrente + opzionalmente capitolo precedente.
- Rimuovere completamente il canone completo dal `system_instruction` della chat lettore.

#### Beneficio

Il controllo spoiler passa da vincolo promptistico a vincolo architetturale.

### 1.2 Usare davvero la history della chat

#### Modifiche

- Leggere `history` nell'endpoint `/api/chat/<cap_id>`.
- Limitare la memoria breve agli ultimi 6-10 turni utili.
- Introdurre una memoria compressa di sessione lato server con struttura minima:
  - `facts_understood`;
  - `open_questions`;
  - `characters_followed`;
  - `themes_discussed`.
- In assenza di persistenza dedicata, mantenere inizialmente il summary in memoria o in file JSON per sessione.

#### Beneficio

La chat frontend potrà consolidare la comprensione del lettore invece di rispondere sempre single-turn.

### 1.3 Inserire uno Spoiler Auditor finale

#### Modifiche

Dopo la generazione della bozza reader:

1. passare risposta + `cap_id` + frontier al guard model;
2. ottenere esito `safe/unsafe`;
3. se `unsafe`, tentare una rigenerazione prudente o una riscrittura conservativa.

#### Contratto suggerito

```json
{
  "status": "safe | unsafe",
  "violations": ["future_event", "future_causality", "unknown_character", "future_interpretation"],
  "rewrite_instruction": "..."
}
```

### 1.4 Rendere espliciti i ruoli del backend chat

#### Modifiche

Mantenere gli agenti correnti, ma rinominarli e allinearli ai compiti reali:

- `metadata agent` -> `CanonRouter`;
- `summaries agent` -> `NarrativeHistorian`;
- `deep_text agent` -> `PassageReader`;
- orchestratore finale -> `ResponseSynthesizer`.

Aggiungere nei log/stati SSE il ruolo effettivo e la fonte usata.

### 1.5 Prima separazione dei modelli locali e cloud per agente

#### Nuove env suggerite

Queste env restano utili come default di bootstrap, ma non devono sostituire la configurazione per-agente da pannello:

- `LOCAL_ROUTER_MODEL`
- `LOCAL_READER_MODEL`
- `LOCAL_AUTHOR_MODEL`
- `LOCAL_GUARD_MODEL`
- `LOCAL_RERANK_MODEL`
- `ALLOW_CLOUD_FALLBACK`
- `OLLAMA_URL`
- `OPENAI_COMPATIBLE_URL`
- `OPENAI_COMPATIBLE_API_KEY`

#### Modifiche

- Estendere il resolver del provider/model in `llm_client.py` o in un nuovo modulo `model_routing.py`.
- Mantenere compatibilità con `ADMIN_CHAT_MODEL`, ma trattarlo come fallback legacy.
- Introdurre una risoluzione a cascata: `agent config` -> `workspace defaults` -> `legacy env`.
- Aggiungere discovery separata per LM Studio e Ollama direttamente dal pannello.

### 1.6 Registro agenti configurabile da interfaccia

#### Nuovo concetto

Serve un archivio persistente degli agenti, ad esempio in SQLite, con una tabella dedicata `chat_agents` e una tabella `chat_agent_prompts`.

#### Campi minimi consigliati

- `agent_key`
- `label`
- `mode` (`reader`, `author`, `shared`)
- `provider_type` (`openai`, `anthropic`, `gemini`, `openai_compatible`, `lmstudio`, `ollama`)
- `model_id`
- `base_url`
- `api_key_ref`
- `system_prompt`
- `task_prompt`
- `temperature`
- `max_tokens`
- `timeout_sec`
- `enabled`
- `tool_scope`
- `priority`
- `fallback_agent_key`

#### UI minima da aggiungere

Nel pannello di configurazione vanno previste almeno queste azioni:

- creare un nuovo agente;
- duplicare un agente esistente;
- cambiare provider/modello per agente;
- modificare prompt di sistema e prompt task-specific;
- lanciare `discover` per LM Studio;
- lanciare `discover` per Ollama;
- testare la configurazione del singolo agente;
- riordinare la pipeline degli agenti.

### Deliverable Fase 1

- reader frontier hard;
- memoria breve + summary sessione;
- spoiler auditor finale;
- model routing per ruoli e per singolo agente;
- registro agenti configurabile da pannello;
- log più trasparenti su agenti e fonti.

---

## Fase 2 — Backend chat come sistema tool-based reale

### Obiettivo

Fare in modo che la chat backend possa aiutare l'autore anche ad agire sull'opera, non solo a commentarla.

### 2.1 Introdurre un registry di tool interni

Creare un modulo dedicato, ad esempio `chat_tools.py`, con funzioni pure e output JSON stabile.

### Tool di retrieval da introdurre subito

- `get_chapter_metadata(cap_id)`
- `get_chapter_text(cap_id)`
- `get_chapter_summary(cap_id)`
- `get_summaries_until(cap_id)`
- `get_character_state(name, max_cap_id=None)`
- `get_character_arc(name)`
- `get_timeline_until(cap_id)`
- `search_passages(keyword, cap_id=None, admin_mode=false)`
- `get_cross_chapter_links(cap_id)`

### Tool azionali per la chat autore

Questi tool devono essere wrapper sicuri sopra le API funzionali v1 già presenti nel software.

- `update_chapter_fields(cap_id, patch)`
- `rewrite_chapter(cap_id, instruction)`
- `revise_chapter(cap_id, instruction)`
- `regenerate_metadata(target_ids, instruction)`
- `enrich_metadata(cap_id, fields)`
- `validate_chapter_consistency(cap_id)`

### Regola operativa

La chat backend non deve scrivere direttamente nel DB o sui file passando solo dal testo della risposta del modello. Deve invece:

1. pianificare;
2. dichiarare il tool da usare;
3. eseguire il tool applicativo;
4. sintetizzare l'esito per l'autore.

### 2.2 Contratto di tool-call comune

Definire un formato unico di chiamata/risposta tra orchestratore e tool:

```json
{
  "tool": "update_chapter_fields",
  "arguments": {
    "cap_id": 12,
    "patch": {
      "titolo": "...",
      "riassunto": "..."
    }
  }
}
```

Risposta tool:

```json
{
  "ok": true,
  "tool": "update_chapter_fields",
  "result": {
    "updated_fields": ["titolo", "riassunto"],
    "cap_id": 12
  },
  "grounding": [
    "capitoli.id=12"
  ]
}
```

### 2.3 Due stack agentici distinti

#### Reader stack

- `ReaderRouter`
- `AllowedContextRetriever`
- `ReaderAnswerer`
- `SpoilerJudge`

#### Author stack

- `AuthorTaskRouter`
- `CanonRetriever`
- `TimelineChecker`
- `CharacterConsistencyChecker`
- `ToolExecutor`
- `AnswerSynthesizer`

#### Nota di configurazione

Questi stack non devono essere hardcoded come unica sequenza fissa. Il pannello deve permettere di associare a ogni ruolo un agente concreto configurato a DB, con provider e prompt modificabili. In pratica, `ReaderRouter` o `SpoilerJudge` diventano ruoli logici risolti verso agenti configurati dall'utente.

### 2.4 Tipi di task per la chat backend

Il router autore deve classificare almeno queste intenzioni:

- analisi tematica;
- audit coerenza;
- confronto capitoli;
- riscrittura capitolo;
- revisione capitolo;
- rigenerazione metadati;
- arricchimento metadati;
- preparazione dati per vettorializzazione;
- interrogazione canonica generale.

### 2.5 Risposte backend grounded

Ogni risposta autore dovrebbe poter includere internamente o mostrare opzionalmente:

- capitoli rilevanti;
- personaggi rilevanti;
- eventi timeline usati;
- tool eseguiti;
- modifiche effettuate.

### 2.6 Config schema degli agenti

#### Esempio di record persistito

```json
{
  "agent_key": "author_timeline_checker",
  "label": "Timeline Checker",
  "mode": "author",
  "provider": {
    "type": "ollama",
    "model": "qwen3:14b",
    "base_url": "http://127.0.0.1:11434"
  },
  "prompts": {
    "system": "...",
    "task": "..."
  },
  "runtime": {
    "temperature": 0.2,
    "max_tokens": 1200,
    "timeout_sec": 90
  },
  "tools": ["get_timeline_until", "get_cross_chapter_links"],
  "fallback_agent_key": "author_timeline_checker_cloud",
  "enabled": true
}
```

#### Effetto pratico

Questo permette di avere, per esempio:

- `ReaderAnswerer` su Gemini cloud;
- `SpoilerJudge` su LM Studio;
- `AuthorTaskRouter` su OpenAI-compatible custom;
- `TimelineChecker` su Ollama;
- `AnswerSynthesizer` su Claude.

### 2.7 Discovery provider dal pannello

#### Endpoint da prevedere

- `/api/lmstudio/discover`
- `/api/ollama/discover`
- `/api/openai-compatible/discover` (eventuale semplice model listing se disponibile)
- `/api/agents/test`

#### Comportamento atteso

- LM Studio: usare `/v1/models`;
- Ollama: usare `/api/tags`;
- provider cloud nativi: usare liste statiche curate o discovery dove disponibile;
- endpoint OpenAI-compatible custom: tentare `/v1/models`, ma con fallback manuale se il server non espone listing.

### Deliverable Fase 2

- registry tool;
- author chat con tool-calling esplicito;
- separazione reader/author stack;
- risposte con grounding e audit di coerenza.

---

## Fase 3 — Vector DB locale dell'opera + interoperabilità MCP

### Obiettivo

Preparare l'opera finita e i suoi metadati a essere indicizzati in locale e interrogati anche da un server MCP esterno al software.

### 3.1 Pipeline offline di indicizzazione locale

A opera conclusa, introdurre una pipeline di build che generi:

- chunk testuali dell'opera;
- chunk metadata-centrici;
- schede evento;
- schede personaggio;
- schede simboli/oggetti;
- schede relazioni cross-capitolo;
- embeddings locali;
- manifest con versionamento dell'indice.

### 3.2 Unità documentali consigliate

Per ottenere retrieval migliore senza spoiler accidentali:

- `chapter_summary_public`
- `chapter_summary_full`
- `chapter_passage`
- `character_state_public`
- `character_state_full`
- `timeline_event`
- `canon_rule`
- `symbol_thread`

### 3.3 Metadati minimi per chunk

Ogni record indicizzato dovrebbe avere almeno:

- `doc_type`
- `cap_start`
- `cap_end`
- `spoiler_level`
- `characters`
- `themes`
- `timeline_refs`
- `source_ref`
- `updated_at`

### 3.4 Compatibilità con server MCP esterno

Il software dovrebbe esportare due livelli:

1. **indice locale interrogabile internamente** per la chat;
2. **contratti di query stabili** per un server MCP esterno.

#### Query MCP suggerite

- `search_work_canon(query, scope, max_cap_id)`
- `get_chapter_bundle(cap_id, mode)`
- `get_character_bundle(name, mode, max_cap_id)`
- `get_timeline_bundle(range_or_cap_id)`
- `list_vector_index_versions()`

### 3.5 Boundary di sicurezza MCP

Anche se il server MCP è esterno al software, il filtro `max_cap_id` deve restare obbligatorio per qualunque interrogazione reader-facing.

### Deliverable Fase 3

- export locale dell'opera strutturata;
- pipeline embeddings locale;
- retrieval ibrido SQLite + vector DB;
- interfaccia MCP esterna coerente con i tool interni.

---

## Modifiche al codice consigliate per file

## `app.py`

### Interventi

- Far leggere davvero `history` in `/api/chat/<cap_id>`.
- Sdoppiare chiaramente le pipeline `reader_chat_flow()` e `author_chat_flow()`.
- Spostare fuori da `app.py` la logica di contesto/tool routing per ridurre accoppiamento.
- Mantenere nell'endpoint solo autenticazione, deserializzazione, scelta flow e serializzazione SSE/JSON.

## `ai_orchestrator.py`

### Interventi

- Sostituire i tre agenti attuali text-dump con ruoli guidati da tool.
- Aggiungere supporto a:
  - router pass;
  - retrieval pass;
  - guard/audit pass;
  - tool execution pass per backend.
- Rendere strutturato il dossier intermedio con JSON invece di testo libero.

## `llm_client.py`

### Interventi

- Introdurre risoluzione modello per ruolo.
- Lasciare il provider unificato, ma permettere routing per task.
- Preparare parametri distinti per modelli locali piccoli/medi.

## Nuovi moduli suggeriti

### `agent_registry.py`

Gestione persistente di:

- definizione agenti;
- mapping ruolo -> agente attivo;
- prompt e runtime config per agente;
- fallback provider/modello;
- permessi tool per agente.

### `provider_discovery.py`

Adapter unificato per:

- discovery LM Studio;
- discovery Ollama;
- discovery OpenAI-compatible custom;
- normalizzazione della lista modelli per la UI.

### `chat_memory.py`

Gestione di:

- memoria breve;
- riassunto sessione;
- profilo conversazionale reader/autore.

### `chat_tools.py`

Tool registry interno con output JSON stabile.

### `chat_retrieval.py`

Funzioni per:

- frontier reader;
- retrieval per capitolo/personaggio/timeline;
- ranking semplice iniziale da SQLite + testo.

### `model_routing.py`

Risoluzione provider/modello per ruolo agentico.

### `vector_index_builder.py`

Pipeline offline per creare l'indice locale dell'opera finita.

---

## Contratti dati consigliati

## 1. Router decision

```json
{
  "mode": "reader | author",
  "task_type": "analysis | clarify_plot | spoiler_safe_summary | consistency_audit | rewrite_chapter | revise_chapter | regenerate_metadata | enrich_metadata",
  "needs_tools": true,
  "needs_guard": true,
  "max_cap_id": 14
}
```

## 2. Grounded response payload interno

```json
{
  "answer": "...",
  "sources": [
    {"type": "chapter_summary", "ref": "cap:12"},
    {"type": "character_state", "ref": "personaggio:Lin@cap:12"}
  ],
  "tool_calls": [
    {"tool": "get_character_state", "arguments": {"name": "Lin", "max_cap_id": 12}}
  ],
  "guard": {
    "status": "safe"
  }
}
```

## 3. Session memory payload

```json
{
  "session_id": "...",
  "mode": "reader",
  "max_cap_id": 12,
  "facts_understood": ["..."],
  "open_questions": ["..."],
  "characters_followed": ["..."],
  "themes_discussed": ["..."],
  "last_updated": "ISO-8601"
}
```

---

## Strategia provider e modelli per agente

## Obiettivo operativo

Far funzionare il sistema anche su una macchina locale con GPU consumer, evitando di chiedere a un solo modello di fare tutto e lasciando comunque la libertà di assegnare a ciascun agente un modello cloud o locale diverso.

## Distribuzione ruoli consigliata

Ogni ruolo può essere mappato da pannello a uno tra: provider cloud nativi, endpoint OpenAI-compatible custom, LM Studio, Ollama. Il contratto dell'agente deve restare identico a prescindere dal backend scelto.

### Modello piccolo

Per:

- routing intenti;
- classificazione task;
- spoiler guard;
- check di coerenza rapidi;
- trasformazioni JSON corte.

### Modello medio

Per:

- risposta reader finale;
- analisi autore standard;
- revisione capitolo breve;
- sintesi grounded.

### Modello medio/alto o fallback cloud

Per:

- riscritture lunghe;
- audit macrotrama complessi;
- confronto su molti capitoli;
- rigenerazioni estese.

## Policy suggerita

1. `locale-first` sempre.
2. `cloud-fallback` solo se:
   - task troppo lungo;
   - troppi chunk da sintetizzare;
   - richiesta di qualità massima esplicita;
   - timeout o errore del modello locale.

---

## Backlog tecnico prioritizzato

## Sprint 1

- reader frontier hard;
- uso reale della history;
- spoiler auditor;
- env nuove per model routing;
- aggiornamento README.

## Sprint 2

- `agent_registry.py`;
- `provider_discovery.py`;
- `chat_tools.py`;
- `chat_retrieval.py`;
- `author_chat_flow()` con tool-calling;
- grounding interno delle risposte.

## Sprint 3

- session memory persistente;
- ranking/reranking locale;
- log strutturati per eval;
- test automatici di leakage spoiler.

## Sprint 4

- export opera finita;
- builder vector DB locale;
- query layer riusabile da MCP esterno;
- retrieval ibrido strutturato + semantico.

---

## Suite di valutazione minima da introdurre

## Reader eval

Casi esempio:

- "Riassumimi cosa devo aver capito fin qui senza spoiler."
- "Perché questo personaggio sembra ambiguo al capitolo X?"
- "Posso fidarmi di Y?"
- "Che significato ha quell'oggetto fino a questo punto?"

### Metriche

- spoiler leakage rate;
- groundedness;
- pertinenza al capitolo;
- continuità conversazionale;
- latenza locale.

## Author eval

Casi esempio:

- "Trova contraddizioni tra capitolo 18 e 44."
- "Rigenera i metadati del capitolo 22 mantenendo il POV."
- "Riscrivi il capitolo 31 enfatizzando il conflitto con X."
- "Quali simboli tornano nell'arco di Lin?"

### Metriche

- correttezza tool selection;
- percentuale task completati;
- groundedness su fonti interne;
- qualità modifica prodotta;
- costo/tempo locale vs cloud.

---

## Raccomandazione finale

La priorità pratica non è aggiungere più prompt, ma dare alla chat backend e frontend una struttura operativa chiara:

1. frontiera di conoscenza hard per il lettore;
2. memoria di sessione reale;
3. tool interni stabili per leggere/modificare l'opera;
4. routing di modelli locali per ruolo;
5. pipeline compatibile fin da subito con un vector DB locale e con un server MCP esterno.

In questo modo il software può evolvere senza strappi da:

- chat contestuale prompt-driven;
- a orchestratore tool-based;
- fino a sistema locale-first grounded sull'intera opera e interrogabile anche fuori dall'app.
