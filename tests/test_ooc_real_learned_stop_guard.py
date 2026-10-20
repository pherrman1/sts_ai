"""Seed-free startup regression for STS_OOC_MCTS_REAL_LEARNED_STOP.

Every case fails in configureLiveOocMcts or at the top of runFullRunOOC, before
the named seed plays a decision.
"""
import os
from pathlib import Path
import subprocess
import sys


def main():
    binary = Path(sys.argv[1]).resolve()
    repo = Path(__file__).resolve().parents[1]
    base = {key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ}
    mcts = {
        "STS_NATIVE_OOC": "1", "STS_OOC_MCTS": "1",
        "STS_OOC_STRATEGIC_TOK_NN": str(repo / "selfplay/models/ooc_strategic_tok_final.native"),
        "STS_OOC_MCTS_LEAF_VALUE": "native", "STS_OOC_MCTS_LEAF_COMBATS": "3",
        "STS_SILVER_ADAPTIVE": "0",
    }
    def fails_with(extra, expected, ascension="20"):
        command = ["bash", str(repo / "tools/seed_guard.sh"), str(binary), "bestbench", "10000", "1", ascension,
                   "46009000", "/tmp/ooc-real-learned-stop-invalid.csv"]
        result = subprocess.run(command, cwd=repo, env={**base, **extra}, text=True, capture_output=True)
        output = result.stdout + result.stderr
        assert result.returncode != 0 and expected in output, (extra, output[-2000:])

    fails_with({"STS_OOC_MCTS_REAL_LEARNED_STOP": "2"}, "STS_OOC_MCTS_REAL_LEARNED_STOP must be 0 or 1")
    fails_with({"STS_OOC_MCTS_REAL_LEARNED_STOP": "1"}, "STS_OOC_MCTS_REAL_LEARNED_STOP requires STS_OOC_MCTS=1")
    flag_on = {**mcts, "STS_OOC_MCTS_REAL_LEARNED_STOP": "1"}
    # Flat exact 10k is refused with the flag on.
    fails_with({**flag_on, "STS_SILVER_LEARNED_STOP": "0", "STS_SILVER_EXACT_ROOT_BUDGETS": "1"},
               "requires learned-stop Silver real")
    # Exact root budgets off would multiply imagined boss budgets.
    fails_with({**flag_on, "STS_SILVER_LEARNED_STOP": "1", "STS_SILVER_EXACT_ROOT_BUDGETS": "0"},
               "requires learned-stop Silver real")
    # Unset is on at A20 (ADR-TBD): flat exact 10k is refused, naming the =0 switch.
    fails_with({**mcts, "STS_SILVER_LEARNED_STOP": "0", "STS_SILVER_EXACT_ROOT_BUDGETS": "1"},
               "STS_OOC_MCTS_REAL_LEARNED_STOP=0 restores flat exact 10k")
    # =0 restores the exact-10k guard.
    fails_with({**mcts, "STS_OOC_MCTS_REAL_LEARNED_STOP": "0", "STS_SILVER_LEARNED_STOP": "1",
                "STS_SILVER_EXACT_ROOT_BUDGETS": "1"},
               "live OOC MCTS requires ordinary exact-10k Silver")
    # Below A20 unset stays off.
    fails_with({**mcts, "STS_SILVER_LEARNED_STOP": "1", "STS_SILVER_EXACT_ROOT_BUDGETS": "1"},
               "live OOC MCTS requires ordinary exact-10k Silver", ascension="0")
    print("PASS real-combat learned-stop guard")


if __name__ == "__main__":
    main()
