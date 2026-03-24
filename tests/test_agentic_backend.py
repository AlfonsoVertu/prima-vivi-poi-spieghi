import sqlite3
import unittest

from agent_registry import (
    ensure_schema,
    upsert_provider_endpoint,
    upsert_agent,
    validate_agent_configuration,
    set_agent_enabled,
    delete_agent,
    delete_provider_endpoint,
    export_registry_bundle,
    import_registry_bundle,
    upsert_discovery_cache,
    get_discovery_cache,
    readiness_report,
)
from chat_tools import execute_tool, available_tools_catalog, normalize_tool_plan, execute_tool_plan
from vector_index_local import ensure_schema as ensure_vector_schema, rebuild_index as vector_rebuild_index, list_index_versions, refresh_index_for_chapters


def build_test_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    conn.execute(
        """
        CREATE TABLE capitoli (
            id INTEGER PRIMARY KEY,
            titolo TEXT,
            riassunto TEXT,
            luogo TEXT,
            linea_narrativa TEXT,
            stato TEXT,
            parole_target INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE personaggi (
            id INTEGER PRIMARY KEY,
            nome TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE personaggi_capitoli (
            id INTEGER PRIMARY KEY,
            personaggio_id INTEGER,
            capitolo_id INTEGER,
            presente INTEGER,
            luogo TEXT,
            stato_emotivo TEXT,
            obiettivo TEXT,
            azione_parallela TEXT,
            sviluppo TEXT,
            note TEXT
        )
        """
    )
    conn.execute("CREATE TABLE timeline (id INTEGER PRIMARY KEY, descrizione TEXT)")
    conn.execute("INSERT INTO timeline (id, descrizione) VALUES (1, 'e1'), (2, 'e2')")
    conn.execute(
        "INSERT INTO capitoli (id, titolo, riassunto, luogo, linea_narrativa, stato, parole_target) VALUES "
        "(1, 'Cap1', 'Riassunto uno', 'Roma', 'A', 'draft', 1000), "
        "(2, 'Cap2', 'Riassunto due', 'Milano', 'B', 'draft', 1200), "
        "(3, 'Cap3', 'Riassunto tre', 'Torino', 'A', 'ready', 1500)"
    )
    conn.execute("INSERT INTO personaggi (id, nome) VALUES (1, 'Luca')")
    conn.execute(
        "INSERT INTO personaggi_capitoli (personaggio_id, capitolo_id, presente, luogo, stato_emotivo, obiettivo, azione_parallela, sviluppo, note) "
        "VALUES (1, 1, 1, 'Roma', 'teso', 'scoprire', '', '', '')"
    )
    conn.execute(
        "INSERT INTO chat_sessions (session_key, mode, cap_id, user_scope) VALUES ('sess-1', 'author', 1, '')"
    )
    conn.execute(
        "INSERT INTO chat_tool_runs (session_id, agent_id, tool_name, arguments_json, result_json, status, duration_ms) "
        "SELECT id, NULL, 'search_passages', '{}', '{\"ok\": true}', 'ok', 3 FROM chat_sessions WHERE session_key='sess-1'"
    )
    ensure_vector_schema(conn)
    conn.commit()
    return conn


class AgenticBackendTests(unittest.TestCase):
    def setUp(self):
        self.conn = build_test_conn()

    def tearDown(self):
        self.conn.close()

    def test_registry_crud_and_validation(self):
        ep = upsert_provider_endpoint(
            self.conn,
            {
                "endpoint_key": "local-test",
                "provider_type": "openai_compatible",
                "label": "Local Test",
                "base_url": "http://127.0.0.1:9999",
            },
        )
        self.assertTrue(ep["ok"])

        ag = upsert_agent(
            self.conn,
            {
                "agent_key": "author.agent.test",
                "label": "Author Agent",
                "mode": "author",
                "role_key": "AnswerSynthesizer",
                "provider_type": "openai_compatible",
                "endpoint_key": "local-test",
                "model_id": "x-1",
                "prompts": {"system": "x"},
            },
        )
        self.assertTrue(ag["ok"])

        val = validate_agent_configuration(self.conn, mode="author")
        self.assertTrue(val["ok"])
        self.assertFalse(val["has_errors"])

        dis = set_agent_enabled(self.conn, "author.agent.test", False)
        self.assertTrue(dis["ok"])
        self.assertEqual(dis["agent"]["enabled"], 0)

        blocked = delete_provider_endpoint(self.conn, "local-test")
        self.assertFalse(blocked["ok"])
        self.assertIn("agents", blocked)

        removed_agent = delete_agent(self.conn, "author.agent.test")
        self.assertTrue(removed_agent["ok"])

        removed_endpoint = delete_provider_endpoint(self.conn, "local-test")
        self.assertTrue(removed_endpoint["ok"])

    def test_tool_catalog_and_execution_paths(self):
        catalog = available_tools_catalog(admin_mode=True)
        names = {x["tool"] for x in catalog}
        self.assertIn("list_chapters_range", names)
        self.assertIn("get_recent_tool_runs", names)
        self.assertIn("update_chapter_fields", names)
        self.assertIn("vector_search_reader", names)
        self.assertIn("vector_search_author", names)

        r1 = execute_tool(
            self.conn,
            "list_chapters_range",
            {"start_cap_id": 1, "end_cap_id": 2, "limit": 2},
            admin_mode=False,
        )
        self.assertTrue(r1["ok"])
        self.assertEqual(len(r1["results"]), 2)

        r2 = execute_tool(self.conn, "get_recent_tool_runs", {"session_key": "sess-1", "limit": 10}, admin_mode=False)
        self.assertTrue(r2["ok"])
        self.assertGreaterEqual(len(r2["runs"]), 1)

        r3 = execute_tool(
            self.conn,
            "update_chapter_fields",
            {"cap_id": 1, "patch": {"titolo": "Nuovo Titolo"}, "dry_run": True},
            admin_mode=True,
        )
        self.assertTrue(r3["ok"])
        self.assertTrue(r3["dry_run"])

        bad = execute_tool(self.conn, "search_passages", {"query": "cap", "limit": "oops"}, admin_mode=False)
        self.assertFalse(bad["ok"])
        self.assertIn("intero", bad["error"])

    def test_vector_tools_with_local_index(self):
        chapters = [dict(r) for r in self.conn.execute("SELECT * FROM capitoli ORDER BY id").fetchall()]
        result = vector_rebuild_index(
            self.conn,
            chapters,
            lambda cid: f"capitolo {cid} testo locale prova simbolo vash lin",
            chunk_size=20,
            overlap=5,
            embedding_provider="hash_local",
            embedding_model="",
        )
        self.assertTrue(result["ok"])
        self.assertTrue((result.get("version_tag") or "").startswith("v_"))
        stats = execute_tool(self.conn, "vector_index_stats", {}, admin_mode=False)
        self.assertTrue(stats["ok"])
        self.assertGreater(stats["chunks"], 0)
        self.assertEqual(stats["embedding_provider"], "hash_local")
        self.assertTrue((stats.get("active_version") or "").startswith("v_"))
        versions = list_index_versions(self.conn, limit=5)
        self.assertTrue(versions["ok"])
        self.assertGreaterEqual(len(versions["items"]), 1)
        s_reader = execute_tool(self.conn, "vector_search_reader", {"query": "vash", "cap_id": 2, "k": 3}, admin_mode=False)
        self.assertTrue(s_reader["ok"])
        self.assertTrue(all(r["cap_id"] <= 2 for r in s_reader["results"]))
        self.assertIn("search_mode", s_reader)
        s_author = execute_tool(self.conn, "vector_search_author", {"query": "lin", "k": 3}, admin_mode=True)
        self.assertTrue(s_author["ok"])
        if s_author["results"]:
            self.assertIn("score", s_author["results"][0])

    def test_vector_incremental_refresh(self):
        chapters = [dict(r) for r in self.conn.execute("SELECT * FROM capitoli ORDER BY id").fetchall()]
        base = vector_rebuild_index(
            self.conn,
            chapters,
            lambda cid: f"base text cap {cid}",
            chunk_size=20,
            overlap=5,
            embedding_provider="hash_local",
            embedding_model="",
        )
        self.assertTrue(base["ok"])
        refreshed = refresh_index_for_chapters(
            self.conn,
            chapters,
            lambda cid: f"delta aggiornato cap {cid}",
            cap_ids=[2, 3],
            chunk_size=20,
            overlap=5,
            embedding_provider="hash_local",
            embedding_model="",
        )
        self.assertTrue(refreshed["ok"])
        self.assertEqual(refreshed["mode"], "incremental_refresh")
        self.assertEqual(refreshed["cap_ids_updated"], [2, 3])
        self.assertTrue((refreshed.get("version_tag") or "").endswith("_delta"))
        stats = execute_tool(self.conn, "vector_index_stats", {}, admin_mode=False)
        self.assertTrue(stats["ok"])
        self.assertTrue((stats.get("active_version") or "").endswith("_delta"))

    def test_mcp_hardening_schema_tables_exist(self):
        row_tokens = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='mcp_bridge_tokens'"
        ).fetchone()
        row_rate = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='mcp_bridge_rate_limits'"
        ).fetchone()
        row_audit = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='mcp_bridge_audit'"
        ).fetchone()
        self.assertIsNotNone(row_tokens)
        self.assertIsNotNone(row_rate)
        self.assertIsNotNone(row_audit)

    def test_tool_plan_normalization_and_execution(self):
        bad_plan = normalize_tool_plan({"tool": "list_chapters_range"})
        self.assertFalse(bad_plan["ok"])

        dry_plan = normalize_tool_plan([
            {"tool": "list_chapters_range", "arguments": {"start_cap_id": 1, "end_cap_id": 2, "limit": 2}},
            {"tool": "update_chapter_fields", "arguments": {"cap_id": 1, "patch": {"titolo": "X"}, "dry_run": True}},
        ])
        self.assertTrue(dry_plan["ok"])
        self.assertEqual(len(dry_plan["plan"]), 2)

        reader_exec = execute_tool_plan(
            self.conn,
            dry_plan["plan"],
            admin_mode=False,
            allowed_tools=["list_chapters_range", "update_chapter_fields"],
            stop_on_error=False,
        )
        self.assertFalse(reader_exec["ok"])
        self.assertEqual(reader_exec["errors"], 1)  # update_chapter_fields bloccato da permesso execute_tool

        scoped_exec = execute_tool_plan(
            self.conn,
            dry_plan["plan"],
            admin_mode=True,
            allowed_tools=["list_chapters_range"],  # secondo tool fuori scope
            stop_on_error=False,
        )
        self.assertFalse(scoped_exec["ok"])
        self.assertEqual(scoped_exec["blocked"], 1)

    def test_registry_export_import_bundle(self):
        upsert_provider_endpoint(
            self.conn,
            {
                "endpoint_key": "bundle-endpoint",
                "provider_type": "openai_compatible",
                "label": "Bundle Endpoint",
                "base_url": "http://127.0.0.1:9999",
            },
        )
        upsert_agent(
            self.conn,
            {
                "agent_key": "bundle.agent",
                "label": "Bundle Agent",
                "mode": "author",
                "role_key": "AnswerSynthesizer",
                "provider_type": "openai_compatible",
                "endpoint_key": "bundle-endpoint",
                "model_id": "bundle-model",
                "prompts": {"system": "Prompt di bundle"},
            },
        )
        exported = export_registry_bundle(self.conn)
        self.assertTrue(exported["ok"])
        bundle = exported["bundle"]
        self.assertGreaterEqual(len(bundle["endpoints"]), 1)
        self.assertGreaterEqual(len(bundle["agents"]), 1)

        other = build_test_conn()
        try:
            imported = import_registry_bundle(other, bundle, overwrite=True, import_disabled=True)
            self.assertTrue(imported["ok"])
            self.assertGreaterEqual(imported["stats"]["inserted_agents"] + imported["stats"]["updated_agents"], 1)
        finally:
            other.close()

    def test_discovery_cache_roundtrip(self):
        upsert_provider_endpoint(
            self.conn,
            {
                "endpoint_key": "cache-endpoint",
                "provider_type": "ollama",
                "label": "Cache Endpoint",
                "base_url": "http://127.0.0.1:11434",
            },
        )
        saved = upsert_discovery_cache(self.conn, "cache-endpoint", ["model-b", "model-a", "model-a"])
        self.assertTrue(saved["ok"])
        self.assertEqual(saved["models"], ["model-a", "model-b"])

        all_cache = get_discovery_cache(self.conn)
        self.assertTrue(all_cache["ok"])
        self.assertGreaterEqual(len(all_cache["items"]), 1)

        single = get_discovery_cache(self.conn, endpoint_key="cache-endpoint")
        self.assertTrue(single["ok"])
        self.assertEqual(len(single["items"]), 1)
        self.assertEqual(single["items"][0]["models"], ["model-a", "model-b"])

    def test_readiness_report_shape(self):
        rep = readiness_report(self.conn)
        self.assertTrue(rep["ok"])
        self.assertIn("summary", rep)
        self.assertIn("score", rep["summary"])
        self.assertIn("go_live_ready", rep["summary"])
        self.assertIn("coverage", rep)


if __name__ == "__main__":
    unittest.main()
