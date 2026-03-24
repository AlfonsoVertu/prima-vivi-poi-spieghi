import json
import sqlite3
from typing import Dict, List

from agent_registry import ensure_schema


def _safe_json_loads(value: str, fallback):
    try:
        return json.loads(value) if value else fallback
    except Exception:
        return fallback


def _compact_unique(values: List[str], max_items: int = 8) -> List[str]:
    out = []
    seen = set()
    for item in values:
        norm = (item or "").strip()
        if not norm:
            continue
        key = norm.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(norm)
    if len(out) > max_items:
        out = out[-max_items:]
    return out


def _extract_user_questions(history: List[Dict[str, str]]) -> List[str]:
    qs = []
    for item in history:
        if item.get("role") != "user":
            continue
        content = (item.get("content") or "").strip()
        if not content:
            continue
        if "?" in content:
            qs.append(content)
    return _compact_unique(qs, max_items=6)


def _extract_characters(history: List[Dict[str, str]]) -> List[str]:
    names = []
    for item in history:
        content = (item.get("content") or "").strip()
        if not content:
            continue
        words = [w.strip(".,:;!?()[]{}\"'") for w in content.split()]
        for w in words:
            if len(w) >= 3 and w[:1].isupper() and w[1:].islower():
                names.append(w)
    return _compact_unique(names, max_items=10)


def _extract_facts(history: List[Dict[str, str]]) -> List[str]:
    facts = []
    for item in history:
        if item.get("role") != "assistant":
            continue
        content = (item.get("content") or "").strip()
        if not content:
            continue
        short = content.split("\n")[0][:180].strip()
        if short:
            facts.append(short)
    return _compact_unique(facts, max_items=6)


def compute_memory_snapshot(history: List[Dict[str, str]]) -> Dict[str, List[str]]:
    questions = _extract_user_questions(history)
    chars = _extract_characters(history)
    facts = _extract_facts(history)
    themes = _compact_unique([q.split()[0] for q in questions if q], max_items=6)
    return {
        "facts_understood": facts,
        "open_questions": questions,
        "characters_followed": chars,
        "themes_discussed": themes,
    }


def upsert_session_memory(conn: sqlite3.Connection, session_key: str, mode: str, cap_id: int, history: List[Dict[str, str]]) -> Dict[str, List[str]]:
    ensure_schema(conn)
    snapshot = compute_memory_snapshot(history)

    row = conn.execute("SELECT id FROM chat_sessions WHERE session_key=?", (session_key,)).fetchone()
    if row:
        session_id = row[0]
        conn.execute(
            "UPDATE chat_sessions SET mode=?, cap_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (mode, cap_id, session_id),
        )
    else:
        cur = conn.execute(
            "INSERT INTO chat_sessions (session_key, mode, cap_id, user_scope) VALUES (?, ?, ?, '')",
            (session_key, mode, cap_id),
        )
        session_id = cur.lastrowid

    summary_text = " | ".join(snapshot["open_questions"][:2]) if snapshot["open_questions"] else ""

    mem_row = conn.execute("SELECT id FROM chat_session_memory WHERE session_id=?", (session_id,)).fetchone()
    if mem_row:
        conn.execute(
            """
            UPDATE chat_session_memory
            SET facts_understood=?, open_questions=?, characters_followed=?, themes_discussed=?, summary_text=?, updated_at=CURRENT_TIMESTAMP
            WHERE session_id=?
            """,
            (
                json.dumps(snapshot["facts_understood"], ensure_ascii=False),
                json.dumps(snapshot["open_questions"], ensure_ascii=False),
                json.dumps(snapshot["characters_followed"], ensure_ascii=False),
                json.dumps(snapshot["themes_discussed"], ensure_ascii=False),
                summary_text,
                session_id,
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO chat_session_memory
            (session_id, facts_understood, open_questions, characters_followed, themes_discussed, summary_text)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                json.dumps(snapshot["facts_understood"], ensure_ascii=False),
                json.dumps(snapshot["open_questions"], ensure_ascii=False),
                json.dumps(snapshot["characters_followed"], ensure_ascii=False),
                json.dumps(snapshot["themes_discussed"], ensure_ascii=False),
                summary_text,
            ),
        )

    conn.commit()
    return snapshot


def load_session_memory(conn: sqlite3.Connection, session_key: str) -> Dict[str, List[str]]:
    ensure_schema(conn)
    row = conn.execute(
        """
        SELECT m.facts_understood, m.open_questions, m.characters_followed, m.themes_discussed
        FROM chat_session_memory m
        JOIN chat_sessions s ON s.id = m.session_id
        WHERE s.session_key=?
        """,
        (session_key,),
    ).fetchone()
    if not row:
        return {"facts_understood": [], "open_questions": [], "characters_followed": [], "themes_discussed": []}

    return {
        "facts_understood": _safe_json_loads(row[0], []),
        "open_questions": _safe_json_loads(row[1], []),
        "characters_followed": _safe_json_loads(row[2], []),
        "themes_discussed": _safe_json_loads(row[3], []),
    }
