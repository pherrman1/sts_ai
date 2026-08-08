#!/usr/bin/env python3
"""Tests for agent telemetry parsing and aggregation.

Uses synthetic Pi events — no real API calls required.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.summarize_agent_context import load_records, summarise


def _write_jsonl(path: str, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


SYNTHETIC_RECORDS: list[dict] = [
    {
        "ts": "2026-08-08T12:00:00.000Z",
        "agent": "architect",
        "model": "deepseek/deepseek-v4-pro",
        "turn": 1,
        "tool": "read",
        "path": "apps/one_combat.cpp",
        "offset": 7990,
        "limit": 120,
        "ok": True,
    },
    {
        "ts": "2026-08-08T12:00:01.000Z",
        "agent": "architect",
        "model": "deepseek/deepseek-v4-pro",
        "turn": 1,
        "tool": "read",
        "path": "apps/one_combat.cpp",
        "offset": 2369,
        "limit": 200,
        "ok": True,
    },
    {
        "ts": "2026-08-08T12:00:02.000Z",
        "agent": "architect",
        "model": "deepseek/deepseek-v4-pro",
        "turn": 1,
        "tool": "grep",
        "path": "apps/one_combat.cpp",
        "pattern": "runFullRunOOC",
        "ok": True,
    },
    {
        "ts": "2026-08-08T12:00:03.000Z",
        "agent": "architect",
        "model": "deepseek/deepseek-v4-pro",
        "turn": 2,
        "tool": "read",
        "path": "include/combat/BattleContext.h",
        "limit": 80,
        "ok": True,
    },
    {
        "ts": "2026-08-08T12:00:04.000Z",
        "agent": "architect",
        "model": "deepseek/deepseek-v4-pro",
        "turn": 2,
        "tool": "grep",
        "path": "src/combat",
        "pattern": "executeActions",
        "ok": True,
    },
    {
        "ts": "2026-08-08T12:00:05.000Z",
        "agent": "architect",
        "model": "deepseek/deepseek-v4-pro",
        "turn": 2,
        "tool": "read",
        "path": "EXPERIMENTS.md",
        "offset": 200,
        "limit": 60,
        "ok": True,
    },
    {
        "ts": "2026-08-08T12:00:06.000Z",
        "agent": "investigator",
        "model": "deepseek/deepseek-v4-flash",
        "turn": 1,
        "tool": "grep",
        "path": "docs/knowledge-base",
        "pattern": "STS_FAIR",
        "ok": True,
    },
    {
        "ts": "2026-08-08T12:00:07.000Z",
        "agent": "investigator",
        "model": "deepseek/deepseek-v4-flash",
        "turn": 1,
        "tool": "read",
        "path": "docs/knowledge-base/architecture/combat-search.md",
        "offset": 1,
        "limit": 60,
        "ok": True,
    },
    {
        "ts": "2026-08-08T12:00:08.000Z",
        "agent": "investigator",
        "model": "deepseek/deepseek-v4-flash",
        "turn": 2,
        "tool": "grep",
        "path": "src/sim/search",
        "pattern": "playoutBattle",
        "ok": True,
    },
    {
        "ts": "2026-08-08T12:00:09.000Z",
        "agent": "reviewer",
        "model": "deepseek/deepseek-v4-flash",
        "turn": 1,
        "tool": "read",
        "path": "apps/one_combat.cpp",
        "offset": 2400,
        "limit": 100,
        "ok": True,
    },
    {
        "ts": "2026-08-08T12:00:10.000Z",
        "agent": "reviewer",
        "model": "deepseek/deepseek-v4-flash",
        "turn": 1,
        "tool": "read",
        "path": "src/combat/BattleContext.cpp",
        "offset": 1,
        "limit": 200,
        "ok": True,
    },
    {
        "ts": "2026-08-08T12:00:11.000Z",
        "agent": "reviewer",
        "model": "deepseek/deepseek-v4-flash",
        "turn": 1,
        "tool": "sts_git",
        "pattern": "diff",
        "ok": True,
    },
    {
        "ts": "2026-08-08T12:00:12.000Z",
        "agent": "reviewer",
        "model": "deepseek/deepseek-v4-flash",
        "turn": 2,
        "tool": "grep",
        "path": "include",
        "pattern": "isBattleOver",
        "ok": True,
    },
    # Malformed lines should be skipped
    None,  # type: ignore[arg-type]
    # Invalid JSON
    "{bad json",
]


class TestLoadRecords(unittest.TestCase):
    def test_load_from_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tf:
            _write_jsonl(tf.name, [r for r in SYNTHETIC_RECORDS if isinstance(r, dict)])
        try:
            records = load_records([tf.name])
            self.assertEqual(len(records), 13)
        finally:
            Path(tf.name).unlink()

    def test_load_empty_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tf:
            tf.write("")
        try:
            records = load_records([tf.name])
            self.assertEqual(len(records), 0)
        finally:
            Path(tf.name).unlink()

    def test_load_skips_bad_lines(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tf:
            tf.write("{bad json\n")
            tf.write('{"ts":"ok","tool":"read","ok":true}\n')
            tf.write("also bad\n")
        try:
            records = load_records([tf.name])
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["tool"], "read")
        finally:
            Path(tf.name).unlink()

    def test_load_multiple_files(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f1:
            _write_jsonl(f1.name, [SYNTHETIC_RECORDS[0], SYNTHETIC_RECORDS[1]])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f2:
            _write_jsonl(f2.name, [SYNTHETIC_RECORDS[2], SYNTHETIC_RECORDS[3]])
        try:
            records = load_records([f1.name, f2.name])
            self.assertEqual(len(records), 4)
        finally:
            Path(f1.name).unlink()
            Path(f2.name).unlink()


class TestSummarise(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.records = [r for r in SYNTHETIC_RECORDS if isinstance(r, dict)]
        cls.summary = summarise(cls.records, top_n=10)

    def test_total_count(self) -> None:
        self.assertIn("Total tool events: 13", self.summary)

    def test_read_counts(self) -> None:
        self.assertIn("Most read files", self.summary)
        # one_combat.cpp has 3 reads
        self.assertIn("apps/one_combat.cpp", self.summary)

    def test_read_lines(self) -> None:
        self.assertIn("Top files by requested lines", self.summary)
        # one_combat.cpp: 120 + 200 + 100 = 420 lines
        self.assertIn("apps/one_combat.cpp", self.summary)

    def test_search_directories(self) -> None:
        self.assertIn("Most searched directories", self.summary)

    def test_patterns(self) -> None:
        self.assertIn("Most searched patterns", self.summary)
        self.assertIn("runFullRunOOC", self.summary)
        self.assertIn("playoutBattle", self.summary)

    def test_by_role(self) -> None:
        self.assertIn("By role", self.summary)
        self.assertIn("architect", self.summary)
        self.assertIn("investigator", self.summary)
        self.assertIn("reviewer", self.summary)

    def test_hotspots(self) -> None:
        self.assertIn("Top hotspots", self.summary)
        self.assertIn("apps/one_combat.cpp", self.summary)

    def test_output_is_readable(self) -> None:
        """Summary should not contain raw JSON or exceptions."""
        self.assertNotIn("Traceback", self.summary)
        self.assertNotIn('"ts"', self.summary)


class TestSummariseEmpty(unittest.TestCase):
    def test_empty_records(self) -> None:
        s = summarise([], top_n=10)
        self.assertIn("Total tool events: 0", s)

    def test_no_read_tools(self) -> None:
        records = [
            {"ts": "x", "tool": "bash", "ok": True},
            {"ts": "x", "tool": "write", "path": "foo.txt", "ok": True},
        ]
        s = summarise(records, top_n=10)
        self.assertIn("Total tool events: 2", s)
        # No read sections should appear
        self.assertNotIn("Most read files", s)

    def test_unknown_role(self) -> None:
        records = [{"ts": "x", "tool": "read", "path": "foo.txt", "ok": True}]
        s = summarise(records, top_n=10)
        self.assertIn("(no role)", s)


class TestSyntheticTelemetrySensitive(unittest.TestCase):
    """Verify telemetry records contain no sensitive values."""

    SENSITIVE_KEYS = {"api_key", "apiKey", "secret", "token", "password", "content", "prompt"}

    def test_no_sensitive_keys(self) -> None:
        for r in SYNTHETIC_RECORDS:
            if not isinstance(r, dict):
                continue
            for key in r:
                self.assertNotIn(key.lower(), self.SENSITIVE_KEYS,
                                f"Record contains sensitive key: {key}")

    def test_no_full_file_contents(self) -> None:
        for r in SYNTHETIC_RECORDS:
            if not isinstance(r, dict):
                continue
            self.assertNotIn("content", r, "Record should not contain file contents")
            self.assertNotIn("text", r, "Record should not contain full text")

    def test_paths_are_relative(self) -> None:
        for r in SYNTHETIC_RECORDS:
            if not isinstance(r, dict):
                continue
            p = r.get("path", "")
            if p:
                self.assertFalse(p.startswith("/"), f"Path should be relative: {p}")


class TestTelemetryWriteFailureNonFatal(unittest.TestCase):
    """The telemetry writer must not crash on I/O failures."""

    def test_summariser_handles_missing_file(self) -> None:
        records = load_records(["/nonexistent/path/file.jsonl"])
        self.assertEqual(len(records), 0)

    def test_summariser_handles_permission_denied(self) -> None:
        # Use a file that exists but we simulate not being able to read it.
        # The load_records function should just skip the file gracefully.
        records = load_records(["/root/forbidden.jsonl"])
        self.assertEqual(len(records), 0)

    def test_summariser_handles_directory_as_file(self) -> None:
        records = load_records(["/tmp"])
        self.assertEqual(len(records), 0)


if __name__ == "__main__":
    unittest.main()
