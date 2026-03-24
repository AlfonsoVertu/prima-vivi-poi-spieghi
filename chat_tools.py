import json
import os
import sqlite3
from typing import Any, Dict, List
from vector_index_local import ensure_schema as ensure_vector_schema, search_index as vector_search_index, index_stats as vector_index_stats

ALLOWED_UPDATE_FIELDS = {
    "titolo", "pov", "luogo", "data_narrativa", "descrizione", "personaggi_precedenti", "personaggi_successivi",
    "background", "parallelo", "obiettivi_personaggi", "timeline_capitolo", "timeline_opera", "riassunto",
    "stato", "anno", "luogo_macro", "linea_narrativa", "personaggi_capitolo", "scene_outline",
    "oggetti_simbolo", "tensione_capitolo", "hook_finale", "rischi_incoerenza", "transizione_prossimo_capitolo",
    "riassunto_capitolo_precedente", "riassunto_capitolo_successivo", "parole_target", "revisione_istruzioni",
}

READ_ONLY_TOOLS = {
    "get_chapter_metadata",
    "get_chapter_text",
    "get_character_state",
    "get_timeline_until",
    "search_passages",
    "list_chapters_range",
    "get_recent_tool_runs",
    "vector_search_reader",
    "vector_search_author",
    "vector_index_stats",
}

MUTATING_TOOLS = {
    "update_chapter_fields",
}

TOOL_SPECS: Dict[str, Dict[str, Any]] = {
    "get_chapter_metadata": {
        "description": "Restituisce i metadati completi del capitolo.",
        "args": {"cap_id": "int (obbligatorio)"},
    },
    "get_chapter_text": {
        "description": "Legge il file testo capitolo locale.",
        "args": {"cap_id": "int (obbligatorio)"},
    },
    "get_character_state": {
        "description": "Stato personaggio per capitolo fino a max_cap_id opzionale.",
        "args": {"name": "str (obbligatorio)", "max_cap_id": "int (opzionale)"},
    },
    "get_timeline_until": {
        "description": "Timeline completa o fino a cap_id.",
        "args": {"cap_id": "int (opzionale)"},
    },
    "search_passages": {
        "description": "Ricerca testuale su titolo/riassunto capitoli.",
        "args": {"query": "str (obbligatorio)", "cap_id": "int (opzionale)", "limit": "int 1..20"},
    },
    "list_chapters_range": {
        "description": "Lista sintetica capitoli in un range id.",
        "args": {"start_cap_id": "int (obbligatorio)", "end_cap_id": "int (obbligatorio)", "limit": "int 1..50"},
    },
    "get_recent_tool_runs": {
        "description": "Audit ultimi tool run (globale o per session_key).",
        "args": {"session_key": "str (opzionale)", "limit": "int 1..100"},
    },
    "vector_search_reader": {
        "description": "Ricerca locale su indice capitoli con frontier anti-spoiler (cap_id <= frontier).",
        "args": {"query": "str (obbligatorio)", "cap_id": "int (obbligatorio)", "k": "int 1..20"},
    },
    "vector_search_author": {
        "description": "Ricerca locale su indice capitoli full-canon (author mode).",
        "args": {"query": "str (obbligatorio)", "k": "int 1..20"},
    },
    "vector_index_stats": {
        "description": "Statistiche indice locale (chunks, capitoli, timestamp).",
        "args": {},
    },
    "update_chapter_fields": {
        "description": "Aggiorna campi metadata capitolo in modalità admin.",
        "args": {"cap_id": "int (obbligatorio)", "patch": "dict", "dry_run": "bool (opzionale)"},
    },
}


def _row_to_dict(row):
    return dict(row) if row else None


def _to_int(value: Any, field_name: str, minimum: int = None, maximum: int = None) -> int:
    try:
        iv = int(value)
    except Exception:
        raise ValueError(f"{field_name} deve essere un intero")
    if minimum is not None and iv < minimum:
        raise ValueError(f"{field_name} deve essere >= {minimum}")
    if maximum is not None and iv > maximum:
        raise ValueError(f"{field_name} deve essere <= {maximum}")
    return iv


def get_chapter_metadata(conn: sqlite3.Connection, cap_id: int) -> Dict[str, Any]:
    row = conn.execute("SELECT * FROM capitoli WHERE id=?", (cap_id,)).fetchone()
    if not row:
        return {"ok": False, "error": f"Capitolo {cap_id} non trovato"}
    return {"ok": True, "capitolo": dict(row)}


def get_chapter_text(cap_id: int) -> Dict[str, Any]:
    path = os.path.join("capitoli", f"cap{cap_id:02d}.txt")
    if not os.path.exists(path):
        return {"ok": False, "error": f"File capitolo non trovato: {path}"}
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()
    return {"ok": True, "cap_id": cap_id, "text": txt}


def get_character_state(conn: sqlite3.Connection, name: str, max_cap_id: int = None) -> Dict[str, Any]:
    char = conn.execute("SELECT * FROM personaggi WHERE LOWER(nome)=LOWER(?)", (name,)).fetchone()
    if not char:
        return {"ok": False, "error": f"Personaggio non trovato: {name}"}

    q = (
        "SELECT pc.capitolo_id, pc.presente, pc.luogo, pc.stato_emotivo, pc.obiettivo, pc.azione_parallela, pc.sviluppo, pc.note "
        "FROM personaggi_capitoli pc WHERE pc.personaggio_id=?"
    )
    params: List[Any] = [char["id"]]
    if isinstance(max_cap_id, int):
        q += " AND pc.capitolo_id <= ?"
        params.append(max_cap_id)
    q += " ORDER BY pc.capitolo_id"
    rows = conn.execute(q, tuple(params)).fetchall()
    return {
        "ok": True,
        "personaggio": dict(char),
        "stato_per_capitolo": [dict(r) for r in rows],
    }


def get_timeline_until(conn: sqlite3.Connection, cap_id: int = None) -> Dict[str, Any]:
    if isinstance(cap_id, int):
        rows = conn.execute(
            """
            SELECT t.*
            FROM timeline t
            JOIN capitoli c ON c.timeline_event_id = t.id
            WHERE c.id <= ?
            ORDER BY c.id, t.id
            """,
            (cap_id,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM timeline ORDER BY id").fetchall()
    return {"ok": True, "timeline": [dict(r) for r in rows]}


def search_passages(conn: sqlite3.Connection, query: str, cap_id: int = None, limit: int = 5) -> Dict[str, Any]:
    q = "SELECT id, titolo, riassunto FROM capitoli WHERE (LOWER(titolo) LIKE ? OR LOWER(riassunto) LIKE ?)"
    params: List[Any] = [f"%{query.lower()}%", f"%{query.lower()}%"]
    if isinstance(cap_id, int):
        q += " AND id <= ?"
        params.append(cap_id)
    q += " ORDER BY id LIMIT ?"
    params.append(max(1, min(limit, 20)))
    rows = conn.execute(q, tuple(params)).fetchall()
    return {"ok": True, "results": [dict(r) for r in rows]}


def list_chapters_range(conn: sqlite3.Connection, start_cap_id: int, end_cap_id: int, limit: int = 20) -> Dict[str, Any]:
    if end_cap_id < start_cap_id:
        return {"ok": False, "error": "end_cap_id deve essere >= start_cap_id"}
    safe_limit = max(1, min(limit, 50))
    rows = conn.execute(
        """
        SELECT id, titolo, luogo, linea_narrativa, stato, parole_target
        FROM capitoli
        WHERE id BETWEEN ? AND ?
        ORDER BY id
        LIMIT ?
        """,
        (start_cap_id, end_cap_id, safe_limit),
    ).fetchall()
    return {
        "ok": True,
        "start_cap_id": start_cap_id,
        "end_cap_id": end_cap_id,
        "results": [dict(r) for r in rows],
    }


def get_recent_tool_runs(conn: sqlite3.Connection, session_key: str = "", limit: int = 20) -> Dict[str, Any]:
    safe_limit = max(1, min(limit, 100))
    skey = (session_key or "").strip()
    params: List[Any] = [safe_limit]
    query = (
        "SELECT tr.id, tr.tool_name, tr.status, tr.created_at, tr.duration_ms, s.session_key "
        "FROM chat_tool_runs tr "
        "LEFT JOIN chat_sessions s ON s.id = tr.session_id "
    )
    if skey:
        query += "WHERE s.session_key = ? "
        params = [skey, safe_limit]
    query += "ORDER BY tr.id DESC LIMIT ?"
    rows = conn.execute(query, tuple(params)).fetchall()
    return {"ok": True, "session_key": skey, "runs": [dict(r) for r in rows]}


def update_chapter_fields(conn: sqlite3.Connection, cap_id: int, patch: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    row = conn.execute("SELECT id FROM capitoli WHERE id=?", (cap_id,)).fetchone()
    if not row:
        return {"ok": False, "error": f"Capitolo {cap_id} non trovato"}

    updates = []
    params: List[Any] = []
    updated_fields = []
    for k, v in (patch or {}).items():
        if k not in ALLOWED_UPDATE_FIELDS:
            continue
        updates.append(f"{k}=?")
        params.append(v)
        updated_fields.append(k)

    if not updates:
        return {"ok": False, "error": "Nessun campo aggiornabile nel patch"}

    if dry_run:
        return {"ok": True, "cap_id": cap_id, "updated_fields": updated_fields, "dry_run": True}

    params.append(cap_id)
    conn.execute(f"UPDATE capitoli SET {', '.join(updates)} WHERE id=?", tuple(params))
    conn.commit()
    return {"ok": True, "cap_id": cap_id, "updated_fields": updated_fields}


def execute_tool(conn: sqlite3.Connection, tool_name: str, arguments: Dict[str, Any], admin_mode: bool = False) -> Dict[str, Any]:
    name = (tool_name or "").strip()
    args = arguments or {}

    if name in MUTATING_TOOLS and not admin_mode:
        return {"ok": False, "error": f"Tool non autorizzato in reader mode: {name}"}

    try:
        if name == "get_chapter_metadata":
            return get_chapter_metadata(conn, _to_int(args.get("cap_id"), "cap_id", minimum=1))
        if name == "get_chapter_text":
            return get_chapter_text(_to_int(args.get("cap_id"), "cap_id", minimum=1))
        if name == "get_character_state":
            max_cap = args.get("max_cap_id")
            max_cap = _to_int(max_cap, "max_cap_id", minimum=1) if max_cap is not None else None
            return get_character_state(conn, str(args.get("name", "")), max_cap)
        if name == "get_timeline_until":
            cid = args.get("cap_id")
            cid = _to_int(cid, "cap_id", minimum=1) if cid is not None else None
            return get_timeline_until(conn, cid)
        if name == "search_passages":
            cid = args.get("cap_id")
            cid = _to_int(cid, "cap_id", minimum=1) if cid is not None else None
            return search_passages(conn, str(args.get("query", "")), cid, _to_int(args.get("limit", 5), "limit", 1, 20))
        if name == "list_chapters_range":
            return list_chapters_range(
                conn,
                _to_int(args.get("start_cap_id"), "start_cap_id", minimum=1),
                _to_int(args.get("end_cap_id"), "end_cap_id", minimum=1),
                _to_int(args.get("limit", 20), "limit", 1, 50),
            )
        if name == "get_recent_tool_runs":
            return get_recent_tool_runs(
                conn,
                str(args.get("session_key", "")),
                _to_int(args.get("limit", 20), "limit", 1, 100),
            )
        if name == "vector_search_reader":
            ensure_vector_schema(conn)
            cap_id = _to_int(args.get("cap_id"), "cap_id", minimum=1)
            return vector_search_index(
                conn,
                str(args.get("query", "")),
                k=_to_int(args.get("k", 5), "k", 1, 20),
                max_cap_id=cap_id,
                embedding_provider=os.getenv("VECTOR_EMBEDDING_PROVIDER", "hash_local"),
                embedding_model=os.getenv("VECTOR_EMBEDDING_MODEL", ""),
                embedding_base_url=os.getenv("VECTOR_EMBEDDING_BASE_URL", ""),
                embedding_api_key=os.getenv("VECTOR_EMBEDDING_API_KEY", ""),
            )
        if name == "vector_search_author":
            ensure_vector_schema(conn)
            return vector_search_index(
                conn,
                str(args.get("query", "")),
                k=_to_int(args.get("k", 5), "k", 1, 20),
                max_cap_id=None,
                embedding_provider=os.getenv("VECTOR_EMBEDDING_PROVIDER", "hash_local"),
                embedding_model=os.getenv("VECTOR_EMBEDDING_MODEL", ""),
                embedding_base_url=os.getenv("VECTOR_EMBEDDING_BASE_URL", ""),
                embedding_api_key=os.getenv("VECTOR_EMBEDDING_API_KEY", ""),
            )
        if name == "vector_index_stats":
            ensure_vector_schema(conn)
            return vector_index_stats(conn)
        if name == "update_chapter_fields":
            return update_chapter_fields(
                conn,
                _to_int(args.get("cap_id"), "cap_id", minimum=1),
                args.get("patch") or {},
                bool(args.get("dry_run", False)),
            )
    except ValueError as ve:
        return {"ok": False, "error": str(ve)}

    return {"ok": False, "error": f"Tool non riconosciuto: {name}"}


def available_tools(admin_mode: bool = False) -> List[str]:
    tools = sorted(READ_ONLY_TOOLS)
    if admin_mode:
        tools += sorted(MUTATING_TOOLS)
    return tools


def available_tools_catalog(admin_mode: bool = False) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for tool_name in available_tools(admin_mode=admin_mode):
        spec = TOOL_SPECS.get(tool_name, {})
        items.append(
            {
                "tool": tool_name,
                "kind": "mutating" if tool_name in MUTATING_TOOLS else "read_only",
                "description": spec.get("description", ""),
                "args": spec.get("args", {}),
            }
        )
    return items


def normalize_tool_plan(plan: Any, max_steps: int = 8) -> Dict[str, Any]:
    if not isinstance(plan, list):
        return {"ok": False, "error": "tool_plan deve essere una lista"}
    normalized = []
    for idx, step in enumerate(plan):
        if len(normalized) >= max_steps:
            break
        if not isinstance(step, dict):
            return {"ok": False, "error": f"Step {idx} non valido: deve essere un oggetto"}
        tool_name = str(step.get("tool", "")).strip()
        if not tool_name:
            return {"ok": False, "error": f"Step {idx} non valido: tool mancante"}
        args = step.get("arguments", {})
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return {"ok": False, "error": f"Step {idx} non valido: arguments deve essere un oggetto"}
        normalized.append({"tool": tool_name, "arguments": args})
    if not normalized:
        return {"ok": False, "error": "tool_plan vuoto"}
    return {"ok": True, "plan": normalized}


def execute_tool_plan(
    conn: sqlite3.Connection,
    plan: Any,
    admin_mode: bool = False,
    allowed_tools: List[str] = None,
    stop_on_error: bool = False,
) -> Dict[str, Any]:
    normalized = normalize_tool_plan(plan)
    if not normalized.get("ok"):
        return {"ok": False, "error": normalized.get("error", "tool_plan non valido"), "runs": []}
    steps = normalized["plan"]

    allowed_set = set(str(t).strip() for t in (allowed_tools or []) if str(t).strip())
    enforce_scope = len(allowed_set) > 0
    runs = []
    has_error = False

    for i, step in enumerate(steps, start=1):
        tool_name = step["tool"]
        args = step["arguments"]
        if enforce_scope and tool_name not in allowed_set:
            run = {
                "index": i,
                "tool": tool_name,
                "status": "blocked",
                "result": {"ok": False, "error": f"Tool fuori scope: {tool_name}"},
            }
            runs.append(run)
            has_error = True
            if stop_on_error:
                break
            continue

        result = execute_tool(conn, tool_name, args, admin_mode=admin_mode)
        run = {
            "index": i,
            "tool": tool_name,
            "status": "ok" if result.get("ok") else "error",
            "result": result,
        }
        runs.append(run)
        if not result.get("ok"):
            has_error = True
            if stop_on_error:
                break

    return {
        "ok": not has_error,
        "runs": runs,
        "executed": sum(1 for r in runs if r.get("status") == "ok"),
        "blocked": sum(1 for r in runs if r.get("status") == "blocked"),
        "errors": sum(1 for r in runs if r.get("status") == "error"),
    }
