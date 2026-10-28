"""Seed-free startup regression for the ADR-0057 leaf calibration default (STS_OOC_MCTS_LEAF_CALIBRATION).

Each case reads the live OOC MCTS startup banner. Flat exact-10k Silver makes runFullRunOOC refuse the A20 run
right after configureLiveOocMcts, before the named seed plays a decision.
"""
import os
from pathlib import Path
import subprocess
import sys

M0 = [-2.5384, -2.9227, -3.6523, -3.6334, 1.0535]
SCOPE = "leaf_calibration_min_ascension=20"


def calibration(line):
    """The banner's leaf_calibration=a1,a2,a3,a4:b (printed at precision 17) as floats, or None."""
    field = next((f for f in line.split() if f.startswith("leaf_calibration=")), None)
    if field is None:
        return None
    return [float(x) for x in field.split("=", 1)[1].rstrip("]").replace(":", ",").split(",")]


def main():
    binary = Path(sys.argv[1]).resolve()
    repo = Path(__file__).resolve().parents[1]
    base = {key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ}
    mcts = {
        "STS_NATIVE_OOC": "1", "STS_OOC_MCTS": "1",
        "STS_OOC_STRATEGIC_TOK_NN": str(repo / "selfplay/models/ooc_strategic_tok_final.native"),
        "STS_OOC_MCTS_LEAF_VALUE": "native", "STS_OOC_MCTS_LEAF_COMBATS": "3",
        "STS_SILVER_ADAPTIVE": "0", "STS_SILVER_LEARNED_STOP": "0", "STS_SILVER_EXACT_ROOT_BUDGETS": "1",
    }

    def banner(extra):
        command = ["bash", str(repo / "tools/seed_guard.sh"), str(binary), "bestbench", "10000", "1", "20",
                   "46009000", "/tmp/ooc-leaf-calibration-default.csv"]
        result = subprocess.run(command, cwd=repo, env={**base, **mcts, **extra}, text=True, capture_output=True,
                                timeout=600)
        output = result.stdout + result.stderr
        lines = [line for line in output.splitlines() if line.startswith("[live OOC MCTS ON")]
        assert len(lines) == 1 and "restores flat exact 10k" in output, (extra, output[-2000:])
        return lines[0]

    # Unset: the plain rollout3 X2-B leaf takes M0, scoped to ascension 20, also with the pinned public X2-B named.
    for extra in ({}, {"STS_WIN_NET": "models/candidates/v_win_x2b_public_trees.txt"}):
        line = banner(extra)
        assert calibration(line) == M0 and SCOPE in line, (extra, line)
    # =0, another leaf count, the sibling capture and another win model (B0) keep the raw anchor.
    for extra in ({"STS_OOC_MCTS_LEAF_CALIBRATION": "0"}, {"STS_OOC_MCTS_LEAF_COMBATS": "1"},
                  {"STS_OOC_SIBLING_CAPTURE": "/tmp/ooc-leaf-calibration-default-sibling.jsonl"},
                  {"STS_WIN_NET": "1"}):
        line = banner(extra)
        assert calibration(line) is None and SCOPE not in line, (extra, line)
    # The #886 mono capture keeps the default, so its games replay the uncaptured ones.
    line = banner({"STS_OOC_SIBLING_CAPTURE": "/tmp/ooc-leaf-calibration-default-sibling.jsonl",
                   "STS_OOC_SIBLING_MONO": "1"})
    assert calibration(line) == M0 and SCOPE in line, line
    # An explicit value is the research option: every ascension, no scope.
    line = banner({"STS_OOC_MCTS_LEAF_CALIBRATION": "-2.5,-2.9,-3.6,-3.7:1.05"})
    assert calibration(line) == [-2.5, -2.9, -3.6, -3.7, 1.05] and SCOPE not in line, line
    print("PASS leaf calibration default")


if __name__ == "__main__":
    main()
