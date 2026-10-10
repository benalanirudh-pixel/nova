"""
Contract tests for the assistant tool surface in tools.py (and its coupling
to brain.py).

These protect the invariants the Ollama tool-calling loop depends on:

- Every callable in TOOLS is advertised in TOOL_SCHEMA, and every schema
  function name resolves to a real tool (no drift as tools are added/renamed).
- Each schema entry is a well-formed function schema (name, description,
  object parameters, required keys exist in properties).
- run_tool never raises: unknown tools, malformed/non-dict args and bad
  arguments all come back as text, exactly as run_tool promises.

Offline only. No Ollama, no network, no browser launches. Only side-effect-free
tools are actually executed (get_time); a missing-arg call to open_website is
used to hit the TypeError path without opening anything.

Run from the project root:
    .\\venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import datetime
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools


EXPECTED_TOOLS = {
    "get_time",
    "get_market_data",
    "get_market_analysis",
    "get_market_lab_analysis",
    "get_market_brief",
    "open_website",
    "open_app",
    "search_web",
    "search_youtube",
    "web_research",
}


class TestRegistrySchemaConsistency(unittest.TestCase):
    """TOOLS and TOOL_SCHEMA must stay in lock-step."""

    def _schema_names(self):
        return [entry["function"]["name"] for entry in tools.TOOL_SCHEMA]

    def test_every_tool_is_advertised(self):
        for name in tools.TOOLS:
            self.assertIn(
                name,
                self._schema_names(),
                f"tool '{name}' is registered but missing from TOOL_SCHEMA",
            )

    def test_every_schema_entry_resolves_to_a_tool(self):
        for name in self._schema_names():
            self.assertIn(
                name,
                tools.TOOLS,
                f"TOOL_SCHEMA advertises '{name}' but it is not in TOOLS",
            )

    def test_no_duplicate_schema_names(self):
        names = self._schema_names()
        self.assertEqual(len(names), len(set(names)))

    def test_expected_tools_present(self):
        self.assertTrue(
            EXPECTED_TOOLS.issubset(set(tools.TOOLS)),
            f"missing tools: {EXPECTED_TOOLS - set(tools.TOOLS)}",
        )

    def test_schema_entries_are_well_formed(self):
        for entry in tools.TOOL_SCHEMA:
            self.assertEqual(entry.get("type"), "function")
            fn = entry.get("function")
            self.assertIsInstance(fn, dict)
            self.assertIsInstance(fn.get("name"), str)
            self.assertTrue(fn["name"])
            self.assertIsInstance(fn.get("description"), str)
            self.assertTrue(fn["description"].strip())
            params = fn.get("parameters")
            self.assertIsInstance(params, dict)
            self.assertEqual(params.get("type"), "object")
            properties = params.get("properties", {})
            self.assertIsInstance(properties, dict)
            for req in params.get("required", []):
                self.assertIn(
                    req,
                    properties,
                    f"{fn['name']}: required arg '{req}' not in properties",
                )


class TestRunTool(unittest.TestCase):
    """run_tool must never raise and must normalize args as documented."""

    def setUp(self):
        # Silence the "[tool] ... -> ..." debug print for clean output.
        patcher = mock.patch.object(tools, "DEBUG", False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_unknown_tool_returns_text(self):
        out = tools.run_tool("no_such_tool", {})
        self.assertIn("Unknown tool", out)

    def test_get_time_executes_and_returns_string(self):
        out = tools.run_tool("get_time", {})
        self.assertIsInstance(out, str)
        self.assertTrue(out.strip())
        # Should include the current year somewhere.
        self.assertIn(str(datetime.datetime.now().year), out)

    def test_json_string_args_are_parsed(self):
        out = tools.run_tool("get_time", "{}")
        self.assertIsInstance(out, str)

    def test_malformed_json_string_becomes_empty_args(self):
        # Invalid JSON -> normalized to {} -> get_time() runs fine.
        out = tools.run_tool("get_time", "this is not json {")
        self.assertIsInstance(out, str)
        self.assertIn(str(datetime.datetime.now().year), out)

    def test_non_dict_args_become_empty(self):
        out = tools.run_tool("get_time", 12345)
        self.assertIsInstance(out, str)

    def test_bad_arguments_are_reported_not_raised(self):
        # open_website requires 'url'; calling with {} raises TypeError before
        # the body runs, so no browser opens. run_tool converts it to text.
        out = tools.run_tool("open_website", {})
        self.assertIn("Bad arguments", out)

    def test_json_args_with_wrong_keys_hit_bad_arguments(self):
        # Valid JSON but wrong keys -> TypeError -> Bad arguments text.
        out = tools.run_tool("get_time", '{"x": 1}')
        self.assertIn("Bad arguments", out)

    def test_brief_dispatches_through_run_tool(self):
        report = {
            "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "market_regime": "BEARISH",
            "breadth": {"advancing": 1, "declining": 2},
            "data_availability": {},
        }
        with mock.patch.object(
            tools, "_load_latest_market_lab_report", return_value=report
        ):
            out = tools.run_tool("get_market_brief", {})
        self.assertIn("NOVA MORNING MARKET BRIEF", out)
        self.assertIn("BEARISH", out)


class TestBrainCoupling(unittest.TestCase):
    """The brain must dispatch on tool names that run_tool understands."""

    def test_brain_reuses_tools_schema(self):
        import brain

        self.assertIs(brain.TOOL_SCHEMA, tools.TOOL_SCHEMA)
        self.assertGreaterEqual(brain.MAX_TOOL_ROUNDS, 1)

    def test_brain_schema_names_all_dispatchable(self):
        import brain

        schema_names = [e["function"]["name"] for e in brain.TOOL_SCHEMA]
        for name in schema_names:
            self.assertIn(name, tools.TOOLS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
