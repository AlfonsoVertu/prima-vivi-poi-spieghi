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
    tool_spoiler_predictive_guard,
)


def _sse(stage, content):
    return f"data: {json.dumps({'stage': stage, 'content': content}, ensure_ascii=False)}\n\n"


def _extract_json_object(raw):
    txt = str(raw or "").strip()
    if not txt:
        return None
    try:
        return json.loads(txt)
    except Exception:
        pass
    m = re.search(r"\{.*\}", txt, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _heuristic_router(user_msg: str, mode_hint: str = "auto"):
    t = (user_msg or "").lower()
    if mode_hint and mode_hint != "auto":
        intent = mode_hint
    elif "punto di vista" in t:
        intent = "alternate_pov"
    elif "riassum" in t or "recap" in t:
        intent = "recap"
    elif "raccont" in t:
        intent = "retell"
    elif "perché" in t or "spiega" in t:
        intent = "explain"
    else:
        intent = "qa"
    return {
        "intent": intent,
        "depth": "deep" if len(t) > 140 else "medium",
        "needs_narrative_output": intent in {"recap", "retell", "alternate_pov", "explain"},
        "requested_pov": None,
    }


def _tool_dispatch(name, cap_id):
    mapping = {
        "tool_book_index": lambda: tool_book_index(cap_id, admin_mode=False),
        "tool_chapter_text": lambda: tool_chapter_text(cap_id, admin_mode=False, include_previous=True),
        "tool_chapter_summary": lambda: tool_chapter_summary(cap_id, admin_mode=False, window=5),
        "tool_timeline_lookup": lambda: tool_timeline_lookup(cap_id, admin_mode=False),
        "tool_character_state": lambda: tool_character_state(cap_id, admin_mode=False),
        "tool_metadata_lookup": lambda: tool_metadata_lookup(cap_id, admin_mode=False),
        "tool_canon_constraints": lambda: tool_canon_constraints(cap_id, admin_mode=False),
    }
    fn = mapping.get(name)
    return fn() if fn else {"ok": False, "error": f"tool non supportato: {name}"}


def run_reader_orchestrator_stream(cap_id: int, user_msg: str, history: list[dict] | None, agent_configs: dict, *, get_all, get_cap, get_full_canon, get_conn, read_txt, get_character_context, mode_hint: str = "auto"):
    """Reader path v2: produce una sola synthesis finale user-visible."""
    try:
        from llm_client import generate_with_agent

        yield _sse("context", "🧭 Reader v2: avvio orchestrazione")
        reader_cfg = (agent_configs or {}).get("reader", {})

        # 1) Intent router (agente reale)
        router_cfg = reader_cfg.get("reader_intent_router", {})
        router_prompt = (
            "Classifica la richiesta lettore. Restituisci SOLO JSON con chiavi: "
            "intent(qa|recap|retell|alternate_pov|explain), depth(shallow|medium|deep), "
            "needs_narrative_output(bool), requested_pov(null|string).\n"
            f"Messaggio: {user_msg}\nMode hint: {mode_hint}"
        )
        router_raw = generate_with_agent(router_cfg, prompt=router_prompt)
        router_out = _extract_json_object(router_raw) or _heuristic_router(user_msg, mode_hint)
        if not isinstance(router_out, dict):
            router_out = _heuristic_router(user_msg, mode_hint)
        router_out.setdefault("intent", "qa")
        router_out.setdefault("depth", "medium")
        router_out.setdefault("needs_narrative_output", True)
        router_out.setdefault("requested_pov", None)
        yield _sse("orchestrator", f"router: {json.dumps(router_out, ensure_ascii=False)}")

        # 2) Scope planner (agente reale)
        planner_cfg = reader_cfg.get("reader_scope_planner", {})
        planner_prompt = (
            "Genera SOLO JSON con chiavi depth, tool_plan(array di tool reader-safe), reasoning_notes. "
            "Tool disponibili: tool_book_index, tool_chapter_text, tool_chapter_summary, tool_timeline_lookup, "
            "tool_character_state, tool_metadata_lookup, tool_canon_constraints.\n"
            f"Intent: {router_out.get('intent')}\nMessaggio: {user_msg}"
        )
        planner_raw = generate_with_agent(planner_cfg, prompt=planner_prompt)
        planner_out = _extract_json_object(planner_raw) or {}
        default_tools = ["tool_chapter_summary", "tool_metadata_lookup"] if router_out.get("intent") == "recap" else ["tool_chapter_text", "tool_character_state", "tool_metadata_lookup"]
        plan = planner_out.get("tool_plan", default_tools)
        if not isinstance(plan, list):
            plan = default_tools
        planner_out = {
            "depth": planner_out.get("depth", router_out.get("depth", "medium")),
            "tool_plan": [str(x).strip() for x in plan if str(x).strip()],
            "reasoning_notes": planner_out.get("reasoning_notes", "planner fallback"),
        }
        yield _sse("orchestrator", f"scope_planner: {json.dumps(planner_out, ensure_ascii=False)}")

        # 3) Archivist (tool-driven + enforcement allowed_tools)
        archivist_cfg = reader_cfg.get("reader_archivist", {})
        allowed = set(archivist_cfg.get("allowed_tools", []))
        dossier = {}
        blocked = []
        for tool_name in planner_out["tool_plan"]:
            if allowed and tool_name not in allowed:
                blocked.append(tool_name)
                continue
            dossier[tool_name] = _tool_dispatch(tool_name, cap_id)
        if blocked:
            yield _sse("orchestrator", f"archivist: tool bloccati da policy: {', '.join(blocked)}")
        yield _sse("context", "📚 dossier reader costruito")

        # 4) Transformer (agente reale)
        transformer_cfg = reader_cfg.get("reader_transformer", {})
        transform_prompt = (
            f"Intent: {router_out.get('intent')}\nDomanda: {user_msg}\n"
            f"POV richiesto: {router_out.get('requested_pov')}\n"
            f"Dossier: {json.dumps(dossier, ensure_ascii=False)[:9000]}\n"
            "Produci UNA bozza risposta spoiler-free basata solo sul dossier."
        )
        draft = generate_with_agent(transformer_cfg, prompt=transform_prompt)

        # 5) Validator (agente reale + guard lessicale trasparente)
        validator_cfg = reader_cfg.get("future_coherence_validator", {})
        lexical_guard = tool_spoiler_predictive_guard(draft, cap_id)
        validator_prompt = (
            "Valuta la bozza e restituisci SOLO JSON con status(SAFE|REWRITE), reason, rewrite_hints(array). "
            "Contesto: questo step usa un guard lessicale anti-spoiler/predittivo, non validazione full future-canon.\n"
            f"Guard result: {json.dumps(lexical_guard, ensure_ascii=False)}\n"
            f"Bozza: {draft}"
        )
        validator_raw = generate_with_agent(validator_cfg, prompt=validator_prompt)
        validator_out = _extract_json_object(validator_raw) or {}
        status = str(validator_out.get("status", "SAFE")).upper()
        rewrite_hints = validator_out.get("rewrite_hints", [])
        if lexical_guard.get("severity") in {"soft", "hard"}:
            status = "REWRITE"
            rewrite_hints = list(rewrite_hints) + lexical_guard.get("rewrite_hints", [])
        yield _sse("orchestrator", f"validator: status={status}")

        # 6) Spoiler guard (agente reale)
        guard_cfg = reader_cfg.get("reader_spoiler_guard", {})
        guarded_text = draft
        if status == "REWRITE":
            guard_prompt = (
                "Riscrivi il testo in modo spoiler-safe senza anticipazioni.\n"
                f"Hints: {json.dumps(rewrite_hints, ensure_ascii=False)}\n"
                f"Testo: {draft}"
            )
            guarded_text = generate_with_agent(guard_cfg, prompt=guard_prompt)

        # 7) Final voice (agente reale) - UNICA synthesis visibile
        final_cfg = reader_cfg.get("reader_final_voice", {})
        final_prompt = (
            "Rifinisci in tono 'Voce dell'Archivio', read-only, senza leak futuri.\n"
            f"Intent: {router_out.get('intent')}\n"
            f"Testo: {guarded_text}"
        )
        final = generate_with_agent(final_cfg, prompt=final_prompt)
        yield _sse("synthesis", final)
        yield "data: [DONE]\n\n"
    except Exception as e:
        yield _sse("error", str(e))
        yield "data: [DONE]\n\n"
