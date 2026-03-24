# Agentic chat rollout operativo

Questa cartella traduce il piano architetturale in artefatti operativi, eseguibili a step, specifici per questo repository.

## Obiettivo

Portare il progetto da pipeline chat monolitica a sistema agentico configurabile da pannello, con:

- separazione hard tra chat lettore e chat autore;
- tool-calling reale sulla base dati e sulle API funzionali;
- scelta per-agente di provider, modello e prompt;
- supporto target per cloud, endpoint OpenAI-compatible custom, LM Studio e Ollama;
- preparazione del layer locale per vector DB e interoperabilità MCP.

## Base dati attuale verificata

La pianificazione seguente è stata costruita osservando davvero il database `roman.db`.

Tabelle già presenti e riusabili:

- `capitoli`
- `timeline`
- `personaggi`
- `personaggi_capitoli`
- `validation_prompts`

Queste tabelle coprono già la maggior parte del retrieval strutturato necessario a Fase 1 e Fase 2.

## Stato avanzamento del repository

Questa cartella ora non è più solo pianificazione: nel codice sono già stati introdotti i primi mattoni di foundation per la Fase 2.

Implementato finora:

- `agent_registry.py` con schema runtime e seed di agenti/endpoints di default;
- `provider_discovery.py` con discovery/test per LM Studio, Ollama e OpenAI-compatible;
- endpoint Flask `/api/agents`, `/api/agents/bootstrap`, `/api/agents/save`, `/api/agents/validate`, `/api/agents/export`, `/api/agents/import`, `/api/agents/<agent_key>`, `/api/agents/<agent_key>/enabled`, `/api/provider-endpoints/save`, `/api/provider-endpoints/<endpoint_key>`, `/api/provider-endpoints/discover`, `/api/provider-endpoints/test`, `/api/provider-endpoints/discovery-cache`, `/api/agentic/readiness`, `/api/agentic/bootstrap-full`, `/api/agents/test`, `/api/ollama/discover`, `/api/ollama/test`, `/api/openai-compatible/discover`, `/api/openai-compatible/test`, `/api/chat/memory`, `/api/chat/spoiler-audit`, `/api/chat/tools` (anche `detailed=1`), `/api/chat/tools/execute`, `/api/chat/tool-runs` e uso di `history` + memory snapshot persistito nella chat API con logging safety/tool su `chat_tool_runs`.
- test smoke automatizzati iniziali in `tests/test_agentic_backend.py` per registry + tool executor.

## File operativi inclusi

- `01_fase1_hardening_operativo.md`
- `02_fase2_registry_tool_ui.md`
- `03_fase3_vector_db_mcp.md`
- `PROGRESS.md` (avanzamento percentuale aggiornato)
- `sqlite/001_agentic_chat_foundation.sql`
- `sqlite/002_agentic_chat_indexes.sql`

## Ordine consigliato di esecuzione

1. Eseguire Fase 1 per blindare spoiler, memoria e routing.
2. Introdurre registry agenti, provider discovery e tool execution della Fase 2.
3. Solo dopo stabilizzare indicizzazione locale, vector DB e MCP nella Fase 3.

## Regola pratica

Ogni task riportato nei file di questa cartella deve produrre, a chiusura dello step:

- file toccati;
- test minimi;
- criterio di accettazione;
- aggiornamento documentazione.
