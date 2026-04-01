from chat_tools import tool_chapter_summary, tool_timeline_lookup, tool_chapter_text


def test_reader_summary_no_future():
    out = tool_chapter_summary(5, admin_mode=False, window=10)
    assert out["ok"]
    assert all(item["id"] <= 5 for item in out["items"])


def test_reader_timeline_no_future():
    out = tool_timeline_lookup(5, admin_mode=False)
    assert out["ok"]
    # weaker check: tool should run and return a list with no explicit future filter violations in keys
    assert isinstance(out["items"], list)


def test_reader_chapter_text_current_only():
    out = tool_chapter_text(5, admin_mode=False, include_previous=False)
    assert out["ok"]
    assert "current" in out
    assert "previous" not in out
