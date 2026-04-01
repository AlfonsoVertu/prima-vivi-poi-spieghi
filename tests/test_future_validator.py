from chat_tools import tool_spoiler_predictive_guard


def test_spoiler_predictive_guard_no_direct_spoiler_echo():
    out = tool_spoiler_predictive_guard("Nel prossimo capitolo succede X", 5)
    assert out["ok"]
    assert out["severity"] in {"soft", "hard"}
    dumped = str(out)
    assert "succede X" not in dumped
