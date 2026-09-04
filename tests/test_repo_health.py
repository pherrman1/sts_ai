import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import repo_health


class RepoHealthTests(unittest.TestCase):
    def test_classification(self):
        self.assertIn("generated_or_build", repo_health.classify_path("build/result.json"))
        self.assertIn("generated_or_build", repo_health.classify_path("data/result.csv", ignored=True))
        self.assertIn("docs_archive", repo_health.classify_path("docs/archive/old.md"))
        self.assertIn("session_decision_log", repo_health.classify_path("docs/knowledge-base/decision-log/2026-09-04-session.md"))
        self.assertIn("root_script", repo_health.classify_path("new_helper.py"))

    def test_unchanged_pass_and_policy_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "repo-health-test"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "repo-health@example.invalid"], cwd=repo, check=True)
            for name, content in {
                "README.md": "[doc](docs/current.md)\n[dir](docs/)\n`[fake](missing.md)`\n```\n[also fake](missing.md)\n```\n",
                "docs/current.md": "current\n",
                "docs/index.txt": "not scanned: [missing](no.txt)\n",
                "apps/one_combat.cpp": "int main() {}\n",
                ".gitignore": "ignored/\n",
            }.items():
                path = repo / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repo, check=True)
            baseline = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, text=True, capture_output=True).stdout.strip()
            self.assertEqual(repo_health.report(repo, baseline)["status"], "pass")

            additions = {
                "ignored/new.csv": "local artifact\n",
                "build/new.o": "artifact\n",
                "docs/archive/new.md": "archive\n",
                "docs/knowledge-base/decision-log/2026-09-04-session.md": "decision\n",
                "new_helper.sh": "#!/bin/sh\n",
            }
            for name, content in additions.items():
                path = repo / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            (repo / "README.md").write_text("[missing](docs/missing.md)\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "add", "-f", "ignored/new.csv"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "candidate"], cwd=repo, check=True)
            result = repo_health.report(repo, baseline)
            self.assertEqual(result["status"], "fail")
            self.assertEqual(result["hard_failures"]["generated_or_build"], ["build/new.o", "ignored/new.csv"])
            self.assertEqual(result["hard_failures"]["docs_archive"], ["docs/archive/new.md"])
            self.assertEqual(result["hard_failures"]["session_decision_log"], ["docs/knowledge-base/decision-log/2026-09-04-session.md"])
            self.assertEqual(result["hard_failures"]["broken_current_documentation_references"][0]["target"], "docs/missing.md")
            self.assertIn("new root-level one-off scripts", result["warnings"])


if __name__ == "__main__":
    unittest.main()
