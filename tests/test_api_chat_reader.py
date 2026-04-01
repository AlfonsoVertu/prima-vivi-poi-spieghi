import json
import pytest

pytest.importorskip("flask")
app_module = pytest.importorskip("app")


def test_api_chat_reader_uses_v2_and_no_write(monkeypatch):
    called = {"v2": False, "write": False}

    def fake_write(*args, **kwargs):
        called["write"] = True
        raise AssertionError("write_txt non deve essere chiamato")

    def fake_v2(*args, **kwargs):
        called["v2"] = True
        yield f"data: {json.dumps({'stage': 'synthesis', 'content': 'ok'})}\n\n"
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(app_module, "write_txt", fake_write)
    import reader_orchestrator_v2
    monkeypatch.setattr(reader_orchestrator_v2, "run_reader_orchestrator_stream", fake_v2)

    client = app_module.app.test_client()
    r = client.post(
        "/api/chat/5",
        json={"message": "riassumimi", "admin_mode": False, "stream": False, "history": []},
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["reply"] == "ok"
    assert called["v2"] is True
    assert called["write"] is False
