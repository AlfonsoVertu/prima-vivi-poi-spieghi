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
from chat_tools import execute_tool, available_tools_catalog


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
