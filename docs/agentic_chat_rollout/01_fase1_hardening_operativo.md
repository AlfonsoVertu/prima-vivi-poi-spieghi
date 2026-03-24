# Fase 1 — Hardening operativo

## Outcome della fase

Ottenere una chat lettore realmente spoiler-safe e una base tecnica pronta per introdurre agenti configurabili senza rompere la pipeline esistente.

## Task 1.1 — Estrarre la reader frontier

### Obiettivo

Sostituire il contesto reader basato su dump globale con un contesto filtrato per `cap_id`.

### File da toccare

- `app.py`
- `ai_orchestrator.py`
- nuovo `chat_retrieval.py`

### Implementazione operativa

1. Creare `build_reader_frontier(cap_id, include_previous=True)` in `chat_retrieval.py`.
2. Estrarre da SQLite:
   - capitoli `id <= cap_id`;
   - riassunti accessibili;
   - timeline collegate o comunque coerenti con il punto di lettura;
   - personaggi introdotti entro `cap_id`;
   - stato personaggi da `personaggi_capitoli` fino a `cap_id`.
3. Eliminare il canone completo dal ramo reader in `run_deep_context_pipeline()`.
4. Eliminare il canone completo dal ramo reader in `run_orchestrator_stream()`.
5. Mantenere il canone completo solo in `admin_mode=True`.

### Query SQLite di riferimento

```sql
SELECT id, titolo, pov, riassunto
FROM capitoli
WHERE id <= :cap_id
ORDER BY id;
```

```sql
SELECT p.nome, pc.capitolo_id, pc.stato_emotivo, pc.obiettivo, pc.sviluppo
FROM personaggi_capitoli pc
JOIN personaggi p ON p.id = pc.personaggio_id
WHERE pc.capitolo_id <= :cap_id
ORDER BY pc.capitolo_id, p.nome;
```

### Criterio di accettazione

Una richiesta reader non contiene mai il canone completo né dati da capitoli futuri.

---

## Task 1.2 — Usare davvero la history


### Stato attuale nel repository

- È stata introdotta una prima integrazione di `history` in `/api/chat/<cap_id>` con normalizzazione e iniezione nel prompt utente.
- È stato aggiunto un memory snapshot persistito su SQLite tramite `chat_sessions` e `chat_session_memory`.
- È stata aggiunta una prima safety net non-stream con spoiler audit post-answer e fallback di riscrittura sicura.
- Resta da fare il passo successivo: memoria compressa strutturata reader/author e tuning della UX di audit streaming (ora presente come post-sintesi).


### Obiettivo

Far sì che `history` entri nella pipeline e alimenti una memoria breve + una memoria compressa.

### File da toccare

- `app.py`
- nuovo `chat_memory.py`

### Implementazione operativa

1. Leggere `history` in `/api/chat/<cap_id>`.
2. Normalizzare i messaggi tenendo solo `role` e `content`.
3. Limitare a una finestra di ultimi 6-10 turni.
4. Generare un mini-summary strutturato con chiavi:
   - `facts_understood`
   - `open_questions`
   - `characters_followed`
   - `themes_discussed`
5. Iniettare memoria breve + summary solo nel ramo coerente (`reader` o `author`).

### Criterio di accettazione

Alla seconda/terza domanda consecutiva la chat deve poter riprendere il contesto locale della conversazione senza doverlo ricostruire da zero.

---

## Task 1.3 — Spoiler auditor finale

### Obiettivo

Inserire un controllo post-generazione obbligatorio per il reader.

### File da toccare

- `ai_orchestrator.py`
- `llm_client.py`
- nuovo `model_routing.py`

### Implementazione operativa

1. Dopo la bozza della risposta lettore, chiamare un `SpoilerJudge`.
2. Passargli:
   - risposta bozza;
   - `cap_id`;
   - reader frontier;
   - summary sessione.
3. Se `unsafe`, riscrivere o rigenerare la risposta in modalità conservativa.
4. Loggare esito e violazioni.

### Criterio di accettazione

Risposte contenenti personaggi/eventi/causalità future vengono rigenerate automaticamente.

---

## Task 1.4 — Routing per ruolo e per agente

### Obiettivo

Preparare il backend a scegliere modelli diversi per router, retriever, answerer e guard.

### File da toccare

- `llm_client.py`
- nuovo `model_routing.py`

### Implementazione operativa

1. Introdurre `resolve_agent_model(agent_key, defaults)`.
2. Definire fallback a cascata:
   - configurazione agente;
   - default workspace;
   - env legacy.
3. Supportare questi backend target:
   - OpenAI
   - Anthropic
   - Gemini
   - OpenAI-compatible custom
   - LM Studio
   - Ollama

### Criterio di accettazione

La pipeline può assegnare il `SpoilerJudge` a un backend e il `ReaderAnswerer` a un altro senza modifiche al codice dei prompt.

---

## Task 1.5 — Logging e osservabilità minima

### Obiettivo

Capire quale agente ha fatto cosa e con quali fonti.

### File da toccare

- `ai_orchestrator.py`
- nuovo `agent_registry.py`
- nuovo schema SQLite della Fase 2 già predisposto

### Implementazione operativa

1. Loggare:
   - agente risolto;
   - provider/modello usato;
   - tool chiamati;
   - tempo di esecuzione;
   - esito del guard.
2. Preparare già la scrittura verso `chat_tool_runs` e `chat_sessions`.

### Criterio di accettazione

Ogni risposta chat ha un tracciato minimo utile per debugging e eval.
