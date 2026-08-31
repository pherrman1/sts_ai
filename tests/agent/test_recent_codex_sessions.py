import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "agent" / "recent_codex_sessions.py"


def load_module():
    spec = importlib.util.spec_from_file_location("recent_codex_sessions", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecentCodexSessionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "sts_ai"
        self.project.mkdir()
        self.codex_home = self.root / ".codex"
        self.module = load_module()

    def write_session(self, bucket, session_id, timestamp, cwd=None, body="SECRET BODY"):
        directory = self.codex_home / bucket / "2026" / "08"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{session_id}.jsonl"
        meta = {
            "timestamp": timestamp,
            "type": "session_meta",
            "payload": {
                "session_id": session_id,
                "timestamp": timestamp,
                "cwd": str(cwd or self.project),
            },
        }
        path.write_text(json.dumps(meta) + "\n" + json.dumps({"body": body}) + "\n", encoding="utf-8")
        return path

    def test_discovers_active_and_archived_newest_first(self):
        older = self.write_session("sessions", "active", "2026-08-30T10:00:00Z")
        newer = self.write_session("archived_sessions", "archived", "2026-08-31T10:00:00Z")
        result = self.module.discover(self.project, self.codex_home, 5)
        self.assertEqual([item["path"] for item in result], [str(newer.resolve()), str(older.resolve())])

    def test_filters_other_projects_and_accepts_linked_worktree(self):
        linked = self.project / ".worktrees" / "task"
        linked.mkdir(parents=True)
        self.write_session("sessions", "match", "2026-08-31T10:00:00Z", self.project)
        self.write_session("sessions", "other", "2026-08-31T11:00:00Z", self.root / "other")
        result = self.module.discover(linked, self.codex_home, 5)
        self.assertEqual([Path(item["path"]).stem for item in result], ["match"])

    def test_deduplicates_session_id_and_prefers_active(self):
        archived = self.write_session("archived_sessions", "same", "2026-08-31T10:00:00Z")
        active = self.write_session("sessions", "same", "2026-08-31T10:00:00Z")
        result = self.module.discover(self.project, self.codex_home, 5)
        self.assertEqual(result[0]["path"], str(active.resolve()))
        self.assertNotEqual(result[0]["path"], str(archived.resolve()))

    def test_missing_directories_fail_clearly(self):
        with self.assertRaisesRegex(self.module.SessionDiscoveryError, "no usable"):
            self.module.discover(self.project, self.codex_home, 5)

    def test_malformed_metadata_is_skipped_safely(self):
        directory = self.codex_home / "sessions"
        directory.mkdir(parents=True)
        (directory / "bad.jsonl").write_text("not json\nSECRET BODY", encoding="utf-8")
        good = self.write_session("sessions", "good", "2026-08-31T10:00:00Z")
        result = self.module.discover(self.project, self.codex_home, 5)
        self.assertEqual(result[0]["path"], str(good.resolve()))

    def test_json_output_contains_metadata_not_transcript_body(self):
        self.write_session("sessions", "safe", "2026-08-31T10:00:00Z", body="DO_NOT_EMIT")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = self.module.main([
                "--project", str(self.project), "--limit", "5", "--json",
                "--codex-home", str(self.codex_home),
            ])
        self.assertEqual(rc, 0)
        rendered = output.getvalue()
        self.assertNotIn("DO_NOT_EMIT", rendered)
        self.assertEqual(set(json.loads(rendered)[0]), {"path", "started_at", "cwd", "size_bytes"})


if __name__ == "__main__":
    unittest.main()
