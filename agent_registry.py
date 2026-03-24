import json
import re
import sqlite3
from typing import Any, Dict, List, Optional

SCHEMA_STATEMENTS = [
    """
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
    )
    """,
    """
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_agent_prompts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id INTEGER NOT NULL REFERENCES chat_agents(id) ON DELETE CASCADE,
        prompt_kind TEXT NOT NULL CHECK(prompt_kind IN ('system','task','guard','rewrite','summary')),
        prompt_text TEXT NOT NULL,
        version INTEGER DEFAULT 1,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(agent_id, prompt_kind, version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_key TEXT NOT NULL UNIQUE,
        mode TEXT NOT NULL CHECK(mode IN ('reader','author')),
        cap_id INTEGER,
        user_scope TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
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
    )
    """,
    """
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS provider_discovery_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        endpoint_id INTEGER NOT NULL REFERENCES provider_endpoints(id) ON DELETE CASCADE,
        models_json TEXT DEFAULT '[]',
        discovered_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(endpoint_id)
    )
    """,
    """
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mcp_bridge_rate_limits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token_id TEXT NOT NULL,
        client_key TEXT NOT NULL,
        window_minute INTEGER NOT NULL,
        count INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(token_id, client_key, window_minute)
    )
    """,
    """
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
    )
    """,
]

INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_chat_agents_mode_enabled_priority ON chat_agents(mode, enabled, priority)",
    "CREATE INDEX IF NOT EXISTS idx_chat_agents_role_key ON chat_agents(role_key)",
    "CREATE INDEX IF NOT EXISTS idx_chat_agent_prompts_agent_kind ON chat_agent_prompts(agent_id, prompt_kind, version DESC)",
    "CREATE INDEX IF NOT EXISTS idx_chat_sessions_mode_cap ON chat_sessions(mode, cap_id)",
    "CREATE INDEX IF NOT EXISTS idx_chat_tool_runs_session_created ON chat_tool_runs(session_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_provider_discovery_cache_endpoint ON provider_discovery_cache(endpoint_id)",
    "CREATE INDEX IF NOT EXISTS idx_mcp_bridge_tokens_enabled_scope ON mcp_bridge_tokens(enabled, scope)",
    "CREATE INDEX IF NOT EXISTS idx_mcp_bridge_rate_limits_lookup ON mcp_bridge_rate_limits(token_id, client_key, window_minute)",
    "CREATE INDEX IF NOT EXISTS idx_mcp_bridge_audit_created ON mcp_bridge_audit(created_at DESC)",
]

DEFAULT_ENDPOINTS = [
    {
        "endpoint_key": "openai-default",
        "provider_type": "openai",
        "label": "OpenAI Cloud",
        "base_url": "https://api.openai.com",
        "api_key_env": "OPENAI_API_KEY",
        "supports_discovery": 0,
        "is_local": 0,
    },
    {
        "endpoint_key": "anthropic-default",
        "provider_type": "anthropic",
        "label": "Anthropic Cloud",
        "base_url": "https://api.anthropic.com",
        "api_key_env": "CLAUDE_API_KEY",
        "supports_discovery": 0,
        "is_local": 0,
    },
    {
        "endpoint_key": "gemini-default",
        "provider_type": "gemini",
        "label": "Gemini Cloud",
        "base_url": "https://generativelanguage.googleapis.com",
        "api_key_env": "GEMINI_API_KEY",
        "supports_discovery": 0,
        "is_local": 0,
    },
    {
        "endpoint_key": "lmstudio-default",
        "provider_type": "lmstudio",
        "label": "LM Studio Locale",
        "base_url": "http://127.0.0.1:1234",
        "api_key_env": "LMSTUDIO_API_KEY",
        "supports_discovery": 1,
        "is_local": 1,
    },
    {
        "endpoint_key": "ollama-default",
        "provider_type": "ollama",
        "label": "Ollama Locale",
        "base_url": "http://127.0.0.1:11434",
        "api_key_env": "",
        "supports_discovery": 1,
        "is_local": 1,
    },
    {
        "endpoint_key": "openai-compatible-default",
        "provider_type": "openai_compatible",
        "label": "Endpoint OpenAI-compatible",
        "base_url": "",
        "api_key_env": "OPENAI_COMPATIBLE_API_KEY",
        "supports_discovery": 1,
        "is_local": 0,
    },
]

DEFAULT_AGENTS = [
    {
        "agent_key": "reader_answerer_default",
        "label": "Reader Answerer",
        "mode": "reader",
        "role_key": "ReaderAnswerer",
        "provider_type": "lmstudio",
        "endpoint_key": "lmstudio-default",
        "model_id": "custom",
        "temperature": 0.4,
        "max_tokens": 1600,
        "timeout_sec": 90,
        "priority": 100,
        "tool_scope": "[]",
        "prompts": {
            "system": "Rispondi al lettore senza spoiler e con tono chiaro.",
            "task": "Produci la risposta finale reader grounded sul contesto consentito.",
        },
    },
    {
        "agent_key": "reader_spoiler_judge_default",
        "label": "Reader Spoiler Judge",
        "mode": "reader",
        "role_key": "SpoilerJudge",
        "provider_type": "lmstudio",
        "endpoint_key": "lmstudio-default",
        "model_id": "custom",
        "temperature": 0.1,
        "max_tokens": 700,
        "timeout_sec": 60,
        "priority": 110,
        "tool_scope": "[]",
        "prompts": {
            "guard": "Valuta se la risposta contiene spoiler rispetto a cap_id e contesto consentito.",
        },
    },
    {
        "agent_key": "author_task_router_default",
        "label": "Author Task Router",
        "mode": "author",
        "role_key": "AuthorTaskRouter",
        "provider_type": "openai_compatible",
        "endpoint_key": "openai-compatible-default",
        "model_id": "custom",
        "temperature": 0.1,
        "max_tokens": 800,
        "timeout_sec": 60,
        "priority": 100,
        "tool_scope": "[]",
        "prompts": {
            "system": "Classifica il task autore e proponi tool/contesto necessari.",
            "task": "Restituisci un JSON di routing del task autore.",
        },
    },
    {
        "agent_key": "author_answer_synth_default",
        "label": "Author Answer Synthesizer",
        "mode": "author",
        "role_key": "AnswerSynthesizer",
        "provider_type": "anthropic",
        "endpoint_key": "anthropic-default",
        "model_id": "claude-3-7-sonnet-20250219",
        "temperature": 0.3,
        "max_tokens": 1800,
        "timeout_sec": 90,
        "priority": 120,
        "tool_scope": "[]",
        "prompts": {
            "system": "Sintetizza una risposta grounded per l'autore.",
            "summary": "Usa tool output e retrieval per rispondere in modo operativo e coerente.",
        },
    },
]

ALLOWED_PROVIDER_TYPES = {"openai", "anthropic", "gemini", "openai_compatible", "lmstudio", "ollama"}
ALLOWED_MODES = {"reader", "author", "shared"}
ALLOWED_PROMPT_KINDS = {"system", "task", "guard", "rewrite", "summary"}
ENDPOINT_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
AGENT_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


def ensure_schema(conn: sqlite3.Connection) -> None:
    for stmt in SCHEMA_STATEMENTS:
        conn.execute(stmt)
    for stmt in INDEX_STATEMENTS:
        conn.execute(stmt)
    conn.commit()


def _fetchone_dict(conn: sqlite3.Connection, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    row = conn.execute(query, params).fetchone()
    return dict(row) if row else None


def _validate_tool_scope(tool_scope: Any) -> str:
    if isinstance(tool_scope, str):
        try:
            parsed = json.loads(tool_scope or "[]")
        except Exception:
            parsed = []
    elif isinstance(tool_scope, (list, tuple)):
        parsed = list(tool_scope)
    else:
        parsed = []

    clean = []
    for name in parsed:
        sval = str(name).strip()
        if sval:
            clean.append(sval)
    return json.dumps(clean, ensure_ascii=False)


def get_endpoint(conn: sqlite3.Connection, endpoint_key: str) -> Optional[Dict[str, Any]]:
    ensure_schema(conn)
    key = (endpoint_key or "").strip()
    if not key:
        return None
    row = _fetchone_dict(conn, "SELECT * FROM provider_endpoints WHERE endpoint_key=?", (key,))
    if not row:
        return None
    usage = conn.execute("SELECT COUNT(*) AS n FROM chat_agents WHERE endpoint_id=?", (row["id"],)).fetchone()
    row["agents_count"] = int(usage["n"]) if usage else 0
    return row


def seed_defaults(conn: sqlite3.Connection) -> Dict[str, int]:
    ensure_schema(conn)
    inserted_endpoints = 0
    inserted_agents = 0

    for endpoint in DEFAULT_ENDPOINTS:
        existing = conn.execute(
            "SELECT id FROM provider_endpoints WHERE endpoint_key=?",
            (endpoint["endpoint_key"],),
        ).fetchone()
        if existing:
            continue
        conn.execute(
            """
            INSERT INTO provider_endpoints
            (endpoint_key, provider_type, label, base_url, api_key_env, supports_discovery, is_local, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                endpoint["endpoint_key"], endpoint["provider_type"], endpoint["label"], endpoint["base_url"],
                endpoint["api_key_env"], endpoint["supports_discovery"], endpoint["is_local"],
            ),
        )
        inserted_endpoints += 1

    for agent in DEFAULT_AGENTS:
        existing = conn.execute(
            "SELECT id FROM chat_agents WHERE agent_key=?",
            (agent["agent_key"],),
        ).fetchone()
        if existing:
            continue
        endpoint = conn.execute(
            "SELECT id FROM provider_endpoints WHERE endpoint_key=?",
            (agent["endpoint_key"],),
        ).fetchone()
        endpoint_id = endpoint[0] if endpoint else None
        cur = conn.execute(
            """
            INSERT INTO chat_agents
            (agent_key, label, mode, role_key, provider_type, endpoint_id, model_id, temperature, max_tokens,
             timeout_sec, enabled, priority, tool_scope, fallback_agent_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, '')
            """,
            (
                agent["agent_key"], agent["label"], agent["mode"], agent["role_key"], agent["provider_type"],
                endpoint_id, agent["model_id"], agent["temperature"], agent["max_tokens"], agent["timeout_sec"],
                agent["priority"], agent["tool_scope"],
            ),
        )
        agent_id = cur.lastrowid
        for prompt_kind, prompt_text in agent.get("prompts", {}).items():
            conn.execute(
                "INSERT INTO chat_agent_prompts (agent_id, prompt_kind, prompt_text, version) VALUES (?, ?, ?, 1)",
                (agent_id, prompt_kind, prompt_text),
            )
        inserted_agents += 1

    conn.commit()
    return {"inserted_endpoints": inserted_endpoints, "inserted_agents": inserted_agents}


def list_endpoints(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    ensure_schema(conn)
    rows = conn.execute("SELECT * FROM provider_endpoints ORDER BY provider_type, label").fetchall()
    return [dict(r) for r in rows]


def list_agents(conn: sqlite3.Connection, mode: Optional[str] = None) -> List[Dict[str, Any]]:
    ensure_schema(conn)
    params: List[Any] = []
    query = (
        "SELECT a.*, e.endpoint_key, e.label AS endpoint_label, e.base_url, e.api_key_env "
        "FROM chat_agents a LEFT JOIN provider_endpoints e ON e.id = a.endpoint_id"
    )
    if mode:
        query += " WHERE a.mode = ?"
        params.append(mode)
    query += " ORDER BY a.mode, a.priority, a.label"
    rows = conn.execute(query, tuple(params)).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        prompt_rows = conn.execute(
            "SELECT prompt_kind, prompt_text, version, updated_at FROM chat_agent_prompts WHERE agent_id=? ORDER BY prompt_kind, version DESC",
            (item["id"],),
        ).fetchall()
        item["prompts"] = [dict(p) for p in prompt_rows]
        results.append(item)
    return results


def get_agent(conn: sqlite3.Connection, agent_key: str) -> Optional[Dict[str, Any]]:
    ensure_schema(conn)
    row = _fetchone_dict(conn, "SELECT * FROM chat_agents WHERE agent_key=?", (agent_key,))
    if not row:
        return None
    prompts = conn.execute(
        "SELECT prompt_kind, prompt_text, version, updated_at FROM chat_agent_prompts WHERE agent_id=? ORDER BY prompt_kind, version DESC",
        (row["id"],),
    ).fetchall()
    row["prompts"] = [dict(p) for p in prompts]
    return row


def resolve_agent_for_role(conn: sqlite3.Connection, mode: str, role_key: str) -> Optional[Dict[str, Any]]:
    ensure_schema(conn)
    row = conn.execute(
        """
        SELECT a.*, e.endpoint_key, e.base_url, e.api_key_env
        FROM chat_agents a
        LEFT JOIN provider_endpoints e ON e.id = a.endpoint_id
        WHERE a.enabled=1 AND a.mode=? AND a.role_key=?
        ORDER BY a.priority ASC, a.id ASC
        LIMIT 1
        """,
        (mode, role_key),
    ).fetchone()
    if not row:
        return None
    agent = dict(row)
    prompts = conn.execute(
        "SELECT prompt_kind, prompt_text, version FROM chat_agent_prompts WHERE agent_id=? ORDER BY prompt_kind, version DESC",
        (agent["id"],),
    ).fetchall()
    agent["prompts"] = [dict(p) for p in prompts]
    return agent


def upsert_provider_endpoint(conn: sqlite3.Connection, payload: Dict[str, Any]) -> Dict[str, Any]:
    ensure_schema(conn)
    endpoint_key = (payload.get("endpoint_key") or "").strip()
    provider_type = (payload.get("provider_type") or "").strip()
    label = (payload.get("label") or "").strip()
    if not endpoint_key or not provider_type or not label:
        return {"ok": False, "error": "endpoint_key, provider_type e label sono obbligatori"}
    if not ENDPOINT_KEY_RE.match(endpoint_key):
        return {"ok": False, "error": "endpoint_key non valido (usa minuscole, numeri, ., _, -)"}
    if provider_type not in ALLOWED_PROVIDER_TYPES:
        return {"ok": False, "error": f"provider_type non supportato: {provider_type}"}

    base_url = (payload.get("base_url") or "").strip()
    api_key_env = (payload.get("api_key_env") or "").strip()
    supports_discovery = 1 if payload.get("supports_discovery", True) else 0
    is_local = 1 if payload.get("is_local", False) else 0
    enabled = 1 if payload.get("enabled", True) else 0

    existing = conn.execute("SELECT id FROM provider_endpoints WHERE endpoint_key=?", (endpoint_key,)).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE provider_endpoints
            SET provider_type=?, label=?, base_url=?, api_key_env=?, supports_discovery=?, is_local=?, enabled=?, updated_at=CURRENT_TIMESTAMP
            WHERE endpoint_key=?
            """,
            (provider_type, label, base_url, api_key_env, supports_discovery, is_local, enabled, endpoint_key),
        )
    else:
        conn.execute(
            """
            INSERT INTO provider_endpoints
            (endpoint_key, provider_type, label, base_url, api_key_env, supports_discovery, is_local, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (endpoint_key, provider_type, label, base_url, api_key_env, supports_discovery, is_local, enabled),
        )
    conn.commit()
    row = get_endpoint(conn, endpoint_key)
    return {"ok": True, "endpoint": row}


def upsert_agent(conn: sqlite3.Connection, payload: Dict[str, Any]) -> Dict[str, Any]:
    ensure_schema(conn)
    agent_key = (payload.get("agent_key") or "").strip()
    label = (payload.get("label") or "").strip()
    mode = (payload.get("mode") or "").strip()
    role_key = (payload.get("role_key") or "").strip()
    provider_type = (payload.get("provider_type") or "").strip()
    model_id = (payload.get("model_id") or "").strip()
    endpoint_key = (payload.get("endpoint_key") or "").strip()
    prompts = payload.get("prompts") or {}

    if not all([agent_key, label, mode, role_key, provider_type, model_id]):
        return {"ok": False, "error": "Campi obbligatori mancanti per l'agente"}
    if not AGENT_KEY_RE.match(agent_key):
        return {"ok": False, "error": "agent_key non valido (usa minuscole, numeri, ., _, -)"}
    if mode not in ALLOWED_MODES:
        return {"ok": False, "error": f"mode non valido: {mode}"}
    if provider_type not in ALLOWED_PROVIDER_TYPES:
        return {"ok": False, "error": f"provider_type non supportato: {provider_type}"}

    endpoint_id = None
    if endpoint_key:
        row_ep = conn.execute("SELECT id FROM provider_endpoints WHERE endpoint_key=?", (endpoint_key,)).fetchone()
        if not row_ep:
            return {"ok": False, "error": f"endpoint_key non trovato: {endpoint_key}"}
        endpoint_id = row_ep["id"]

    temperature = float(payload.get("temperature", 0.2))
    max_tokens = int(payload.get("max_tokens", 1200))
    timeout_sec = int(payload.get("timeout_sec", 90))
    enabled = 1 if payload.get("enabled", True) else 0
    priority = int(payload.get("priority", 100))
    tool_scope = _validate_tool_scope(payload.get("tool_scope", "[]"))
    fallback_agent_key = (payload.get("fallback_agent_key") or "").strip()

    existing = conn.execute("SELECT id FROM chat_agents WHERE agent_key=?", (agent_key,)).fetchone()
    if existing:
        agent_id = existing["id"]
        conn.execute(
            """
            UPDATE chat_agents
            SET label=?, mode=?, role_key=?, provider_type=?, endpoint_id=?, model_id=?, temperature=?, max_tokens=?, timeout_sec=?, enabled=?, priority=?, tool_scope=?, fallback_agent_key=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                label, mode, role_key, provider_type, endpoint_id, model_id, temperature, max_tokens, timeout_sec,
                enabled, priority, tool_scope, fallback_agent_key, agent_id
            ),
        )
    else:
        cur = conn.execute(
            """
            INSERT INTO chat_agents
            (agent_key, label, mode, role_key, provider_type, endpoint_id, model_id, temperature, max_tokens, timeout_sec, enabled, priority, tool_scope, fallback_agent_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent_key, label, mode, role_key, provider_type, endpoint_id, model_id, temperature, max_tokens,
                timeout_sec, enabled, priority, tool_scope, fallback_agent_key
            ),
        )
        agent_id = cur.lastrowid

    if isinstance(prompts, dict) and prompts:
        for prompt_kind, prompt_text in prompts.items():
            if str(prompt_kind) not in ALLOWED_PROMPT_KINDS:
                continue
            if not str(prompt_text).strip():
                continue
            top = conn.execute(
                "SELECT COALESCE(MAX(version), 0) AS max_v FROM chat_agent_prompts WHERE agent_id=? AND prompt_kind=?",
                (agent_id, str(prompt_kind)),
            ).fetchone()
            next_version = int(top["max_v"]) + 1
            conn.execute(
                "INSERT INTO chat_agent_prompts (agent_id, prompt_kind, prompt_text, version) VALUES (?, ?, ?, ?)",
                (agent_id, str(prompt_kind), str(prompt_text), next_version),
            )

    conn.commit()
    agent = get_agent(conn, agent_key)
    return {"ok": True, "agent": agent}


def set_agent_enabled(conn: sqlite3.Connection, agent_key: str, enabled: bool) -> Dict[str, Any]:
    ensure_schema(conn)
    key = (agent_key or "").strip()
    if not key:
        return {"ok": False, "error": "agent_key mancante"}
    row = conn.execute("SELECT id FROM chat_agents WHERE agent_key=?", (key,)).fetchone()
    if not row:
        return {"ok": False, "error": "agente non trovato"}
    conn.execute(
        "UPDATE chat_agents SET enabled=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (1 if enabled else 0, row["id"]),
    )
    conn.commit()
    return {"ok": True, "agent": get_agent(conn, key)}


def delete_agent(conn: sqlite3.Connection, agent_key: str) -> Dict[str, Any]:
    ensure_schema(conn)
    key = (agent_key or "").strip()
    if not key:
        return {"ok": False, "error": "agent_key mancante"}
    row = conn.execute("SELECT id FROM chat_agents WHERE agent_key=?", (key,)).fetchone()
    if not row:
        return {"ok": False, "error": "agente non trovato"}
    conn.execute("DELETE FROM chat_agent_prompts WHERE agent_id=?", (row["id"],))
    conn.execute("DELETE FROM chat_agents WHERE id=?", (row["id"],))
    conn.commit()
    return {"ok": True, "deleted_agent_key": key}


def delete_provider_endpoint(conn: sqlite3.Connection, endpoint_key: str) -> Dict[str, Any]:
    ensure_schema(conn)
    key = (endpoint_key or "").strip()
    if not key:
        return {"ok": False, "error": "endpoint_key mancante"}
    row = conn.execute("SELECT id FROM provider_endpoints WHERE endpoint_key=?", (key,)).fetchone()
    if not row:
        return {"ok": False, "error": "endpoint non trovato"}
    used = conn.execute("SELECT agent_key FROM chat_agents WHERE endpoint_id=? ORDER BY agent_key", (row["id"],)).fetchall()
    if used:
        return {
            "ok": False,
            "error": "endpoint in uso da agenti",
            "agents": [u["agent_key"] for u in used],
        }
    conn.execute("DELETE FROM provider_endpoints WHERE id=?", (row["id"],))
    conn.commit()
    return {"ok": True, "deleted_endpoint_key": key}


def validate_agent_configuration(conn: sqlite3.Connection, mode: Optional[str] = None) -> Dict[str, Any]:
    ensure_schema(conn)
    problems: List[Dict[str, Any]] = []
    agents = list_agents(conn, mode=mode)
    for a in agents:
        if a.get("enabled") != 1:
            continue
        if not a.get("model_id"):
            problems.append({"level": "error", "agent_key": a.get("agent_key"), "message": "model_id mancante"})
        if not a.get("endpoint_id") and a.get("provider_type") in {"lmstudio", "ollama", "openai_compatible"}:
            problems.append(
                {"level": "warning", "agent_key": a.get("agent_key"), "message": "endpoint mancante per provider locale/custom"}
            )
        prompts = a.get("prompts") or []
        if not prompts:
            problems.append({"level": "warning", "agent_key": a.get("agent_key"), "message": "nessun prompt configurato"})
    return {"ok": True, "mode": mode, "problems": problems, "has_errors": any(p["level"] == "error" for p in problems)}


def export_registry_bundle(conn: sqlite3.Connection, mode: Optional[str] = None) -> Dict[str, Any]:
    ensure_schema(conn)
    endpoints = list_endpoints(conn)
    agents = list_agents(conn, mode=mode)
    payload = {
        "schema_version": 1,
        "mode_filter": mode,
        "exported_at": conn.execute("SELECT CURRENT_TIMESTAMP AS ts").fetchone()["ts"],
        "endpoints": endpoints,
        "agents": agents,
    }
    return {"ok": True, "bundle": payload}


def import_registry_bundle(
    conn: sqlite3.Connection,
    bundle: Dict[str, Any],
    overwrite: bool = False,
    import_disabled: bool = True,
) -> Dict[str, Any]:
    ensure_schema(conn)
    if not isinstance(bundle, dict):
        return {"ok": False, "error": "bundle non valido"}

    endpoints = bundle.get("endpoints") or []
    agents = bundle.get("agents") or []
    if not isinstance(endpoints, list) or not isinstance(agents, list):
        return {"ok": False, "error": "bundle malformato: endpoints/agents devono essere liste"}

    inserted_endpoints = 0
    updated_endpoints = 0
    inserted_agents = 0
    updated_agents = 0
    skipped_agents = 0
    errors: List[str] = []

    for raw in endpoints:
        if not isinstance(raw, dict):
            errors.append("endpoint non dict ignorato")
            continue
        payload = {
            "endpoint_key": raw.get("endpoint_key"),
            "provider_type": raw.get("provider_type"),
            "label": raw.get("label"),
            "base_url": raw.get("base_url", ""),
            "api_key_env": raw.get("api_key_env", ""),
            "supports_discovery": bool(raw.get("supports_discovery", True)),
            "is_local": bool(raw.get("is_local", False)),
            "enabled": bool(raw.get("enabled", True) if import_disabled else True),
        }
        exists = conn.execute("SELECT id FROM provider_endpoints WHERE endpoint_key=?", ((payload.get("endpoint_key") or "").strip(),)).fetchone()
        if exists and not overwrite:
            continue
        res = upsert_provider_endpoint(conn, payload)
        if not res.get("ok"):
            errors.append(f"endpoint {payload.get('endpoint_key')}: {res.get('error')}")
            continue
        if exists:
            updated_endpoints += 1
        else:
            inserted_endpoints += 1

    for raw in agents:
        if not isinstance(raw, dict):
            errors.append("agent non dict ignorato")
            continue
        prompts = {}
        for p in (raw.get("prompts") or []):
            if isinstance(p, dict) and p.get("prompt_kind") and p.get("prompt_text"):
                kind = str(p.get("prompt_kind"))
                if kind not in prompts:
                    prompts[kind] = str(p.get("prompt_text"))

        payload = {
            "agent_key": raw.get("agent_key"),
            "label": raw.get("label"),
            "mode": raw.get("mode"),
            "role_key": raw.get("role_key"),
            "provider_type": raw.get("provider_type"),
            "endpoint_key": raw.get("endpoint_key"),
            "model_id": raw.get("model_id"),
            "temperature": raw.get("temperature", 0.2),
            "max_tokens": raw.get("max_tokens", 1200),
            "timeout_sec": raw.get("timeout_sec", 90),
            "enabled": bool(raw.get("enabled", True) if import_disabled else True),
            "priority": raw.get("priority", 100),
            "tool_scope": raw.get("tool_scope", "[]"),
            "fallback_agent_key": raw.get("fallback_agent_key", ""),
            "prompts": prompts,
        }
        agent_key = (payload.get("agent_key") or "").strip()
        exists = conn.execute("SELECT id FROM chat_agents WHERE agent_key=?", (agent_key,)).fetchone() if agent_key else None
        if exists and not overwrite:
            skipped_agents += 1
            continue
        res = upsert_agent(conn, payload)
        if not res.get("ok"):
            errors.append(f"agent {agent_key}: {res.get('error')}")
            continue
        if exists:
            updated_agents += 1
        else:
            inserted_agents += 1

    return {
        "ok": True,
        "stats": {
            "inserted_endpoints": inserted_endpoints,
            "updated_endpoints": updated_endpoints,
            "inserted_agents": inserted_agents,
            "updated_agents": updated_agents,
            "skipped_agents": skipped_agents,
            "errors_count": len(errors),
        },
        "errors": errors,
    }


def upsert_discovery_cache(conn: sqlite3.Connection, endpoint_key: str, models: List[str]) -> Dict[str, Any]:
    ensure_schema(conn)
    key = (endpoint_key or "").strip()
    if not key:
        return {"ok": False, "error": "endpoint_key mancante"}
    row = conn.execute("SELECT id FROM provider_endpoints WHERE endpoint_key=?", (key,)).fetchone()
    if not row:
        return {"ok": False, "error": "endpoint non trovato"}
    clean = sorted({str(m).strip() for m in (models or []) if str(m).strip()})
    payload = json.dumps(clean, ensure_ascii=False)
    existing = conn.execute("SELECT id FROM provider_discovery_cache WHERE endpoint_id=?", (row["id"],)).fetchone()
    if existing:
        conn.execute(
            "UPDATE provider_discovery_cache SET models_json=?, discovered_at=CURRENT_TIMESTAMP WHERE endpoint_id=?",
            (payload, row["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO provider_discovery_cache (endpoint_id, models_json, discovered_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (row["id"], payload),
        )
    conn.commit()
    return {"ok": True, "endpoint_key": key, "models": clean}


def get_discovery_cache(conn: sqlite3.Connection, endpoint_key: Optional[str] = None) -> Dict[str, Any]:
    ensure_schema(conn)
    key = (endpoint_key or "").strip()
    query = (
        "SELECT c.models_json, c.discovered_at, e.endpoint_key, e.provider_type, e.label, e.base_url "
        "FROM provider_discovery_cache c "
        "JOIN provider_endpoints e ON e.id = c.endpoint_id "
    )
    params: List[Any] = []
    if key:
        query += "WHERE e.endpoint_key = ? "
        params.append(key)
    query += "ORDER BY c.discovered_at DESC"
    rows = conn.execute(query, tuple(params)).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        try:
            item["models"] = json.loads(item.pop("models_json") or "[]")
        except Exception:
            item["models"] = []
        items.append(item)
    return {"ok": True, "items": items}


def readiness_report(conn: sqlite3.Connection) -> Dict[str, Any]:
    ensure_schema(conn)
    validation = validate_agent_configuration(conn)
    endpoints = list_endpoints(conn)
    agents = list_agents(conn)
    cache = get_discovery_cache(conn)

    enabled_agents = [a for a in agents if int(a.get("enabled") or 0) == 1]
    enabled_endpoints = [e for e in endpoints if int(e.get("enabled") or 0) == 1]
    problems = validation.get("problems") or []
    has_errors = bool(validation.get("has_errors"))

    warnings = [p for p in problems if p.get("level") == "warning"]
    errors = [p for p in problems if p.get("level") == "error"]

    coverage = {
        "reader_answerer": any(a.get("mode") == "reader" and a.get("role_key") == "ReaderAnswerer" and int(a.get("enabled") or 0) == 1 for a in agents),
        "reader_spoiler_judge": any(a.get("mode") == "reader" and a.get("role_key") == "SpoilerJudge" and int(a.get("enabled") or 0) == 1 for a in agents),
        "author_answer_synthesizer": any(a.get("mode") == "author" and a.get("role_key") == "AnswerSynthesizer" and int(a.get("enabled") or 0) == 1 for a in agents),
    }
    coverage_ok = all(coverage.values())
    if not coverage_ok:
        warnings.append({"level": "warning", "message": "Copertura ruoli incompleta per go-live", "coverage": coverage})

    score = 100
    score -= min(len(warnings) * 4, 24)
    score -= min(len(errors) * 20, 60)
    if len(enabled_agents) == 0:
        score -= 20
    if len(enabled_endpoints) == 0:
        score -= 20
    score = max(0, min(score, 100))

    go_live_ready = (not has_errors) and coverage_ok and len(enabled_agents) > 0 and len(enabled_endpoints) > 0
    summary = {
        "enabled_agents": len(enabled_agents),
        "enabled_endpoints": len(enabled_endpoints),
        "discovery_cache_entries": len(cache.get("items") or []),
        "warnings": len(warnings),
        "errors": len(errors),
        "score": score,
        "go_live_ready": go_live_ready,
    }
    return {
        "ok": True,
        "summary": summary,
        "coverage": coverage,
        "validation": validation,
        "warnings": warnings,
        "errors": errors,
    }
