"""Learner check of the arch screen (PREREG.md "Binding under B"), on the PC GPU before any arm runs.

    python3 learner_check.py SCREEN2_LOCAL SCRATCH [--micro-batch 192] [--device cuda]

Forks screen 2's BASE at update 30 with every arch flag off (`ppo_cloud.py init --fork-dir`, learner argv = BASE's
own, read from its config) into a scratch store and directory, trains the fork's first update (iteration 30, on
BASE's kept iteration-30 parts) exactly as `serve` does (ArmLearner.step, serve's --micro-batch override), and
compares the result with BASE's net-0031.bin. Prints LEARNER_CHECK_OK or LEARNER_CHECK_FAIL with both sha256 and the
max |delta parameter|; the scratch directory is left for inspection. SCRATCH must not exist yet.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "tools", "heart1"))
import ppo_cloud  # noqa: E402
from ppo_model import PolicyNet  # noqa: E402

SCREEN2_ENV = os.path.join(HERE, "..", "ppo_reward_screen_20261103", "actors_frozen.env")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("screen2_local")
    ap.add_argument("scratch")
    ap.add_argument("--micro-batch", type=int, default=192, help="screen 2's serve --micro-batch")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--fork-at", type=int, default=30)
    a = ap.parse_args()
    if os.path.exists(a.scratch):
        sys.exit(f"{a.scratch} exists")
    src = os.path.join(a.screen2_local, "BASE")
    cfg = json.load(open(os.path.join(src, "config.json")))
    n = a.fork_at
    store = "dir:" + os.path.join(a.scratch, "store")
    local = os.path.join(a.scratch, "local")
    ppo_cloud.cmd_init([store, "FORKCHECK", "--fork-dir", src, "--fork-at", str(n), "--local", local,
                        "--env-file", SCREEN2_ENV, "--one-combat-sha", cfg["one_combat_sha256"],
                        "--iterations", str(n + 1), "--games", str(cfg["games"]), "--parts", str(cfg["parts"]),
                        "--seed-base", str(cfg["seed_base"]), "--sims", str(cfg["sims"]), "--asc", str(cfg["asc"]),
                        "--value-warmup", "0", "--pipeline", str(cfg["pipeline"]), "--"] + cfg["learner_argv"])
    s = ppo_cloud.open_store(store)
    arm = ppo_cloud.ArmLearner(s, local, "FORKCHECK", a.device)
    if a.micro_batch > 0:
        arm.hparams.micro_batch = a.micro_batch
    if not arm.step(s.names("")):
        sys.exit("LEARNER_CHECK_FAIL: the fork did not train its iteration-30 update")
    mine = os.path.join(local, "FORKCHECK", f"net-{n + 1:04d}.bin")
    ref = os.path.join(src, f"net-{n + 1:04d}.bin")
    sm, sr = ppo_cloud.sha256(mine), ppo_cloud.sha256(ref)
    pm, pr = PolicyNet.from_bin(mine).state_dict(), PolicyNet.from_bin(ref).state_dict()
    dmax = max(float((pm[k] - pr[k]).abs().max()) for k in pr) if pm.keys() == pr.keys() else float("inf")
    ok = sm == sr
    print(json.dumps({"fork_net": sm, "base_net": sr, "max_abs_dparam": dmax, "learner_argv": cfg["learner_argv"],
                      "micro_batch": a.micro_batch}))
    print("LEARNER_CHECK_OK" if ok else "LEARNER_CHECK_FAIL (PREREG fallback bar: max |dparam| of a rerun of screen "
                                        "2's own learner on the same update)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
