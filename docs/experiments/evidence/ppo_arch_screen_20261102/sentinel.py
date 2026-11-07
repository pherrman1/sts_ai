"""Actor sentinel of the arch screen (PREREG.md "Binding under B", ADR-0064 §2; IN_DECK's binary only).

    python3 sentinel.py ONE_COMBAT NET REF_TRAJ.jsonl.gz WORK --env-file ENV --seed-first S [--n 32] [--salt 30]
                        [--sims 1000] [--asc 20] [--threads N]

Plays seeds S..S+n-1 exactly as a ppo_cloud actor does (ppo_loop.start_actors: bestbench through seed_guard.sh, the
arm's env, STS_OOC_HEART1_SAMPLE_SALT = the iteration) twice with ONE_COMBAT: once with NET as stored and once with
NET extended by IN_DECK's zero-initialised construction (ppo_model.construct(inputs=["x3_deck"])). Every trajectory
line of those seeds (each decision with its logp, and the game line with the outcome) must equal REF_TRAJ's, compared
per seed as JSON objects in file order (excluded: the game line's net path and its outcome's wall_s timing). For the screen: NET = screen 2's BASE net-0029.bin, REF_TRAJ = BASE's kept
parts/traj-0030-p0.jsonl.gz, S = 111485360 (iteration 30, part 0), salt 30. Prints SENTINEL_OK or SENTINEL_FAIL.
"""
import argparse
import gzip
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "tools", "heart1"))
import ppo_loop  # noqa: E402
import ppo_model  # noqa: E402


def by_seed(path, lo, hi):
    out = defaultdict(list)
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                s = int(r.get("seed", -1))   # the trajectory writes seeds as strings
                if lo <= s <= hi:
                    if r.get("type") == "game":
                        r.pop("net", None)   # the net file's path
                    if isinstance(r.get("outcome"), dict):
                        r["outcome"].pop("wall_s", None)   # wall-clock time, not play
                    out[s].append(r)
    return out


def play(a, net, work):
    os.makedirs(work, exist_ok=True)
    run = argparse.Namespace(seed_base=a.seed_first - a.salt * a.n, games=a.n, one_combat=os.path.abspath(a.one_combat),
                             sims=a.sims, asc=a.asc, threads=a.threads)
    job = ppo_loop.start_actors(run, ppo_loop.read_env(a.env_file), os.path.abspath(net), a.salt, work)
    rc = job["proc"].wait()
    for f in job["files"]:
        f.close()
    if rc != 0:
        sys.exit(f"SENTINEL_FAIL: actors exited {rc} (see {work}/actors.err)")
    return job["traj"]


def compare(ref, got, lo, hi):
    bad = []
    for s in range(lo, hi + 1):
        if ref.get(s) != got.get(s):
            r, g = ref.get(s, []), got.get(s, [])
            k = next((i for i, (x, y) in enumerate(zip(r, g)) if x != y), min(len(r), len(g)))
            bad.append({"seed": s, "ref_lines": len(r), "lines": len(g), "first_diff_line": k})
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("one_combat")
    ap.add_argument("net")
    ap.add_argument("ref")
    ap.add_argument("work")
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--seed-first", type=int, required=True)
    ap.add_argument("--n", type=int, default=32)
    ap.add_argument("--salt", type=int, default=30)
    ap.add_argument("--sims", type=int, default=1000)
    ap.add_argument("--asc", type=int, default=20)
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 4)
    a = ap.parse_args()
    lo, hi = a.seed_first, a.seed_first + a.n - 1
    ref = by_seed(a.ref, lo, hi)
    if sorted(ref) != list(range(lo, hi + 1)):
        sys.exit(f"SENTINEL_FAIL: {a.ref} lacks seeds of {lo}..{hi}")
    os.makedirs(a.work, exist_ok=True)
    ext = os.path.join(a.work, "net_x3.bin")
    ppo_model.construct(ppo_model.PolicyNet.from_bin(a.net), inputs=["x3_deck"]).to_bin(ext)
    report = {}
    for name, net in (("stored", a.net), ("x3_zero", ext)):
        got = by_seed(play(a, net, os.path.join(a.work, name)), lo, hi)
        report[name] = compare(ref, got, lo, hi)
    ok = not any(report.values())
    print(json.dumps({"seeds": [lo, hi], "mismatches": report}))
    print("SENTINEL_OK" if ok else "SENTINEL_FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
