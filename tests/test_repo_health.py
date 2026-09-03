import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import repo_health


class RepoHealthTests(unittest.TestCase):
    def test_classifies_policy_paths(self):
        self.assertIn("generated_or_build", repo_health.classify_path("build/result.json"))
        self.assertIn("docs_archive", repo_health.classify_path("docs/archive/old.md"))
        self.assertIn("session_decision_log", repo_health.classify_path("docs/knowledge-base/decision-log/2026-09-03-session.md"))
        self.assertIn("root_script", repo_health.classify_path("new_helper.py"))
        self.assertEqual(repo_health.classify_path("src/main.cpp"), set())

    def test_report_compares_tracked_paths_and_current_links(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            files = {
                "README.md": "[main](docs/current.md)\n",
                "docs/current.md": "current\n",
                "apps/one_combat.cpp": "int main() {}\n",
            }
            for name, content in files.items():
                path = repo / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repo, check=True)
            baseline = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, text=True, capture_output=True).stdout.strip()
            additions = {
                "build/new.o": "artifact",
                "docs/archive/new.md": "archive",
                "docs/knowledge-base/decision-log/2026-09-03-session.md": "decision",
                "new_helper.sh": "#!/bin/sh\n",
            }
            for name, content in additions.items():
                path = repo / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            (repo / "README.md").write_text("[missing](docs/missing.md)\n", encoding="utf-8")
            (repo / "docs/current.md").write_text("current\nmore\n", encoding="utf-8")
            (repo / "apps/one_combat.cpp").write_text("int main() {}\nmore\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            result = repo_health.report(repo, baseline)
            self.assertEqual(result["status"], "fail")
            self.assertEqual(result["hard_failures"]["generated_or_build"], ["build/new.o"])
            self.assertEqual(result["hard_failures"]["docs_archive"], ["docs/archive/new.md"])
            self.assertEqual(result["hard_failures"]["session_decision_log"], ["docs/knowledge-base/decision-log/2026-09-03-session.md"])
            self.assertEqual(result["hard_failures"]["broken_current_documentation_references"][0]["target"], "docs/missing.md")
            self.assertIn("new root-level one-off scripts", result["warnings"])
            self.assertIn("active Markdown growth", result["warnings"])
            self.assertIn("one_combat.cpp growth", result["warnings"])


if __name__ == "__main__":
    unittest.main()
