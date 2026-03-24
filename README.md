# Prima Vivi Poi Spieghi

Applicazione web Flask per la scrittura, revisione e gestione del romanzo corale *Prima Vivi Poi Spieghi*.

## Struttura del Progetto

```
prima-vivi-poi-spieghi/
├── app.py                  # Server Flask principale
├── llm_client.py           # Client AI multi-provider (OpenAI, Anthropic, Gemini)
├── ai_queue.py             # Coda per le generazioni AI
├── compila_iterativo.py    # Builder dei prompt per l'AI
├── roman.db                # Database SQLite (capitoli, personaggi, timeline)
├── prompts.json            # Prompt di sistema per l'AI
├── ui_settings.json        # Impostazioni UI
├── CANONE_DEFINITIVO.md    # Canon del romanzo (usato come contesto AI)
├── CANONE_AGGIORNATO.md    # Canon aggiornato
├── capitoli/               # Testi dei 66 capitoli (cap01.txt - cap66.txt)
└── docs/                   # Documentazione del progetto
```

## Avvio

```bash
# 1. Crea il file .env con le chiavi API
cp .env.example .env  # oppure crealo manualmente

# 2. Installa le dipendenze
pip install flask python-dotenv requests

# 3. Avvia il server
python app.py
```

L'applicazione sarà disponibile su `http://localhost:5000`.

## Funzionalità

- **Dashboard Admin**: gestione capitoli, metadati, timeline e personaggi
- **Editor Testo**: scrittura e revisione con analisi AI on-save
- **Generazione AI**: generazione automatica di metadati (titolo, POV, riassunti)
- **Chat AI**: assistente contestuale per l'autore e per il lettore
- **Timeline**: gestione degli archi temporali del romanzo
- **Personaggi**: schede complete con tracking presenza per capitolo

## Architettura chat attuale

- **Endpoint unificato**: `/api/chat/<cap_id>` gestisce sia la chat lettore sia la chat autore tramite `admin_mode`.
- **Pipeline di contesto**: il backend assembla metadati capitolo, riassunti, timeline e porzioni di testo per costruire il contesto AI.
- **Orchestrazione agentica**: `ai_orchestrator.py` coordina sottoruoli paralleli per metadati, riassunti e testo profondo prima della sintesi finale.
- **Supporto locale**: il progetto include integrazione LM Studio via endpoint OpenAI-compatible e discovery dei modelli caricati.
- **Gap documentato**: il piano di evoluzione prevede la configurazione di provider/modello per singolo agente, inclusi cloud, endpoint OpenAI-compatible custom, LM Studio e Ollama.

## Roadmap documentata per il potenziamento agentico

È disponibile un piano tecnico dedicato in `docs/D_piano_implementazione_chat_agentica_locale.md`, focalizzato su:

- separazione hard tra conoscenza lettore e conoscenza totale dell'opera;
- tool backend per analisi, revisione, riscrittura e rigenerazione metadati dalla chat autore;
- orchestrazione locale-first con modelli specializzati via LM Studio;
- configurazione da pannello di agenti con prompt, provider e modello per ruolo;
- supporto target per cloud, OpenAI-compatible custom, LM Studio e Ollama con discovery;
- pacchetto operativo di rollout in `docs/agentic_chat_rollout/` con task, step, bozze SQL e tracker percentuale `PROGRESS.md`;
- foundation code già aggiunta per registry agenti, test/validazione agente, discovery provider e ingestione history chat (`/api/agents`, `/api/agents/bootstrap`, `/api/agents/save`, `/api/agents/validate`, `/api/agents/export`, `/api/agents/import`, `/api/agents/<agent_key>`, `/api/agents/<agent_key>/enabled`, `/api/provider-endpoints/save`, `/api/provider-endpoints/<endpoint_key>`, `/api/provider-endpoints/discover`, `/api/provider-endpoints/test`, `/api/provider-endpoints/discovery-cache`, `/api/agentic/readiness`, `/api/agentic/bootstrap-full`, `/api/agents/test`, `/api/ollama/*`, `/api/openai-compatible/*`, `/api/chat/memory`, `/api/chat/spoiler-audit`, `/api/chat/tools*` con opzione `detailed=1`) con enforcement safety anche sul percorso streaming e logging audit su `chat_tool_runs`;
- preparazione di un vector DB locale dell'opera interrogabile anche da un server MCP esterno.

Avanzamento operativo corrente: vedi `docs/agentic_chat_rollout/PROGRESS.md` (aggiornato in percentuale).
Per smoke test backend agentico è disponibile anche `tests/test_agentic_backend.py`.
Fase 3 (Vector/MCP) può essere avviata dopo il go-live: Fase 1+2 ora coprono la partenza operativa del progetto.
Per manutenzione evolutiva, leggere `docs/agentic_chat_rollout/04_mappa_codice_operativa.md` (mappa completa endpoint→codice→controlli).

## Variabili d'Ambiente (.env)

```
ADMIN_USER=<utente>
ADMIN_PASS=<password>
OPENAI_API_KEY=<chiave>
CLAUDE_API_KEY=<chiave Anthropic>
GEMINI_API_KEY=<chiave Google>
LMSTUDIO_URL=<endpoint OpenAI-compatible locale>
LMSTUDIO_API_KEY=<opzionale>
LLM_PROVIDER=<openai|anthropic|google|lmstudio>
ADMIN_CHAT_MODEL=<modello locale legacy o override>
OLLAMA_URL=<endpoint locale Ollama, roadmap target>
OPENAI_COMPATIBLE_URL=<endpoint custom OpenAI-compatible, roadmap target>
OPENAI_COMPATIBLE_API_KEY=<chiave endpoint custom, roadmap target>
```

> Nota: il codice usa già `CLAUDE_API_KEY`, `GEMINI_API_KEY`, `LMSTUDIO_URL`, `LMSTUDIO_API_KEY`, `OLLAMA_URL`, `OPENAI_COMPATIBLE_URL` e `OPENAI_COMPATIBLE_API_KEY`. La copertura è foundation-level (discovery/test/registry + chiamata provider), mentre la piena orchestrazione agentica per ruolo resta in roadmap.

## Licenza

Progetto privato — tutti i diritti riservati.
