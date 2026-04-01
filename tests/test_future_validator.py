from chat_tools import tool_future_consistency_check


def test_future_validator_no_direct_spoiler_echo():
    out = tool_future_consistency_check("Nel prossimo capitolo succede X", 5)
    assert out["ok"]
    assert out["severity"] in {"soft", "hard"}
    dumped = str(out)
    assert "succede X" not in dumped
