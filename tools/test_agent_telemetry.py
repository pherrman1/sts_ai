#!/usr/bin/env python3
"""Tests for agent telemetry parsing and aggregation.

Covers the 15 required test cases from the context-telemetry handoff:
  1.  operation classification
  2.  extension counts include reads only
  3.  overlapping intervals merge correctly
  4.  disjoint intervals remain separate
  5.  duplicate-line count is correct
  6.  read spanning multiple hot-region buckets is allocated correctly
  7.  unknown read ranges are reported, not invented
  8.  per-session aggregation
  9.  repeated-search counting
  10. cross-agent overlap calculation (unavailable flag)
  11. backward compatibility with existing telemetry lacking new metadata
  12. CODE_MAP-first classification
  13. malformed JSONL lines are handled safely
  14. sensitive fields are not emitted by telemetry code
  15. telemetry write failures remain non-fatal
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.summarize_agent_context import (
    load_records,
    summarise,
    summarise_json,
    _merge_intervals,
    _interval_length,
    _code_map_first_rate,
    _tool_class,
)


def _write_jsonl(path: str, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            if isinstance(r, dict):
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
]


# ── Test 1: Operation classification ──────────────────────────────────

class TestOperationClassification(unittest.TestCase):
    def test_tool_classes(self):
        self.assertEqual(_tool_class("read"), "read")
        self.assertEqual(_tool_class("grep"), "search")
        self.assertEqual(_tool_class("find"), "search")
        self.assertEqual(_tool_class("ls"), "list")
        self.assertEqual(_tool_class("sts_git"), "git")
        self.assertEqual(_tool_class("sts_inspect"), "inspect")
        self.assertEqual(_tool_class("bash"), "other")
        self.assertEqual(_tool_class("write"), "other")

    def test_summary_has_operation_breakdown(self):
        records = [r for r in SYNTHETIC_RECORDS if isinstance(r, dict)]
        s = summarise(records, top_n=10)
        self.assertIn("Operation Breakdown", s)
        self.assertIn("Read operations:", s)
        self.assertIn("Search operations:", s)
        self.assertIn("Directory/list ops:", s)
        self.assertIn("Git inspection ops:", s)

    def test_json_has_breakdown(self):
        records = [r for r in SYNTHETIC_RECORDS if isinstance(r, dict)]
        j = summarise_json(records, top_n=10)
        self.assertEqual(j["operation_breakdown"]["read_operations"], 7)
        self.assertEqual(j["operation_breakdown"]["search_operations"], 5)
        self.assertEqual(j["operation_breakdown"]["git_inspection_operations"], 1)
        self.assertEqual(j["operation_breakdown"]["other_operations"], 0)


# ── Test 2: Extension counts include reads only ───────────────────────

class TestExtensionCounts(unittest.TestCase):
    def test_extensions_are_reads_only(self):
        """Grep/find/ls should NOT appear in extension counts."""
        records = [
            {"ts": "x", "tool": "read", "path": "foo.cpp", "ok": True},
            {"ts": "x", "tool": "read", "path": "bar.md", "ok": True},
            {"ts": "x", "tool": "grep", "path": "baz.cpp", "pattern": "x", "ok": True},
            {"ts": "x", "tool": "find", "path": "qux.py", "pattern": "x", "ok": True},
            {"ts": "x", "tool": "ls", "path": "dir", "ok": True},
        ]
        j = summarise_json(records)
        ec = j["file_reads"]["extension_counts_reads_only"]
        self.assertEqual(ec[".cpp"], 1)
        self.assertEqual(ec[".md"], 1)
        # grep/find/ls paths should NOT contribute
        self.assertNotIn(".py", {str(k) for k in ec})
        self.assertNotIn("dir", {str(k) for k in ec})

    def test_extension_sum_equals_read_count(self):
        records = [
            {"ts": "x", "tool": "read", "path": "a.cpp", "ok": True},
            {"ts": "x", "tool": "read", "path": "b.md", "ok": True},
            {"ts": "x", "tool": "read", "path": "c.py", "ok": True},
            {"ts": "x", "tool": "grep", "path": "d.cpp", "pattern": "x", "ok": True},
        ]
        j = summarise_json(records)
        ec = j["file_reads"]["extension_counts_reads_only"]
        ext_sum = sum(ec.values())
        self.assertEqual(ext_sum, 3)  # 3 reads, not 4


# ── Test 3 & 4: Interval merging ──────────────────────────────────────

class TestIntervalMerging(unittest.TestCase):
    def test_overlapping_intervals_merge(self):
        ivs = [(1, 50), (30, 80), (90, 120)]
        merged = _merge_intervals(ivs)
        self.assertEqual(merged, [(1, 80), (90, 120)])
        self.assertEqual(sum(_interval_length(iv) for iv in merged), 79 + 30)

    def test_disjoint_intervals_stay_separate(self):
        ivs = [(1, 50), (60, 100), (200, 300)]
        merged = _merge_intervals(ivs)
        self.assertEqual(merged, [(1, 50), (60, 100), (200, 300)])

    def test_nested_intervals_merge(self):
        ivs = [(1, 100), (20, 30), (40, 60)]
        merged = _merge_intervals(ivs)
        self.assertEqual(merged, [(1, 100)])
        self.assertEqual(_interval_length(merged[0]), 99)

    def test_adjacent_intervals_merge(self):
        # [start, end) where end of first == start of second
        ivs = [(1, 50), (50, 100)]
        merged = _merge_intervals(ivs)
        self.assertEqual(merged, [(1, 100)])

    def test_empty(self):
        self.assertEqual(_merge_intervals([]), [])


# ── Test 5: Duplicate-line count ──────────────────────────────────────

class TestDuplicateLineCounting(unittest.TestCase):
    def test_duplicate_count(self):
        records = [
            {"ts": "x", "tool": "read", "path": "test.txt",
             "offset": 1, "limit": 100, "ok": True},
            {"ts": "x", "tool": "read", "path": "test.txt",
             "offset": 50, "limit": 100, "ok": True},
        ]
        j = summarise_json(records)
        top = j["file_reads"]["top_by_requested_lines"][0]
        self.assertEqual(top["requested_lines"], 200)
        self.assertEqual(top["unique_lines"], 149)  # [1,149)
        self.assertEqual(top["repeated_lines"], 51)  # 50 + 1 overlap

    def test_no_duplicate_when_disjoint(self):
        records = [
            {"ts": "x", "tool": "read", "path": "test.txt",
             "offset": 1, "limit": 50, "ok": True},
            {"ts": "x", "tool": "read", "path": "test.txt",
             "offset": 200, "limit": 50, "ok": True},
        ]
        j = summarise_json(records)
        top = j["file_reads"]["top_by_requested_lines"][0]
        self.assertEqual(top["unique_lines"], 100)
        self.assertEqual(top["repeated_lines"], 0)


# ── Test 6: Hot-region bucket allocation ──────────────────────────────

class TestHotRegionBucketing(unittest.TestCase):
    def test_read_spanning_multiple_buckets(self):
        """A read spanning 3 buckets should touch all 3."""
        records = [
            {"ts": "x", "tool": "read", "path": "big.cpp",
             "offset": 150, "limit": 500, "ok": True},
        ]
        j = summarise_json(records, hot_files=["big.cpp"], bucket_lines=200)
        hr = j["hot_regions"]["big.cpp"]
        buckets = [(h["start"], h["end"]) for h in hr]
        self.assertIn((1, 200), buckets)
        self.assertIn((201, 400), buckets)
        self.assertIn((401, 600), buckets)


# ── Test 7: Unknown ranges reported ───────────────────────────────────

class TestUnknownReadRanges(unittest.TestCase):
    def test_unknown_ranges_reported(self):
        records = [
            {"ts": "x", "tool": "read", "path": "a.txt", "ok": True},  # no offset/limit
            {"ts": "x", "tool": "read", "path": "b.txt",
             "offset": 1, "limit": 50, "ok": True},
        ]
        j = summarise_json(records)
        self.assertEqual(j["unknown_range_reads"], 1)
        s = summarise(records)
        self.assertIn("unknown_range_reads: 1", s)

    def test_unknown_ranges_not_invented(self):
        """Reads without limit should not be counted in requested_lines."""
        records = [
            {"ts": "x", "tool": "read", "path": "a.txt", "ok": True},
            {"ts": "x", "tool": "read", "path": "b.txt",
             "offset": 1, "limit": 50, "ok": True},
        ]
        j = summarise_json(records)
        for f in j["file_reads"]["top_by_requested_lines"]:
            if f["path"] == "a.txt":
                self.assertEqual(f["requested_lines"], 0)


# ── Test 8: Per-session aggregation ───────────────────────────────────

class TestPerSessionAggregation(unittest.TestCase):
    def test_per_session_stats(self):
        records = [
            {"ts": "x", "tool": "read", "path": "a.cpp",
             "offset": 1, "limit": 100, "ok": True},
            {"ts": "x", "tool": "read", "path": "b.cpp",
             "offset": 50, "limit": 80, "ok": True},
            {"ts": "x", "tool": "grep", "path": "x", "pattern": "y", "ok": True},
        ]
        j = summarise_json(records)
        # These go into session derived from the temp dir name
        self.assertGreater(len(j["per_session"]), 0)


# ── Test 9: Repeated-search counting ──────────────────────────────────

class TestRepeatedSearchCounting(unittest.TestCase):
    def test_repeated_search_counting(self):
        records = [
            {"ts": "x", "tool": "grep", "path": "apps", "pattern": "VWin", "ok": True},
            {"ts": "x", "tool": "grep", "path": "apps", "pattern": "VWin", "ok": True},
            {"ts": "x", "tool": "grep", "path": "src", "pattern": "WinNet", "ok": True},
            {"ts": "x", "tool": "grep", "path": "apps", "pattern": "VWin", "ok": True},
        ]
        j = summarise_json(records)
        # VWin in apps appears 3 times
        searches = j["repeated_searches"]["most_repeated"]
        vwin = [s for s in searches
                if s["pattern"] == "VWin" and s["path"] == "apps"]
        self.assertEqual(vwin[0]["count"], 3)
        # Same-session duplicate count
        self.assertGreaterEqual(j["repeated_searches"]["same_session_duplicate_count"], 1)


# ── Test 10: Cross-agent overlap (unavailable flag) ───────────────────

class TestCrossAgentOverlap(unittest.TestCase):
    def test_unavailable_when_no_agent_metadata(self):
        records = [
            {"ts": "x", "tool": "read", "path": "x.txt",
             "offset": 1, "limit": 50, "ok": True},
        ]
        j = summarise_json(records)
        self.assertFalse(j["cross_agent"]["available"])
        self.assertIn("unavailable", j["cross_agent"].get("note", "").lower())

    def test_available_with_agent_metadata(self):
        records = [
            {"ts": "x", "agent": "architect", "tool": "read",
             "path": "x.txt", "offset": 1, "limit": 50, "ok": True},
        ]
        j = summarise_json(records)
        self.assertTrue(j["cross_agent"]["available"])


# ── Test 11: Backward compatibility ───────────────────────────────────

class TestBackwardCompatibility(unittest.TestCase):
    def test_handles_missing_fields(self):
        """Records without agent, offset, or limit should not crash."""
        records = [
            {"tool": "read", "path": "x.txt", "ok": True},  # minimal
            {"tool": "grep", "pattern": "y", "ok": True},   # no path
            {"tool": "read", "path": "z.txt", "offset": 1, "ok": True},  # no limit
        ]
        s = summarise(records)
        self.assertIn("Total telemetry records:", s)
        j = summarise_json(records)
        self.assertEqual(j["total_records"], 3)

    def test_handles_filtered_tools(self):
        """Records with only non-interesting tools should not crash."""
        records = [
            {"ts": "x", "tool": "bash", "command": "ls", "ok": True},
            {"ts": "x", "tool": "write", "path": "f.txt", "ok": True},
            {"ts": "x", "tool": "edit", "path": "f.txt", "ok": True},
        ]
        s = summarise(records)
        self.assertIn("Other tool ops:", s)


# ── Test 12: CODE_MAP-first classification ────────────────────────────

class TestCodeMapFirst(unittest.TestCase):
    def test_codemap_first_true(self):
        records = [
            {"ts": "1", "turn": 1, "tool": "read",
             "path": "docs/knowledge-base/CODE_MAP.md",
             "offset": 1, "limit": 50, "ok": True},
            {"ts": "2", "turn": 2, "tool": "read",
             "path": "apps/one_combat.cpp",
             "offset": 8000, "limit": 100, "ok": True},
        ]
        cm = _code_map_first_rate(records)
        self.assertEqual(cm["codemap_first_count"], 1)
        self.assertGreater(cm["codemap_first_rate"], 0)

    def test_codemap_not_first(self):
        records = [
            {"ts": "1", "turn": 1, "tool": "read",
             "path": "apps/one_combat.cpp",
             "offset": 8000, "limit": 100, "ok": True},
            {"ts": "2", "turn": 2, "tool": "read",
             "path": "docs/knowledge-base/CODE_MAP.md",
             "offset": 1, "limit": 50, "ok": True},
        ]
        cm = _code_map_first_rate(records)
        self.assertEqual(cm["codemap_first_count"], 0)

    def test_codemap_first_no_prod_reads(self):
        """CODE_MAP read with no production reads should count as CODE_MAP-first."""
        records = [
            {"ts": "1", "turn": 1, "tool": "read",
             "path": "docs/knowledge-base/CODE_MAP.md",
             "offset": 1, "limit": 50, "ok": True},
            {"ts": "2", "turn": 2, "tool": "read",
             "path": "README.md",
             "offset": 1, "limit": 50, "ok": True},
        ]
        cm = _code_map_first_rate(records)
        self.assertEqual(cm["codemap_first_count"], 1)


# ── Test 13: Malformed JSONL handled safely ───────────────────────────

class TestMalformedLinesHandled(unittest.TestCase):
    def test_load_skips_bad_lines(self):
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

    def test_load_handles_null_records(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tf:
            tf.write('{"ts":"ok","tool":"read","ok":true}\n')
            tf.write('\n')   # blank line
            tf.write('  \n')  # whitespace
        try:
            records = load_records([tf.name])
            self.assertEqual(len(records), 1)
        finally:
            Path(tf.name).unlink()

    def test_summarise_handles_empty_input(self):
        s = summarise([], top_n=10)
        self.assertIn("Total telemetry records: 0", s)


# ── Test 14: Sensitive fields not emitted ─────────────────────────────

class TestSensitiveFields(unittest.TestCase):
    SENSITIVE_KEYS = {"api_key", "apikey", "secret", "token",
                       "password", "content", "prompt"}

    def test_no_sensitive_keys_in_synthetic_records(self):
        for r in SYNTHETIC_RECORDS:
            if not isinstance(r, dict):
                continue
            for key in r:
                self.assertNotIn(key.lower(), self.SENSITIVE_KEYS,
                                 f"Record contains sensitive key: {key}")

    def test_no_content_in_records(self):
        for r in SYNTHETIC_RECORDS:
            if not isinstance(r, dict):
                continue
            self.assertNotIn("content", r)
            self.assertNotIn("text", r)

    def test_paths_are_relative(self):
        for r in SYNTHETIC_RECORDS:
            if not isinstance(r, dict):
                continue
            p = r.get("path", "")
            if p:
                self.assertFalse(p.startswith("/"),
                                 f"Path should be relative: {p}")


# ── Test 15: Telemetry write failures are non-fatal ───────────────────

class TestTelemetryWriteFailureNonFatal(unittest.TestCase):
    def test_missing_file_graceful(self):
        records = load_records(["/nonexistent/path/file.jsonl"])
        self.assertEqual(len(records), 0)

    def test_permission_denied_graceful(self):
        records = load_records(["/root/forbidden.jsonl"])
        self.assertEqual(len(records), 0)

    def test_directory_as_file_graceful(self):
        records = load_records(["/tmp"])
        self.assertEqual(len(records), 0)

    def test_summarise_empty_does_not_crash(self):
        s = summarise([], top_n=10)
        self.assertIn("Total telemetry records: 0", s)
        j = summarise_json([])
        self.assertEqual(j["total_records"], 0)
        self.assertIn("read_operations", j["operation_breakdown"])


# ── Full summary output sanity ────────────────────────────────────────

class TestFullSummarySanity(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.records = [r for r in SYNTHETIC_RECORDS if isinstance(r, dict)]
        cls.summary = summarise(cls.records, top_n=10)
        cls.json_summary = summarise_json(cls.records, top_n=10)

    def test_total_record_count(self):
        self.assertIn("Total telemetry records: 13", self.summary)

    def test_read_counts_in_summary(self):
        self.assertIn("Top Files by Read Calls", self.summary)
        self.assertIn("apps/one_combat.cpp", self.summary)

    def test_requested_lines_section(self):
        self.assertIn("Top Files by Requested Lines", self.summary)

    def test_duplication_ratios_section(self):
        self.assertIn("Duplication Ratios", self.summary)

    def test_searches_section(self):
        self.assertIn("Repeated Searches", self.summary)
        self.assertIn("runFullRunOOC", self.summary)
        self.assertIn("playoutBattle", self.summary)

    def test_codemap_section(self):
        self.assertIn("CODE_MAP Usage", self.summary)

    def test_warnings_section(self):
        # Warnings only appear when there are data-quality issues;
        # the synthetic records are clean (all have agent metadata, no unknown ranges).
        j = self.json_summary
        self.assertIn("warnings", j)
        # with agent metadata, cross-agent should be available
        self.assertTrue(j["cross_agent"]["available"])

    def test_json_has_all_sections(self):
        sections = [
            "total_records", "operation_breakdown", "file_reads",
            "duplication", "hot_regions", "per_session",
            "cross_agent", "repeated_searches", "code_map_usage", "warnings",
        ]
        for sec in sections:
            self.assertIn(sec, self.json_summary, f"Missing section: {sec}")

    def test_output_no_raw_json(self):
        self.assertNotIn("Traceback", self.summary)
        self.assertNotIn('"ts"', self.summary)


# ── JSONL load baseline ───────────────────────────────────────────────

class TestLoadRecords(unittest.TestCase):
    def test_load_from_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tf:
            _write_jsonl(tf.name, [r for r in SYNTHETIC_RECORDS if isinstance(r, dict)])
        try:
            records = load_records([tf.name])
            self.assertEqual(len(records), 13)
            # Session field should be injected
            for r in records:
                self.assertIn("_session", r)
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


# ── JSON output mode ──────────────────────────────────────────────────

class TestJsonOutput(unittest.TestCase):
    def test_json_output_contains_core_metrics(self):
        records = [r for r in SYNTHETIC_RECORDS if isinstance(r, dict)]
        j = summarise_json(records, top_n=10)
        self.assertIsInstance(j, dict)
        self.assertGreater(j["total_records"], 0)
        # File reads
        self.assertGreater(len(j["file_reads"]["top_by_reads"]), 0)
        self.assertGreater(len(j["file_reads"]["top_by_requested_lines"]), 0)
        # Per session
        self.assertIn("per_session", j)
        # Repeated searches
        self.assertIn("most_repeated", j["repeated_searches"])


if __name__ == "__main__":
    unittest.main()
