import json
import sys
import types

from reader_orchestrator_v2 import run_reader_orchestrator_stream


def test_reader_stream_emits_single_final_synthesis_and_enforces_allowed_tools(monkeypatch):
    calls = []

    def fake_generate_with_agent(agent_cfg, **kwargs):
        prompt = kwargs.get("prompt", "")
        if "Classifica la richiesta lettore" in prompt:
            return json.dumps({"intent": "recap", "depth": "medium", "needs_narrative_output": True, "requested_pov": None})
        if "Genera SOLO JSON con chiavi depth" in prompt:
            return json.dumps({"depth": "medium", "tool_plan": ["tool_chapter_text", "tool_metadata_lookup"]})
        if "Produci UNA bozza risposta" in prompt:
            calls.append("transformer")
            return "DRAFT NON VISIBILE"
        if "Valuta la bozza" in prompt:
            return json.dumps({"status": "SAFE", "reason": "ok", "rewrite_hints": []})
        if "Rifinisci in tono" in prompt:
            return "FINAL ONLY"
        return "{}"

    fake_llm = types.SimpleNamespace(generate_with_agent=fake_generate_with_agent)
    monkeypatch.setitem(sys.modules, "llm_client", fake_llm)

    cfg = {
        "reader": {
            "reader_intent_router": {},
            "reader_scope_planner": {},
            "reader_archivist": {"allowed_tools": ["tool_metadata_lookup"]},
            "reader_transformer": {},
            "future_coherence_validator": {},
            "reader_spoiler_guard": {},
            "reader_final_voice": {},
        }
    }

    events = list(
        run_reader_orchestrator_stream(
            5,
            "riassumimi",
            [],
            cfg,
            get_all=lambda: [],
            get_cap=lambda _id: {},
            get_full_canon=lambda: "",
            get_conn=lambda: None,
            read_txt=lambda _id: "",
            get_character_context=lambda _id: "",
        )
    )

    payloads = []
    for e in events:
        if e.startswith("data: {"):
            payloads.append(json.loads(e[6:].strip()))

    synths = [p["content"] for p in payloads if p.get("stage") == "synthesis"]
    assert synths == ["FINAL ONLY"]

    orchestrator_msgs = [p["content"] for p in payloads if p.get("stage") == "orchestrator"]
    assert any("tool bloccati da policy" in msg for msg in orchestrator_msgs)


def test_reader_orchestrator_fallbacks_on_missing_agent_cfg(monkeypatch):
    def fake_generate_with_agent(agent_cfg, **kwargs):
        prompt = kwargs.get("prompt", "")
        if "Classifica la richiesta lettore" in prompt:
            return "{\"intent\":\"qa\"}"
        if "Genera SOLO JSON con chiavi depth" in prompt:
            return "{\"tool_plan\": [\"tool_metadata_lookup\"]}"
        if "Valuta la bozza" in prompt:
            return "{\"status\":\"SAFE\"}"
        return "FINAL"

    fake_llm = types.SimpleNamespace(generate_with_agent=fake_generate_with_agent)
    monkeypatch.setitem(sys.modules, "llm_client", fake_llm)

    events = list(
        run_reader_orchestrator_stream(
            5,
            "domanda",
            [],
            {"reader": {"reader_archivist": {"allowed_tools": ["tool_metadata_lookup"]}}},
            get_all=lambda: [],
            get_cap=lambda _id: {},
            get_full_canon=lambda: "",
            get_conn=lambda: None,
            read_txt=lambda _id: "",
            get_character_context=lambda _id: "",
        )
    )
    synth = [json.loads(e[6:].strip())["content"] for e in events if e.startswith("data: {") and json.loads(e[6:].strip()).get("stage") == "synthesis"]
    assert synth[-1] == "FINAL"
