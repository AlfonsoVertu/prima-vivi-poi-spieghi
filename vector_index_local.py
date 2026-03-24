import json
import math
import re
import sqlite3
import os
import time
from typing import Any, Dict, List, Callable
try:
    import requests
except Exception:  # pragma: no cover
    requests = None

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS vector_index_chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cap_id INTEGER NOT NULL,
        chunk_no INTEGER NOT NULL,
        chunk_text TEXT NOT NULL,
        metadata_json TEXT DEFAULT '{}',
        embedding_json TEXT DEFAULT '[]',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_vector_chunks_cap ON vector_index_chunks(cap_id)",
    """
    CREATE TABLE IF NOT EXISTS vector_index_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_tag TEXT NOT NULL,
        chunks_inserted INTEGER DEFAULT 0,
        chapters_indexed INTEGER DEFAULT 0,
        embedding_provider TEXT DEFAULT 'hash_local',
        embedding_model TEXT DEFAULT '',
        embedding_dim INTEGER DEFAULT 256,
        build_meta_json TEXT DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_vector_versions_created ON vector_index_versions(created_at DESC)",
]


def ensure_schema(conn: sqlite3.Connection) -> None:
    for stmt in SCHEMA:
        conn.execute(stmt)
    conn.commit()


def _chunk_text(text: str, chunk_size: int = 1200, overlap: int = 180) -> List[str]:
    src = (text or "").strip()
    if not src:
        return []
    words = src.split()
    if not words:
        return []
    chunks: List[str] = []
    i = 0
    step = max(1, chunk_size - max(0, overlap))
    while i < len(words):
        chunk = " ".join(words[i:i + chunk_size]).strip()
        if chunk:
            chunks.append(chunk)
        i += step
    return chunks


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-ZÀ-ÿ0-9_']+", (text or "").lower())


def _compute_hash_embedding(text: str, dim: int = 256) -> List[float]:
    tokens = _tokenize(text)
    if not tokens:
        return [0.0] * dim
    vec = [0.0] * dim
    for t in tokens:
        idx = hash(t) % dim
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def compute_embedding(
    text: str,
    dim: int = 256,
    provider: str = "hash_local",
    model: str = "",
    base_url: str = "",
    api_key: str = "",
) -> List[float]:
    p = (provider or "hash_local").strip().lower()
    if p == "hash_local":
        return _compute_hash_embedding(text, dim=dim)
    if p in {"openai_compatible", "openai-compatible", "lmstudio", "ollama"}:
        if requests is None:
            return _compute_hash_embedding(text, dim=dim)
        url_base = (base_url or os.getenv("OPENAI_COMPATIBLE_URL", "") or os.getenv("LMSTUDIO_URL", "")).rstrip("/")
        if not url_base:
            return _compute_hash_embedding(text, dim=dim)
        endpoint = f"{url_base}/v1/embeddings"
        payload = {"input": text, "model": model or "text-embedding-3-small"}
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            arr = data.get("data") or []
            if arr and isinstance(arr[0], dict) and isinstance(arr[0].get("embedding"), list):
                emb = [float(x) for x in arr[0]["embedding"]]
                n = math.sqrt(sum(v * v for v in emb)) or 1.0
                return [v / n for v in emb]
        except Exception:
            return _compute_hash_embedding(text, dim=dim)
    return _compute_hash_embedding(text, dim=dim)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    return float(sum(a[i] * b[i] for i in range(n)))


def rebuild_index(
    conn: sqlite3.Connection,
    chapters: List[Dict[str, Any]],
    read_txt: Callable[[int], str],
    chunk_size: int = 1200,
    overlap: int = 180,
    embedding_dim: int = 256,
    embedding_provider: str = "hash_local",
    embedding_model: str = "",
    embedding_base_url: str = "",
    embedding_api_key: str = "",
) -> Dict[str, Any]:
    ensure_schema(conn)
    conn.execute("DELETE FROM vector_index_chunks")

    inserted = 0
    for cap in chapters:
        cap_id = int(cap.get("id") or 0)
        if cap_id <= 0:
            continue
        text = read_txt(cap_id)
        chunks = _chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        for no, chunk in enumerate(chunks, start=1):
            meta = {
                "cap_id": cap_id,
                "titolo": cap.get("titolo", ""),
                "linea_narrativa": cap.get("linea_narrativa", ""),
                "pov": cap.get("pov", ""),
            }
            emb = compute_embedding(
                chunk,
                dim=embedding_dim,
                provider=embedding_provider,
                model=embedding_model,
                base_url=embedding_base_url,
                api_key=embedding_api_key,
            )
            conn.execute(
                """
                INSERT INTO vector_index_chunks (cap_id, chunk_no, chunk_text, metadata_json, embedding_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (cap_id, no, chunk, json.dumps(meta, ensure_ascii=False), json.dumps(emb)),
            )
            inserted += 1
    conn.commit()
    conn.execute("CREATE TABLE IF NOT EXISTS vector_index_meta (k TEXT PRIMARY KEY, v TEXT)")
    conn.execute("INSERT OR REPLACE INTO vector_index_meta (k, v) VALUES ('embedding_provider', ?)", (embedding_provider,))
    conn.execute("INSERT OR REPLACE INTO vector_index_meta (k, v) VALUES ('embedding_model', ?)", (embedding_model or "",))
    conn.execute("INSERT OR REPLACE INTO vector_index_meta (k, v) VALUES ('embedding_dim', ?)", (str(embedding_dim),))
    version_tag = f"v_{int(time.time())}"
    build_meta = {
        "chunk_size": int(chunk_size),
        "overlap": int(overlap),
    }
    conn.execute(
        """
        INSERT INTO vector_index_versions
            (version_tag, chunks_inserted, chapters_indexed, embedding_provider, embedding_model, embedding_dim, build_meta_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            version_tag,
            int(inserted),
            int(len(chapters)),
            embedding_provider,
            embedding_model or "",
            int(embedding_dim),
            json.dumps(build_meta, ensure_ascii=False),
        ),
    )
    conn.execute("INSERT OR REPLACE INTO vector_index_meta (k, v) VALUES ('active_version', ?)", (version_tag,))
    conn.commit()
    return {
        "ok": True,
        "chunks_inserted": inserted,
        "chapters_indexed": len(chapters),
        "embedding_dim": embedding_dim,
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model or "",
        "version_tag": version_tag,
    }


def refresh_index_for_chapters(
    conn: sqlite3.Connection,
    chapters: List[Dict[str, Any]],
    read_txt: Callable[[int], str],
    cap_ids: List[int],
    chunk_size: int = 1200,
    overlap: int = 180,
    embedding_dim: int = 256,
    embedding_provider: str = "hash_local",
    embedding_model: str = "",
    embedding_base_url: str = "",
    embedding_api_key: str = "",
) -> Dict[str, Any]:
    ensure_schema(conn)
    normalized_caps: List[int] = []
    for raw in (cap_ids or []):
        try:
            cid = int(raw)
        except Exception:
            continue
        if cid > 0 and cid not in normalized_caps:
            normalized_caps.append(cid)
    if not normalized_caps:
        return {"ok": False, "error": "cap_ids non validi"}

    chapter_map = {int(c.get("id") or 0): c for c in chapters if int(c.get("id") or 0) > 0}
    deleted = 0
    inserted = 0
    touched_caps: List[int] = []
    for cid in normalized_caps:
        cur = conn.execute("DELETE FROM vector_index_chunks WHERE cap_id=?", (cid,))
        deleted += int(cur.rowcount or 0)
        cap = chapter_map.get(cid)
        if not cap:
            continue
        touched_caps.append(cid)
        text = read_txt(cid)
        chunks = _chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        for no, chunk in enumerate(chunks, start=1):
            meta = {
                "cap_id": cid,
                "titolo": cap.get("titolo", ""),
                "linea_narrativa": cap.get("linea_narrativa", ""),
                "pov": cap.get("pov", ""),
            }
            emb = compute_embedding(
                chunk,
                dim=embedding_dim,
                provider=embedding_provider,
                model=embedding_model,
                base_url=embedding_base_url,
                api_key=embedding_api_key,
            )
            conn.execute(
                """
                INSERT INTO vector_index_chunks (cap_id, chunk_no, chunk_text, metadata_json, embedding_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (cid, no, chunk, json.dumps(meta, ensure_ascii=False), json.dumps(emb)),
            )
            inserted += 1
    conn.execute("CREATE TABLE IF NOT EXISTS vector_index_meta (k TEXT PRIMARY KEY, v TEXT)")
    conn.execute("INSERT OR REPLACE INTO vector_index_meta (k, v) VALUES ('embedding_provider', ?)", (embedding_provider,))
    conn.execute("INSERT OR REPLACE INTO vector_index_meta (k, v) VALUES ('embedding_model', ?)", (embedding_model or "",))
    conn.execute("INSERT OR REPLACE INTO vector_index_meta (k, v) VALUES ('embedding_dim', ?)", (str(embedding_dim),))
    version_tag = f"v_{int(time.time())}_delta"
    build_meta = {
        "chunk_size": int(chunk_size),
        "overlap": int(overlap),
        "mode": "incremental_refresh",
        "cap_ids": touched_caps,
        "chunks_deleted": int(deleted),
    }
    conn.execute(
        """
        INSERT INTO vector_index_versions
            (version_tag, chunks_inserted, chapters_indexed, embedding_provider, embedding_model, embedding_dim, build_meta_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            version_tag,
            int(inserted),
            int(len(touched_caps)),
            embedding_provider,
            embedding_model or "",
            int(embedding_dim),
            json.dumps(build_meta, ensure_ascii=False),
        ),
    )
    conn.execute("INSERT OR REPLACE INTO vector_index_meta (k, v) VALUES ('active_version', ?)", (version_tag,))
    conn.commit()
    return {
        "ok": True,
        "mode": "incremental_refresh",
        "cap_ids_requested": normalized_caps,
        "cap_ids_updated": touched_caps,
        "chunks_deleted": int(deleted),
        "chunks_inserted": int(inserted),
        "version_tag": version_tag,
    }


def search_index(
    conn: sqlite3.Connection,
    query: str,
    k: int = 5,
    max_cap_id: int = None,
    min_score: float = 0.0,
    lexical_boost: float = 0.05,
    embedding_dim: int = 256,
    embedding_provider: str = "hash_local",
    embedding_model: str = "",
    embedding_base_url: str = "",
    embedding_api_key: str = "",
) -> Dict[str, Any]:
    ensure_schema(conn)
    q = (query or "").strip().lower()
    if not q:
        return {"ok": False, "error": "query mancante"}
    safe_k = max(1, min(int(k), 20))

    sql = "SELECT id, cap_id, chunk_no, chunk_text, metadata_json, embedding_json FROM vector_index_chunks WHERE 1=1"
    params: List[Any] = []
    if isinstance(max_cap_id, int):
        sql += " AND cap_id <= ?"
        params.append(max_cap_id)
    sql += " ORDER BY cap_id, chunk_no"

    rows = conn.execute(sql, tuple(params)).fetchall()
    q_emb = compute_embedding(
        q,
        dim=embedding_dim,
        provider=embedding_provider,
        model=embedding_model,
        base_url=embedding_base_url,
        api_key=embedding_api_key,
    )
    scored = []
    for row in rows:
        emb_raw = row["embedding_json"] if isinstance(row, sqlite3.Row) else row[5]
        try:
            emb = json.loads(emb_raw or "[]")
        except Exception:
            emb = []
        score = cosine_similarity(q_emb, emb)
        chunk_text = row["chunk_text"] if isinstance(row, sqlite3.Row) else row[3]
        if q in (chunk_text or "").lower():
            score += lexical_boost
        if score >= min_score:
            scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)

    items = []
    for score, row in scored[:safe_k]:
        meta_raw = row["metadata_json"] if isinstance(row, sqlite3.Row) else row[4]
        try:
            meta = json.loads(meta_raw or "{}")
        except Exception:
            meta = {}
        items.append(
            {
                "id": row["id"] if isinstance(row, sqlite3.Row) else row[0],
                "cap_id": row["cap_id"] if isinstance(row, sqlite3.Row) else row[1],
                "chunk_no": row["chunk_no"] if isinstance(row, sqlite3.Row) else row[2],
                "chunk_text": row["chunk_text"] if isinstance(row, sqlite3.Row) else row[3],
                "score": round(float(score), 6),
                "metadata": meta,
            }
        )
    return {
        "ok": True,
        "query": query,
        "k": safe_k,
        "results": items,
        "search_mode": "semantic_local",
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model or "",
    }


def index_stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    ensure_schema(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS vector_index_meta (k TEXT PRIMARY KEY, v TEXT)")
    total = conn.execute("SELECT COUNT(*) AS n FROM vector_index_chunks").fetchone()[0]
    caps = conn.execute("SELECT COUNT(DISTINCT cap_id) AS n FROM vector_index_chunks").fetchone()[0]
    last = conn.execute("SELECT MAX(created_at) AS ts FROM vector_index_chunks").fetchone()[0]
    rows = conn.execute("SELECT k, v FROM vector_index_meta").fetchall()
    meta = {r[0]: r[1] for r in rows}
    return {
        "ok": True,
        "chunks": int(total or 0),
        "chapters": int(caps or 0),
        "last_indexed_at": last,
        "embedding_provider": meta.get("embedding_provider", "hash_local"),
        "embedding_model": meta.get("embedding_model", ""),
        "embedding_dim": int(meta.get("embedding_dim", "256") or 256),
        "active_version": meta.get("active_version", ""),
    }


def list_index_versions(conn: sqlite3.Connection, limit: int = 20) -> Dict[str, Any]:
    ensure_schema(conn)
    safe_limit = max(1, min(int(limit or 20), 100))
    rows = conn.execute(
        """
        SELECT id, version_tag, chunks_inserted, chapters_indexed, embedding_provider, embedding_model, embedding_dim, build_meta_json, created_at
        FROM vector_index_versions
        ORDER BY id DESC
        LIMIT ?
        """,
        (safe_limit,),
    ).fetchall()
    items: List[Dict[str, Any]] = []
    for r in rows:
        try:
            build_meta = json.loads(r["build_meta_json"] if isinstance(r, sqlite3.Row) else r[7] or "{}")
        except Exception:
            build_meta = {}
        items.append(
            {
                "id": r["id"] if isinstance(r, sqlite3.Row) else r[0],
                "version_tag": r["version_tag"] if isinstance(r, sqlite3.Row) else r[1],
                "chunks_inserted": int((r["chunks_inserted"] if isinstance(r, sqlite3.Row) else r[2]) or 0),
                "chapters_indexed": int((r["chapters_indexed"] if isinstance(r, sqlite3.Row) else r[3]) or 0),
                "embedding_provider": r["embedding_provider"] if isinstance(r, sqlite3.Row) else r[4],
                "embedding_model": r["embedding_model"] if isinstance(r, sqlite3.Row) else r[5],
                "embedding_dim": int((r["embedding_dim"] if isinstance(r, sqlite3.Row) else r[6]) or 256),
                "build_meta": build_meta,
                "created_at": r["created_at"] if isinstance(r, sqlite3.Row) else r[8],
            }
        )
    return {"ok": True, "items": items, "limit": safe_limit}
