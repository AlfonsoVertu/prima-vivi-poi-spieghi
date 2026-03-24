# Avanzamento implementazione agentic chat

Ultimo aggiornamento: 2026-03-24

## Progresso complessivo

- **Avanzamento totale stimato: 94%**

## Stato per fase

| Fase | Stato | Avanzamento | Note sintetiche |
|---|---:|---:|---|
| Fase 1 — Hardening | Completata | 100% | Ingestione history attiva, memory snapshot persistito su SQLite (`chat_sessions`, `chat_session_memory`), boundary anti-spoiler hard introdotto sul system prompt reader, spoiler-audit attivo sia non-stream sia streaming (post-sintesi) con fallback safe e logging eventi in `chat_tool_runs`, endpoint audit e readiness go-live attivi. |
| Fase 2 — Registry/Tool/UI | Completata | 100% | Registry agenti + discovery provider + test agente disponibili, endpoint memory/spoiler-audit attivi con logging audit su `chat_tool_runs`, tool executor backend (`/api/chat/tools*`) con catalogo dettagliato e tool operativi (`list_chapters_range`, `get_recent_tool_runs`, `dry_run` mutazioni), API complete di configurazione/manutenzione (`save`, `validate`, `get`, `enable/disable`, `delete`, `export/import` per agenti/endpoints), discovery centralizzata con cache (`/api/provider-endpoints/discover`, `/api/provider-endpoints/test`, `/api/provider-endpoints/discovery-cache`), endpoint osservabilità (`/api/chat/tool-runs`) e readiness/bootstrap full (`/api/agentic/readiness`, `/api/agentic/bootstrap-full`), con base test automatizzata (`tests/test_agentic_backend.py`). |
| Fase 3 — Vector DB/MCP | Non iniziata | 0% | Pianificazione pronta, nessun builder/indice operativo ancora integrato. |

## Milestone completate

- Schema e seed base registry agenti/provider.
- Discovery/test per LM Studio, Ollama, OpenAI-compatible.
- Endpoint backend per listing/bootstrap/test agenti.
- Routing chat con risoluzione per ruolo dal registry.
- Ingestione history recente nella chat API.
- Endpoint dedicato `/api/chat/spoiler-audit` per validazione/riscrittura safety lato reader.
- Audit spoiler anche nel path streaming con riformulazione safe post-sintesi.
- Logging eventi spoiler-audit in `chat_tool_runs`.
- Tool executor backend iniziale (`/api/chat/tools`, `/api/chat/tools/execute`).
- API save per agenti ed endpoint provider.
- Rimozione canone completo dal system prompt reader nei due percorsi principali (`run_deep_context_pipeline` e orchestratore streaming).

## Prossimi 3 task consigliati

1. Implementare `SpoilerJudge` post-generazione con rigenerazione automatica se `unsafe`.
2. Persistenza `chat_sessions` + `chat_session_memory` con summary strutturato.
3. Primo `chat_tools.py` (read-only) e routing task autore su tool.
