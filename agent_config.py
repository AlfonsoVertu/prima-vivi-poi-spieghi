import json
import logging
import os
from copy import deepcopy

AGENT_CONFIG_FILE = os.path.join(os.getcwd(), "agent_configs.json")
logger = logging.getLogger(__name__)

DEFAULT_AGENT_CONFIGS = {
    "reader": {
        "reader_intent_router": {"enabled": True, "provider": "openai", "model": "gpt-5-mini", "system_prompt": "Classifica l'intento del lettore senza rispondere.", "allowed_tools": [], "temperature": 0.1, "max_tokens": 500},
        "reader_scope_planner": {"enabled": True, "provider": "openai", "model": "gpt-5-mini", "system_prompt": "Decidi profondità e fonti da interrogare.", "allowed_tools": [], "temperature": 0.1, "max_tokens": 500},
        "reader_archivist": {"enabled": True, "provider": "anthropic", "model": "claude-3-7-sonnet-20250219", "system_prompt": "Recupera fatti canonici accessibili fino all'orizzonte lettore.", "allowed_tools": ["tool_book_index", "tool_chapter_summary", "tool_timeline_lookup", "tool_character_state", "tool_chapter_text", "tool_metadata_lookup", "tool_canon_constraints"], "temperature": 0.2, "max_tokens": 1200},
        "reader_transformer": {"enabled": True, "provider": "google", "model": "gemini-2.0-pro-exp-02-05", "system_prompt": "Trasforma il dossier in racconto o spiegazione coerente.", "allowed_tools": ["tool_chapter_text", "tool_character_state", "tool_metadata_lookup"], "temperature": 0.7, "max_tokens": 2000},
        "future_coherence_validator": {"enabled": True, "provider": "openai", "model": "o3-mini", "system_prompt": "Valida bozza con guard anti-spoiler/predittivo (non full future-canon).", "allowed_tools": ["tool_spoiler_predictive_guard"], "temperature": 0.0, "max_tokens": 800},
        "reader_spoiler_guard": {"enabled": True, "provider": "openai", "model": "gpt-5-mini", "system_prompt": "Blocca spoiler, anticipazioni e leak.", "allowed_tools": [], "temperature": 0.0, "max_tokens": 800},
        "reader_final_voice": {"enabled": True, "provider": "anthropic", "model": "claude-3-5-sonnet-20241022", "system_prompt": "Rispondi come voce dell'Archivio, in read-only.", "allowed_tools": [], "temperature": 0.6, "max_tokens": 2200},
    },
    "admin": {},
}


def validate_agent_configs(data: dict) -> list[str]:
    errors = []
    if not isinstance(data, dict):
        return ["root deve essere un oggetto"]
    for scope in ["reader", "admin"]:
        if scope not in data or not isinstance(data.get(scope), dict):
            errors.append(f"scope mancante o non valido: {scope}")
    for scope, agents in data.items():
        if not isinstance(agents, dict):
            errors.append(f"scope non oggetto: {scope}")
            continue
        for name, cfg in agents.items():
            if not isinstance(cfg, dict):
                errors.append(f"{scope}.{name}: config non oggetto")
                continue
            for req in ["enabled", "provider", "model", "system_prompt", "allowed_tools", "temperature", "max_tokens"]:
                if req not in cfg:
                    errors.append(f"{scope}.{name}: campo mancante {req}")
            if "allowed_tools" in cfg and not isinstance(cfg["allowed_tools"], list):
                errors.append(f"{scope}.{name}: allowed_tools deve essere lista")
    return errors


def load_agent_configs() -> dict:
    if not os.path.exists(AGENT_CONFIG_FILE):
        return deepcopy(DEFAULT_AGENT_CONFIGS)
    try:
        with open(AGENT_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        errors = validate_agent_configs(data)
        if errors:
            logger.warning("agent_configs.json non valido, fallback defaults: %s", "; ".join(errors))
            return deepcopy(DEFAULT_AGENT_CONFIGS)
        return data
    except Exception as e:
        logger.warning("Errore load agent configs (%s), fallback defaults", e)
        return deepcopy(DEFAULT_AGENT_CONFIGS)


def save_agent_configs(data: dict) -> None:
    errors = validate_agent_configs(data)
    if errors:
        raise ValueError("Configurazione agenti non valida: " + "; ".join(errors))
    with open(AGENT_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_agent_config(scope: str, agent_name: str) -> dict:
    data = load_agent_configs()
    scoped = data.get(scope, {}) if isinstance(data, dict) else {}
    if agent_name in scoped:
        return deepcopy(scoped[agent_name])
    return deepcopy(DEFAULT_AGENT_CONFIGS.get(scope, {}).get(agent_name, {}))
