import json
import re
from chat_tools import (
    tool_book_index,
    tool_chapter_text,
    tool_chapter_summary,
    tool_timeline_lookup,
    tool_character_state,
    tool_metadata_lookup,
    tool_canon_constraints,
    tool_future_consistency_check,
)


INTENT_MAP = {
    "qa": ["chi", "cosa", "quando", "dove"],
    "recap": ["riassum", "recap"],
    "retell": ["racconta", "raccontamelo"],
    "alternate_pov": ["punto di vista", "dal punto di vista", "pov"],
    "explain": ["perché", "spiega", "motiv"],
}


def _sse(stage, content):
    return f"data: {json.dumps({'stage': stage, 'content': content}, ensure_ascii=False)}\n\n"


def _pick_intent(text: str, mode_hint: str = "auto"):
    t = (text or "").lower()
    if mode_hint and mode_hint != "auto":
        return mode_hint
    if "punto di vista" in t or "dal punto di vista" in t:
        return "alternate_pov"
    for intent, keys in INTENT_MAP.items():
        if any(k in t for k in keys):
            return intent
    return "qa"


def run_reader_orchestrator_stream(cap_id: int, user_msg: str, history: list[dict] | None, agent_configs: dict, *, get_all, get_cap, get_full_canon, get_conn, read_txt, get_character_context, mode_hint: str = "auto"):
    try:
        from llm_client import generate_with_agent
        yield _sse("context", "🧭 Reader v2: avvio orchestrazione")
        reader_cfg = (agent_configs or {}).get("reader", {})

        # 1) Router
        intent = _pick_intent(user_msg, mode_hint)
        depth = "deep" if len((user_msg or "")) > 140 else "medium"
        router_out = {"intent": intent, "depth": depth, "needs_narrative_output": intent in {"recap", "retell", "alternate_pov", "explain"}, "requested_pov": None}
        pov_match = re.search(r"punto di vista di\s+([\wÀ-ÿ'\- ]+)", user_msg or "", re.IGNORECASE)
        if pov_match:
            router_out["requested_pov"] = pov_match.group(1).strip()
        yield _sse("orchestrator", f"router: {json.dumps(router_out, ensure_ascii=False)}")

        # 2) Scope planner
        tool_plan = ["tool_chapter_summary", "tool_metadata_lookup"] if intent == "recap" else ["tool_chapter_text", "tool_character_state", "tool_metadata_lookup"]
        planner_out = {"depth": depth, "tool_plan": tool_plan, "reasoning_notes": "Piano adattivo in base all'intento."}
        yield _sse("orchestrator", f"scope_planner: {json.dumps(planner_out, ensure_ascii=False)}")

        # 3) Archivist
        dossier = {}
        for tool in planner_out["tool_plan"]:
            if tool == "tool_book_index":
                dossier[tool] = tool_book_index(cap_id, admin_mode=False)
            elif tool == "tool_chapter_text":
                dossier[tool] = tool_chapter_text(cap_id, admin_mode=False, include_previous=True)
            elif tool == "tool_chapter_summary":
                dossier[tool] = tool_chapter_summary(cap_id, admin_mode=False, window=5)
            elif tool == "tool_timeline_lookup":
                dossier[tool] = tool_timeline_lookup(cap_id, admin_mode=False)
            elif tool == "tool_character_state":
                dossier[tool] = tool_character_state(cap_id, admin_mode=False)
            elif tool == "tool_metadata_lookup":
                dossier[tool] = tool_metadata_lookup(cap_id, admin_mode=False)
            elif tool == "tool_canon_constraints":
                dossier[tool] = tool_canon_constraints(cap_id, admin_mode=False)
        yield _sse("context", "📚 dossier reader costruito")

        # 4) Transformer
        transformer_cfg = reader_cfg.get("reader_transformer", {})
        transform_prompt = (
            f"Intent: {intent}\nDomanda: {user_msg}\n"
            f"POV richiesto: {router_out.get('requested_pov')}\n"
            f"Dossier: {json.dumps(dossier, ensure_ascii=False)[:8000]}\n"
            "Genera una bozza di risposta per il lettore senza spoiler futuri."
        )
        draft = generate_with_agent(transformer_cfg, prompt=transform_prompt)
        yield _sse("synthesis", draft)

        # 5) Future validator
        validation = tool_future_consistency_check(draft, cap_id)
        yield _sse("orchestrator", f"validator: {json.dumps(validation, ensure_ascii=False)}")

        # 6) Spoiler guard
        safe_text = draft
        if validation.get("severity") in {"soft", "hard"}:
            safe_text = "Resto sul perimetro noto fino a questo capitolo: " + draft
        # 7) Final voice
        final_cfg = reader_cfg.get("reader_final_voice", {})
        final = generate_with_agent(final_cfg, prompt=f"Rifinisci in tono 'Voce dell'Archivio' il seguente testo:\n{safe_text}")
        yield _sse("synthesis", final)
        yield "data: [DONE]\n\n"
    except Exception as e:
        yield _sse("error", str(e))
        yield "data: [DONE]\n\n"
