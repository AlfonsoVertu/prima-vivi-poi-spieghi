import re
from typing import Dict, List


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def audit_reader_reply(reply: str, cap_id: int, chapters: List[Dict]) -> Dict:
    text = reply or ""
    lower = _normalize(text)
    violations = []

    # 1) Explicit future chapter mentions (e.g. capitolo 42)
    for m in re.finditer(r"capitolo\s+(\d{1,3})", lower):
        mentioned = int(m.group(1))
        if mentioned > cap_id:
            violations.append({"type": "future_chapter_reference", "value": mentioned})

    # 2) Future chapter title leakage
    for c in chapters:
        cid = c.get("id")
        title = (c.get("titolo") or "").strip()
        if not isinstance(cid, int) or cid <= cap_id or not title:
            continue
        t = _normalize(title)
        if t and len(t) >= 4 and t in lower:
            violations.append({"type": "future_chapter_title", "value": title, "cap_id": cid})

    status = "unsafe" if violations else "safe"
    return {
        "status": status,
        "violations": violations,
    }


def enforce_reader_safety(reply: str, cap_id: int, chapters: List[Dict]) -> Dict:
    audit = audit_reader_reply(reply, cap_id, chapters)
    if audit["status"] == "safe":
        return {"reply": reply, "audit": audit, "rewritten": False}

    safe_reply = (
        "Posso aiutarti senza spoiler fino a questo punto della storia. "
        "Se vuoi, riformulo la risposta concentrandomi solo sui capitoli che hai già letto."
    )
    return {"reply": safe_reply, "audit": audit, "rewritten": True}
