import json
import os

import agent_config


def test_load_fallback_and_validate(tmp_path, monkeypatch):
    cfg_path = tmp_path / "agent_configs.json"
    monkeypatch.setattr(agent_config, "AGENT_CONFIG_FILE", str(cfg_path))

    data = agent_config.load_agent_configs()
    assert "reader" in data

    cfg_path.write_text("{bad", encoding="utf-8")
    data2 = agent_config.load_agent_configs()
    assert "reader" in data2

    errs = agent_config.validate_agent_configs({"reader": {}})
    assert errs


def test_save_and_get(tmp_path, monkeypatch):
    cfg_path = tmp_path / "agent_configs.json"
    monkeypatch.setattr(agent_config, "AGENT_CONFIG_FILE", str(cfg_path))
    base = agent_config.load_agent_configs()
    base["reader"]["reader_intent_router"]["model"] = "x-model"
    agent_config.save_agent_configs(base)
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert raw["reader"]["reader_intent_router"]["model"] == "x-model"
    one = agent_config.get_agent_config("reader", "reader_intent_router")
    assert one["model"] == "x-model"


def test_partial_invalid_agent_config_gets_normalized(tmp_path, monkeypatch):
    cfg_path = tmp_path / "agent_configs.json"
    monkeypatch.setattr(agent_config, "AGENT_CONFIG_FILE", str(cfg_path))
    cfg_path.write_text(
        json.dumps({
            "reader": {
                "reader_transformer": {
                    "provider": "",
                    "model": "",
                    "allowed_tools": "not-a-list",
                    "temperature": "bad",
                    "max_tokens": "bad"
                }
            },
            "admin": {}
        }),
        encoding="utf-8",
    )
    data = agent_config.load_agent_configs()
    cfg = data["reader"]["reader_transformer"]
    assert cfg["provider"] == "google"
    assert cfg["model"]
    assert isinstance(cfg["allowed_tools"], list)
    assert isinstance(cfg["temperature"], float)
    assert isinstance(cfg["max_tokens"], int)
