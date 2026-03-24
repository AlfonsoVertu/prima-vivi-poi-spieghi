-- Foundation schema for the agentic chat rollout.
-- Draft migration for SQLite, derived from the current repository structure.

CREATE TABLE IF NOT EXISTS provider_endpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint_key TEXT NOT NULL UNIQUE,
    provider_type TEXT NOT NULL,
    label TEXT NOT NULL,
    base_url TEXT DEFAULT '',
    api_key_env TEXT DEFAULT '',
    supports_discovery INTEGER DEFAULT 1,
    is_local INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_key TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('reader','author','shared')),
    role_key TEXT NOT NULL,
    provider_type TEXT NOT NULL CHECK(provider_type IN ('openai','anthropic','gemini','openai_compatible','lmstudio','ollama')),
    endpoint_id INTEGER REFERENCES provider_endpoints(id),
    model_id TEXT NOT NULL,
    temperature REAL DEFAULT 0.2,
    max_tokens INTEGER DEFAULT 1200,
    timeout_sec INTEGER DEFAULT 90,
    enabled INTEGER DEFAULT 1,
    priority INTEGER DEFAULT 100,
    tool_scope TEXT DEFAULT '[]',
    fallback_agent_key TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_agent_prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL REFERENCES chat_agents(id) ON DELETE CASCADE,
    prompt_kind TEXT NOT NULL CHECK(prompt_kind IN ('system','task','guard','rewrite','summary')),
    prompt_text TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(agent_id, prompt_kind, version)
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key TEXT NOT NULL UNIQUE,
    mode TEXT NOT NULL CHECK(mode IN ('reader','author')),
    cap_id INTEGER,
    user_scope TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_session_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    facts_understood TEXT DEFAULT '[]',
    open_questions TEXT DEFAULT '[]',
    characters_followed TEXT DEFAULT '[]',
    themes_discussed TEXT DEFAULT '[]',
    summary_text TEXT DEFAULT '',
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id)
);

CREATE TABLE IF NOT EXISTS chat_tool_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES chat_sessions(id) ON DELETE SET NULL,
    agent_id INTEGER REFERENCES chat_agents(id) ON DELETE SET NULL,
    tool_name TEXT NOT NULL,
    arguments_json TEXT DEFAULT '{}',
    result_json TEXT DEFAULT '{}',
    status TEXT NOT NULL CHECK(status IN ('ok','error','blocked')),
    duration_ms INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS provider_discovery_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint_id INTEGER NOT NULL REFERENCES provider_endpoints(id) ON DELETE CASCADE,
    models_json TEXT DEFAULT '[]',
    discovered_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(endpoint_id)
);

CREATE TABLE IF NOT EXISTS mcp_bridge_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id TEXT NOT NULL UNIQUE,
    token_hash TEXT NOT NULL UNIQUE,
    label TEXT DEFAULT '',
    tenant_id TEXT DEFAULT 'default',
    scope TEXT NOT NULL DEFAULT 'both' CHECK(scope IN ('reader','author','both')),
    max_cap_id INTEGER,
    rate_limit_per_minute INTEGER NOT NULL DEFAULT 60,
    enabled INTEGER NOT NULL DEFAULT 1,
    policy_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mcp_bridge_rate_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id TEXT NOT NULL,
    client_key TEXT NOT NULL,
    window_minute INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(token_id, client_key, window_minute)
);

CREATE TABLE IF NOT EXISTS mcp_bridge_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id TEXT DEFAULT '',
    tenant_id TEXT DEFAULT '',
    client_key TEXT DEFAULT '',
    endpoint TEXT NOT NULL,
    mode TEXT DEFAULT '',
    cap_id INTEGER,
    query_len INTEGER DEFAULT 0,
    k INTEGER,
    min_score REAL,
    status TEXT NOT NULL,
    result_count INTEGER DEFAULT 0,
    error_message TEXT DEFAULT '',
    latency_ms INTEGER DEFAULT 0,
    meta_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
