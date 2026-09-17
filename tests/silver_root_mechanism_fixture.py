"""Fixed fixtures only: never collects the scientific source population."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bridge")
    parser.add_argument("relabel")
    parser.add_argument("replay")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    env = {key: value for key, value in os.environ.items() if not key.startswith("STS_")}
    env.update(STS_SILVER_ADAPTIVE="0", STS_EXECUTABLE_GIT_SHA=sha)

    def run(*command, extra=None, success=True):
        completed = subprocess.run(["bash", str(repo / "tools/seed_guard.sh"), *map(str, command)],
                                   cwd=repo, env={**env, **(extra or {})}, capture_output=True, text=True)
        if (completed.returncode == 0) != success:
            raise AssertionError(completed.stdout + completed.stderr)
        return completed

    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        capture = temporary / "live.jsonl"
        control = run(args.bridge, "--capture-neutrality-fixture")
        assert not capture.exists()
        observed = run(args.bridge, "--capture-neutrality-fixture",
                       extra={"STS_SILVER_ROOT_MECHANISM_CAPTURE": str(capture)})
        assert control.stdout == observed.stdout
        assert control.stderr == observed.stderr
        captures = [json.loads(line) for line in capture.read_text().splitlines()]
        assert captures and len({row["root_id"] for row in captures}) == len(captures)
        assert all(row["state"]["state"]["inputState"] == 1
                   and row["state"]["state"]["outcome"] == 0
                   and len(row["actions"]) >= 2 for row in captures)
        run(args.bridge, "--capture-neutrality-fixture",
            extra={"STS_SILVER_ROOT_MECHANISM_CAPTURE": str(capture)}, success=False)
        roots, labels, replay = (temporary / name for name in ("roots.jsonl", "labels.jsonl", "replay.jsonl"))
        run(args.bridge, "--root-mechanism-fixture", roots)
        run(args.relabel, "--roots", roots, labels, "20260917", sha, "32")
        teachers = [json.loads(line) for line in labels.read_text().splitlines()]
        assert len(teachers) == 2 and teachers[0]["teacher_rng_identity"] != teachers[1]["teacher_rng_identity"]
        assert all(row["silver_config"]["reuse_cap_mode"] == "none"
                   and row["simulations_performed"] == 32 for row in teachers)
        changed_roots = [json.loads(roots.read_text().splitlines()[0])]
        changed_roots[0]["executable_git_sha"] = "0" * 40
        changed_root_path = temporary / "changed-root.jsonl"
        changed_root_path.write_text("".join(json.dumps(row) + "\n" for row in changed_roots))
        run(args.relabel, "--roots", changed_root_path, temporary / "root-sha-rejected.jsonl",
            "20260917", sha, success=False)
        run(args.replay, roots, labels, replay, "20260917", sha, "--fixture")
        rows = [json.loads(line) for line in replay.read_text().splitlines()]
        assert len(rows) == 24
        strict_replay = temporary / "strict-rejected.jsonl"
        run(args.replay, roots, labels, strict_replay, "20260917", sha, success=False)
        assert not strict_replay.exists()
        strict_labels = json.loads(json.dumps(teachers))
        for label in strict_labels:
            label["fixture_only"] = False
            label["budget"] = 10000 if label["replicate"] == "A" else 25000
            label["simulations_performed"] = label["budget"]
            label["silver_config"]["simulations_per_decision"] = label["budget"]
        strict_labels_path = temporary / "changed-teacher.jsonl"
        strict_labels_path.write_text("".join(json.dumps(row) + "\n" for row in strict_labels))
        teacher_sha_rejected = temporary / "teacher-sha-rejected.jsonl"
        root_sha = json.loads(roots.read_text().splitlines()[0])["executable_git_sha"]
        run(args.replay, roots, strict_labels_path, teacher_sha_rejected, "20260917", root_sha,
            success=False)
        assert not teacher_sha_rejected.exists()
        tie_labels = json.loads(json.dumps(teachers))
        for index, action in enumerate(tie_labels[0]["root_actions"]):
            action["original_root_corrected_q"] = 1.0 if index == 1 else -1.0
        for action in tie_labels[1]["root_actions"]:
            action["original_root_corrected_q"] = 0.0
        tie_labels_path = temporary / "tie-teacher.jsonl"
        tie_labels_path.write_text("".join(json.dumps(row) + "\n" for row in tie_labels))
        tie_replay = temporary / "tie-replay.jsonl"
        run(args.replay, roots, tie_labels_path, tie_replay, "20260917", sha, "--fixture")
        tie_rows = [json.loads(line) for line in tie_replay.read_text().splitlines()]
        assert all(row["b_regret"] == 0.0 and row["b_best"] for row in tie_rows)
        assert any(row["selected_action_fingerprint"] != row["b_best_action"] for row in tie_rows)
        for row in rows:
            native = row["native_order"]
            if row["arm"] in ("A", "E", "C"):
                assert row["replay_order"] == native
            teacher_actions = {item["action_fingerprint"]: item for item in teachers[0]["root_actions"]}
            expected_order = sorted(native, key=lambda key: -teacher_actions[key]["original_root_corrected_q"])
            if row["arm"] in ("B", "F", "D"):
                assert row["replay_order"] == expected_order
            if row["arm"] in ("E", "F"):
                assert row["priors"] == [1.0 / len(row["replay_order"])] * len(row["replay_order"])
            elif row["arm"] in ("C", "D"):
                total = sum(item["visits"] for item in teacher_actions.values())
                assert row["priors"] == [teacher_actions[key]["visits"] / total for key in row["replay_order"]]
            else:
                assert row["priors"] == []
        for replicate in range(4):
            assert len({row["search_seed"] for row in rows if row["replicate"] == replicate}) == 1
        changed = json.loads(json.dumps(teachers))
        changed[1]["root_actions"][0]["action_fingerprint"] = "invalid"
        invalid = temporary / "invalid.jsonl"
        invalid.write_text("".join(json.dumps(row) + "\n" for row in changed))
        run(args.replay, roots, invalid, temporary / "rejected.jsonl", "20260917", sha, "--fixture", success=False)
        assert not (temporary / "rejected.jsonl").exists()
        changed = json.loads(json.dumps(teachers))
        for action in changed[1]["root_actions"]:
            action["original_root_corrected_q"] = -action["original_root_corrected_q"]
        invalid.write_text("".join(json.dumps(row) + "\n" for row in changed))
        alternative = temporary / "alternative.jsonl"
        run(args.replay, roots, invalid, alternative, "20260917", sha, "--fixture")
        alternative_rows = [json.loads(line) for line in alternative.read_text().splitlines()]
        for original, changed_row in zip(rows, alternative_rows):
            for key in ("selected_action_fingerprint", "replay_order", "priors", "search_seed", "simulations"):
                assert original[key] == changed_row[key], key
        print(json.dumps({"fixed_fixture_only": True, "capture_neutral": True,
                          "teacher_records": 2, "fixture_budget": 32, "replay_rows": 24,
                          "teacher_b_treatment_neutral": True,
                          "hashes": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                     for path in (roots, labels, replay)}}))


if __name__ == "__main__":
    main()
