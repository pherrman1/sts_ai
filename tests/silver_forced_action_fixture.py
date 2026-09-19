"""Fixed one-root contract fixture; never scientific target evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    bridge, audit, analyzer = sys.argv[1:]
    repo = Path(__file__).resolve().parents[1]
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    env = {key: value for key, value in os.environ.items() if not key.startswith("STS_")}
    env.update(STS_EXECUTABLE_GIT_SHA=sha, STS_SILVER_ADAPTIVE="0")
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        roots, raw, report = (tmp / name for name in ("roots.jsonl", "audit.jsonl", "report.json"))
        subprocess.run(["bash", str(repo / "tools/seed_guard.sh"), bridge,
                        "--root-mechanism-fixture", str(roots)], cwd=repo, env=env, check=True)
        subprocess.run(["bash", str(repo / "tools/seed_guard.sh"), audit, str(roots), str(raw),
                        "20260919", sha, "--fixture", "8", "16", "2"],
                       cwd=repo, env=env, check=True)
        rows = [json.loads(line) for line in raw.read_text().splitlines()]
        assert rows and {row["estimator"] for row in rows} == {"L", "J"}
        assert all(row["fixture_only"] and row["population"] == "primary"
                   and row["simulations"] == (0 if row["terminal_after_action"]
                                               else row["continuation_budget"])
                   and row["root_outcome_rng_identity"] == row["continuation_rng_identity"]
                   and row["continuation_rng_counter"] == row["immediate_rng_counter_after"]
                   for row in rows)
        for estimator in ("L", "J"):
            for replicate in range(2):
                identities = {row["rng_identity"] for row in rows
                              if row["estimator"] == estimator and row["replicate"] == replicate}
                assert len(identities) == 1
        subprocess.run([sys.executable, analyzer, "analyze", str(raw), str(report), "--fixture"],
                       cwd=repo, check=True)
        result = json.loads(report.read_text())
        assert result["roots"] == 1 and result["source_seeds"] == 1
        print(json.dumps({"fixed_fixture_only": True, "rows": len(rows),
                          "classification": result["classification"]}))


if __name__ == "__main__":
    main()
