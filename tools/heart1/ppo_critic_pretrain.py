"""Pre-train the critic (value head only) of a start net on recorded PPO games (reward screen 2, arm CRIT_PRE).

    python3 tools/heart1/ppo_critic_pretrain.py --init heart1.bin --traj-dir ~/ppo-screen1/BASE/parts \
        ~/ppo-screen1/BASE_S1/parts --passes 1 --out-bin critpre.bin --log critpre.jsonl [hyperparameters]

Each update is ppo_train's value-only update (the warm-up step: only the value head and its norm move, so the
policy is bit-identical to --init) on one recorded iteration's games (all parts traj-NNNN-p*.jsonl.gz of one
NNNN in one directory), in directory order then iteration order, PASSES times. Hyperparameters as ppo_train.py
(the reward decides the value targets; default 1{Heart}).
"""
import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ppo_train  # noqa: E402


def iteration_groups(dirs):
    groups = []
    for d in dirs:
        by_it = {}
        for p in glob.glob(os.path.join(os.path.expanduser(d), "traj-*-p*.jsonl.gz")):
            m = re.match(r"traj-(\d{4})-p\d+\.jsonl\.gz$", os.path.basename(p))
            if m:
                by_it.setdefault(int(m.group(1)), []).append(p)
        groups.extend(sorted(v) for _, v in sorted(by_it.items()))
    return groups


def main(argv):
    import torch
    ap = argparse.ArgumentParser(prog="ppo_critic_pretrain.py")
    ap.add_argument("--init", required=True)
    ap.add_argument("--traj-dir", nargs="+", required=True)
    ap.add_argument("--passes", type=int, default=1)
    ap.add_argument("--out-bin", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ppo_train.add_hparams(ap)
    a = ap.parse_args(argv)
    a.state = ""   # always start from --init
    groups = iteration_groups(a.traj_dir)
    if not groups:
        sys.exit("no traj-NNNN-pK.jsonl.gz files")
    torch.manual_seed(a.seed)
    learner = ppo_train.make_learner(a, torch.device(a.device))
    phi = ppo_train.phi_model_for(a)
    with open(a.log, "w") as log:
        for p in range(a.passes):
            for k, files in enumerate(groups):
                games = ppo_train.load_games(files, learner.net.trim_map, phi_model=phi)
                st = learner.update(games, value_only=True, log=lambda line: None)
                st.update({"pass": p, "group": k, "files": [os.path.basename(f) for f in files]})
                log.write(json.dumps(st) + "\n"); log.flush()
                print(f"pass {p} group {k}/{len(groups)}: {len(games)} games, value loss {st['value']:.5f}, "
                      f"mean value {st['mean_value']:.4f}, mean return {st['mean_return']:.4f}", flush=True)
                del games
    learner.net.to("cpu").to_bin(a.out_bin)
    print(f"wrote {a.out_bin} after {a.passes * len(groups)} value-only updates")


if __name__ == "__main__":
    main(sys.argv[1:])
