"""Seed-free replay-probe startup refusals; every invocation rejects before play."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    binary = Path(sys.argv[1]).resolve()
    repo = Path(__file__).resolve().parents[1]
    base = {key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ}
    base.update({
        "OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE",
        "STS_NATIVE_OOC": "1", "STS_OOC_MCTS": "1",
        "STS_OOC_STRATEGIC_TOK_NN": str(repo / "selfplay/models/ooc_strategic_tok_final.native"),
        "STS_OOC_MCTS_LEAF_VALUE": "native", "STS_OOC_MCTS_LEAF_COMBATS": "3",
        "STS_OOC_MCTS_SIMS": "4096", "STS_OOC_MCTS_PRIOR": "policy",
        "STS_OOC_MCTS_LEAF_POLICY": "v4",
    })
    prefix = ["bash", str(repo / "tools/seed_guard.sh"), str(binary), "oocleafreplayprobe"]
    valid_args = ["1", "87000000", "20"]
    teacher_error = "replay_requires_a20_native_4096_rollout3_v4_teacher"
    with tempfile.TemporaryDirectory(prefix="sts-leaf-replay-startup-") as directory:
        def reject(label, args, reason, changes=None, capture=True, probe_error=False):
            folder = Path(directory) / label
            folder.mkdir()
            output = folder / "capture.jsonl"
            trace, profile, mcts = (folder / name for name in ("game.trace.jsonl", "game.profile.jsonl", "mcts.csv"))
            env = {**base, **(changes or {}), "STS_OOC_DECISION_TRACE": str(trace),
                   "STS_RUN_PROFILE": str(profile), "STS_OOC_MCTS_TRACE": str(mcts)}
            # These outputs are forbidden by the probe too: if an earlier gate
            # regresses, their later refusal prevents accidentally starting play.
            if capture:
                env["STS_OOC_MCTS_LEAF_CAPTURE"] = str(output)
            result = subprocess.run(prefix + args, cwd=repo, env=env, text=True,
                                    capture_output=True, timeout=30)
            diagnostic = result.stdout + result.stderr
            assert result.returncode != 0 and reason in diagnostic, (label, result.returncode, diagnostic)
            if output.exists():
                rows = [json.loads(line) for line in output.read_text().splitlines()]
                assert rows[0]["type"] == "header", (label, rows)
                assert len(rows) == (2 if probe_error else 1), (label, rows)
                if probe_error:
                    failure = rows[1]
                    assert failure["type"] == "replay_probe" and failure["status"] == "INVALID", (label, failure)
                    assert failure["reason"] == reason and failure["gameplayResult"] is None, (label, failure)
            else:
                assert not capture or reason.startswith("SEED_GUARD:"), label
            for path in (trace, profile, mcts, Path(str(mcts) + ".actions.jsonl"), Path(str(mcts) + ".support.jsonl")):
                assert not path.exists() or not path.read_bytes(), (label, "unexpected gameplay output", path)

        for count in ("0", "2", "01", "invalid"):
            reject("count-" + count, [count, "87000000", "20"],
                   "SEED_GUARD: oocleafreplayprobe requires exactly one source seed")
        reject("missing-asc", valid_args[:-1], "usage: one_combat oocleafreplayprobe 1 SEED ASC")
        reject("extra-argument", valid_args + ["extra"], "usage: one_combat oocleafreplayprobe 1 SEED ASC")
        reject("malformed-seed", ["1", "invalid", "20"], "oocleafreplayprobe:")
        reject("malformed-asc", ["1", "87000000", "invalid"], "oocleafreplayprobe:")
        for label, seed, asc in (("negative-seed", "-1", "20"), ("seed-suffix", "87000000x", "20"),
                                 ("negative-asc", "87000000", "-1"), ("asc-suffix", "87000000", "20x")):
            reject(label, ["1", seed, asc], "seed and ascension must be nonnegative integers")
        reject("missing-capture", valid_args, "replay_requires_finalized_capture_sink", capture=False)
        reject("wrong-sims", valid_args, teacher_error, {"STS_OOC_MCTS_SIMS": "1024"}, probe_error=True)
        reject("wrong-horizon", valid_args, teacher_error, {"STS_OOC_MCTS_LEAF_COMBATS": "1"}, probe_error=True)
        reject("wrong-asc", ["1", "87000000", "0"], teacher_error, probe_error=True)
    print("PASS replay startup: malformed arguments/counts, missing capture, teacher gates, no gameplay output")


if __name__ == "__main__":
    main()
