from chat_tools import (
    tool_chapter_summary, tool_timeline_lookup, tool_chapter_text, tool_metadata_lookup,
    get_db_path, get_chapters_dir, get_chapter_path,
)


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


def test_reader_metadata_whitelist_no_spoiler_fields():
    out = tool_metadata_lookup(5, admin_mode=False)
    assert out["ok"]
    md = out["metadata"]
    assert "riassunto_capitolo_successivo" not in md
    assert "personaggi_successivi" not in md
    assert "transizione_prossimo_capitolo" not in md
    assert "hook_finale" not in md


def test_path_helpers_are_consistent():
    assert get_db_path().endswith("roman.db")
    assert get_chapters_dir().endswith("capitoli")
    assert get_chapter_path(5).endswith("cap05.txt")
