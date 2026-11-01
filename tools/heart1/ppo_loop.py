"""Single-machine PPO iteration loop (S0): native actors write trajectories, the torch learner updates, repeat.

Per iteration i (resumable; finished iterations are listed in RUN/loop.json):
  1. actors: one `one_combat bestbench` process through tools/seed_guard.sh with OMP threads, playing GAMES games
     on seeds SEED_BASE + i*GAMES ... with STS_OOC_HEART1=RUN/net_i.bin, STS_OOC_HEART1_PPO=1,
     STS_OOC_HEART1_SAMPLE_SALT=i and STS_OOC_HEART1_PPO_TRAJ=RUN/iter_i/traj.jsonl, plus every KEY=VALUE line of
     --env-file (the frozen game/combat configuration; it must not set the variables above);
  2. learner: tools/heart1/ppo_train.py's update on that file (critic only for i < --value-warmup), checkpoint
     RUN/state.pt, export RUN/net_{i+1}.bin;
  3. the trajectory is gzipped in place (--keep-traj 0 deletes it instead).

    python3 tools/heart1/ppo_loop.py --run RUN --one-combat build/.../one_combat --env-file actors.env \
        --init heart1.bin --iterations 60 --games 512 --seed-base SEED --threads 12 --value-warmup 3 -- --lr 1e-5

Everything after `--` goes to the learner (ppo_train.py update hyperparameters). Seeds must be a reserved block:
the loop prints the whole range it will use before the first game. Collection and update are not pipelined.
"""
import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ppo_train  # noqa: E402
from ppo_model import PolicyNet  # noqa: E402

RESERVED = {"STS_OOC_HEART1", "STS_OOC_HEART1_PPO", "STS_OOC_HEART1_SAMPLE_SALT", "STS_OOC_HEART1_PPO_TRAJ",
            "OMP_NUM_THREADS"}
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def sha16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def read_env(path):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            k, _, v = line.partition("=")
            if k in RESERVED:
                sys.exit(f"{path}: {k} is set by the loop")
            env[k] = v
    return env


def run_actors(args, env_base, net, it, out_dir, trim_map):
    traj = os.path.join(out_dir, "traj.jsonl")
    for f in (traj, os.path.join(out_dir, "results.csv")):
        if os.path.exists(f):
            os.remove(f)   # a half-finished iteration restarts from scratch
    seed = args.seed_base + it * args.games
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/tmp"), **env_base,
           "STS_OOC_HEART1": net, "STS_OOC_HEART1_PPO": "1", "STS_OOC_HEART1_SAMPLE_SALT": str(it),
           "STS_OOC_HEART1_PPO_TRAJ": traj, "OMP_NUM_THREADS": str(args.threads)}
    cmd = ["bash", os.path.join(REPO, "tools", "seed_guard.sh"), args.one_combat, "bestbench", str(args.sims),
           str(args.games), str(args.asc), str(seed), os.path.join(out_dir, "results.csv")]
    t0 = time.time()
    with open(os.path.join(out_dir, "actors.log"), "w") as log, open(os.path.join(out_dir, "actors.err"), "w") as err:
        rc = subprocess.run(cmd, env=env, cwd=REPO, stdout=log, stderr=err).returncode
    if rc != 0:
        sys.exit(f"iteration {it}: actors exited {rc} (see {out_dir}/actors.err)")
    games = ppo_train.load_games([traj], trim_map)
    if len(games) != args.games:
        sys.exit(f"iteration {it}: {len(games)} games in {traj}, expected {args.games}")
    return traj, games, seed, time.time() - t0


def main():
    argv = sys.argv[1:]
    learner_argv = []
    if "--" in argv:
        k = argv.index("--")
        argv, learner_argv = argv[:k], argv[k + 1:]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--one-combat", required=True)
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--init", required=True, help="start net (.bin); extended with zero-init inputs")
    ap.add_argument("--iterations", type=int, required=True)
    ap.add_argument("--games", type=int, default=512)
    ap.add_argument("--seed-base", type=int, required=True)
    ap.add_argument("--sims", type=int, default=1000)
    ap.add_argument("--asc", type=int, default=20)
    ap.add_argument("--threads", type=int, default=12)
    ap.add_argument("--value-warmup", type=int, default=0)
    ap.add_argument("--keep-traj", type=int, default=1, help="1 = gzip each iteration's trajectory, 0 = delete it")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args(argv)
    hp = argparse.ArgumentParser(prog="learner")
    ppo_train.add_hparams(hp)
    hparams = hp.parse_args(learner_argv)

    os.makedirs(args.run, exist_ok=True)
    meta_path = os.path.join(args.run, "loop.json")
    meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {
        "init": os.path.abspath(args.init), "init_sha16": sha16(args.init), "one_combat_sha16": sha16(args.one_combat),
        "env": read_env(args.env_file), "games": args.games, "seed_base": args.seed_base, "sims": args.sims,
        "asc": args.asc, "hparams": vars(hparams), "value_warmup": args.value_warmup, "iterations": []}
    for key, now in (("one_combat_sha16", sha16(args.one_combat)), ("env", read_env(args.env_file)),
                     ("games", args.games), ("seed_base", args.seed_base), ("sims", args.sims), ("asc", args.asc)):
        if meta[key] != now:
            sys.exit(f"{meta_path}: {key} differs from this call ({meta[key]} vs {now}); start a new run directory")
    done = len(meta["iterations"])
    print(f"[ppo_loop] seeds {args.seed_base}..{args.seed_base + args.iterations * args.games - 1} "
          f"({args.iterations} x {args.games}); resuming at iteration {done}", flush=True)

    state = os.path.join(args.run, "state.pt")
    net0 = os.path.join(args.run, "net_0000.bin")
    if done == 0 and not os.path.exists(net0):
        PolicyNet.from_bin(args.init).to_bin(net0)
    hparams.state, hparams.init = state, net0
    learner = ppo_train.make_learner(hparams, torch.device(args.device))
    if learner.iteration != done:
        sys.exit(f"{state} is at iteration {learner.iteration}, loop.json at {done}")

    for it in range(done, args.iterations):
        out_dir = os.path.join(args.run, f"iter_{it:04d}")
        os.makedirs(out_dir, exist_ok=True)
        net = os.path.join(args.run, f"net_{it:04d}.bin")
        traj, games, seed, actor_s = run_actors(args, meta["env"], net, it, out_dir, learner.net.trim_map)
        value_only = it < args.value_warmup
        stats = learner.update(games, value_only=value_only, log=lambda line: print(line, flush=True))
        nxt = os.path.join(args.run, f"net_{it + 1:04d}.bin")
        learner.net.to("cpu").to_bin(nxt)
        learner.net.to(args.device)
        ppo_train.save(learner, state)
        if args.keep_traj:
            with open(traj, "rb") as src, gzip.open(traj + ".gz", "wb") as dst:
                shutil.copyfileobj(src, dst)
        os.remove(traj)
        stats.update({"seed_first": seed, "actor_s": actor_s, "net": os.path.basename(net), "net_sha16": sha16(net),
                      "next_sha16": sha16(nxt)})
        meta["iterations"].append(stats)
        tmp = meta_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(meta, f, indent=1)
        os.replace(tmp, meta_path)


if __name__ == "__main__":
    main()
