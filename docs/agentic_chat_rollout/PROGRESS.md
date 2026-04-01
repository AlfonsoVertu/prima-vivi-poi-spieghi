# Avanzamento implementazione agentic chat

Ultimo aggiornamento: 2026-03-24

## Progresso complessivo

- **Avanzamento totale stimato: 99%**

## Stato per fase

| Fase | Stato | Avanzamento | Note sintetiche |
|---|---:|---:|---|
| Fase 1 — Hardening | Completata | 100% | Ingestione history attiva, memory snapshot persistito su SQLite (`chat_sessions`, `chat_session_memory`), boundary anti-spoiler hard introdotto sul system prompt reader, spoiler-audit attivo sia non-stream sia streaming (post-sintesi) con fallback safe e logging eventi in `chat_tool_runs`, endpoint audit e readiness go-live attivi. |
| Fase 1.5 — Runtime Multi-Role Chat | Completata | 100% | `/api/chat` ora usa pipeline multiruolo da registry quando i ruoli richiesti sono presenti: reader (`ReaderAnswerer` + `SpoilerJudge`) e author (`AuthorTaskRouter` + `AnswerSynthesizer`), con fallback automatico al flusso legacy in caso di ruoli mancanti. |
| Fase 2 — Registry/Tool/UI | Completata | 100% | Registry agenti + discovery provider + test agente disponibili, endpoint memory/spoiler-audit attivi con logging audit su `chat_tool_runs`, tool executor backend (`/api/chat/tools*`) con catalogo dettagliato e tool operativi (`list_chapters_range`, `get_recent_tool_runs`, `dry_run` mutazioni), API complete di configurazione/manutenzione (`save`, `validate`, `get`, `enable/disable`, `delete`, `export/import` per agenti/endpoints), discovery centralizzata con cache (`/api/provider-endpoints/discover`, `/api/provider-endpoints/test`, `/api/provider-endpoints/discovery-cache`), endpoint osservabilità (`/api/chat/tool-runs`) e readiness/bootstrap full (`/api/agentic/readiness`, `/api/agentic/bootstrap-full`), base test automatizzata (`tests/test_agentic_backend.py`) e mappa manutentiva dettagliata (`04_mappa_codice_operativa.md`). |
| Fase 2.0 — Tool-plan runtime integration | Completata | 100% | Tool-plan integrato nel runtime multi-role di `/api/chat`: contratti JSON per router/answerer, normalizzazione schema, esecuzione automatica con `execute_tool_plan(...)`, enforcement `tool_scope` agente, logging run su `chat_tool_runs` con `agent_id`/`session_id`, e fallback robusto in caso di output non valido. |
| Fase 3A — Foundation Vector/MCP | Completata | 100% | Modulo `vector_index_local.py` con rebuild semantic embedding, policy forcing vector retrieval nel runtime multirole (query knowledge lookup), fallback automatico a vector search quando il tool-plan non include retrieval, endpoint API `/api/vector-index/*`, bridge MCP read-only `/api/mcp/vector-search`, e provider embedding pluggabile (`VECTOR_EMBEDDING_*`). |
| Fase 3B — Hardening semantico + bridge | In corso | 95% | Completati: citazioni evidenze nel loop (`sources_used` + `include_sources`), MCP hardening enterprise (policy token scope reader/author + tenant/max_cap, rate-limit persistente SQLite, audit avanzato token/client), endpoint meta bridge (`/api/mcp/health`, `/api/mcp/capabilities`, `/api/mcp/list_vector_index_versions`), versioning indice (`active_version`, `/api/vector-index/versions`), refresh incrementale indice (`/api/vector-index/refresh`), analytics/cleanup audit MCP (`/api/mcp/audit/*`) e CRUD token MCP con rotazione (`/api/mcp/tokens*`) esposto anche in UI settings. Restano: hardening operativo finale (alerting/KPI e test E2E runtime HTTP). |

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

1. Fase 3.5: test E2E HTTP/streaming su runtime agentico + MCP bridge in ambiente con dipendenze complete.
2. Fase 3.6: alerting operativo su KPI MCP (rate-limit saturation, unauthorized spike, latency p95).
3. Fase 3.7: policy di retention automatizzata + export periodico audit.

- 2026-04-01: avviata implementazione reader-orchestrator v2 con agent config JSON, tool layer read-only e integrazione endpoint /api/chat (reader path).
- 2026-04-01: fix bloccanti PR reader v2: una sola synthesis finale, enforcement allowed_tools archivist, metadata whitelist reader-safe, validator rinominato come guard lessicale anti-spoiler/predittivo.
