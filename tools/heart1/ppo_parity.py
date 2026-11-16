"""Native vs torch parity of the PPO decision net on trajectory records (S0 review check).

    python3 tools/heart1/ppo_parity.py ONE_COMBAT NET.bin TRAJ.jsonl[.gz] [--perturb SEED] [--work DIR]

1. Extracts every decision record of the trajectory (schema heart1-ppo-traj-v1).
2. Scores them with `one_combat heart1score NET.bin` and with tools/heart1/ppo_model.py; reports max |logit| and
   |value| differences.
3. Without --perturb, NET.bin must be the net that played the trajectory: the recorded behaviour log-prob of each
   sampled decision is compared with log-softmax(torch logits / temperature) (median, p99, max, count > 1e-5).
4. --perturb SEED first writes NET.bin with random values in every optional input (x_*, x2_*) and the PPO
   fixed-action rows 166-178 (ppo_model.py perturb) and scores that net instead (no log-prob step); it also reports how
   far the perturbation moved the native logits, so a zero-effect perturbation cannot pass silently.

Reference run (#945, cov8.jsonl.gz of docs/experiments/evidence/ppo_s0_smoke_20261101, heart1.bin):
977 records, max |dlogit| 2.7e-5, log-prob median 1.1e-9 / p99 5.2e-6 / max 1.6e-5; --perturb 1: max |dlogit| 2.0e-5 (perturbation moves logits by 5.1).
Exit status 1 when max |dlogit| > --max-logit (default 1e-4) or max |dlogp| > --max-logp (default 1e-4).
"""
import argparse
import gzip
import json
import math
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ppo_model  # noqa: E402


def rows(path):
    with (gzip.open(path, "rt") if path.endswith(".gz") else open(path)) as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("one_combat")
    ap.add_argument("net")
    ap.add_argument("traj")
    ap.add_argument("--perturb", type=int)
    ap.add_argument("--work")
    ap.add_argument("--max-logit", type=float, default=1e-4)
    ap.add_argument("--max-logp", type=float, default=1e-4)
    a = ap.parse_args()
    work = a.work or tempfile.mkdtemp(prefix="ppo_parity_")
    os.makedirs(work, exist_ok=True)
    dec = [r for r in rows(a.traj) if r["type"] == "decision"]
    recs = os.path.join(work, "records.jsonl")
    with open(recs, "w") as f:
        for r in dec:
            f.write(json.dumps(r["record"]) + "\n")
    net = a.net
    if a.perturb is not None:
        net = os.path.join(work, "perturbed.bin")
        ppo_model.perturb_main([a.net, net, str(a.perturb)])
    nat, tor = os.path.join(work, "native.jsonl"), os.path.join(work, "torch.jsonl")
    subprocess.run([a.one_combat, "heart1score", net, recs, nat], check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    ppo_model.score_main([net, recs, tor])
    N = [json.loads(l) for l in open(nat)]
    T = [json.loads(l) for l in open(tor)]
    assert len(N) == len(T) == len(dec)
    out = {"records": len(dec), "net": net,
           "max_dlogit": max(max([abs(x - y) for x, y in zip(n["logits"], t["logits"])] or [0]) for n, t in zip(N, T)),
           "max_dvalue": max(abs(n["value"] - t["value"]) for n, t in zip(N, T))}
    ok = out["max_dlogit"] <= a.max_logit
    if a.perturb is not None:
        base = os.path.join(work, "native_base.jsonl")
        subprocess.run([a.one_combat, "heart1score", a.net, recs, base], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        B = [json.loads(l) for l in open(base)]
        out["perturbation_max_dlogit"] = max(max([abs(x - y) for x, y in zip(n["logits"], b["logits"])] or [0])
                                             for n, b in zip(N, B))
        ok = ok and out["perturbation_max_dlogit"] > 100 * a.max_logit
    else:
        d = []
        for r, t in zip(dec, T):
            if r["n"] < 2:
                continue
            temp = r["temp"] if r["temp"] > 0 else 1.0
            z = [x / temp for x in t["logits"]]
            m = max(z)
            lp = z[r["chosen"]] - m - math.log(sum(math.exp(x - m) for x in z))
            d.append(abs(lp - r["logp"]))
        d.sort()
        if d:
            out.update({"sampled": len(d), "dlogp_median": d[len(d) // 2], "dlogp_p99": d[int(0.99 * (len(d) - 1))],
                        "dlogp_max": d[-1], "dlogp_over_1e-5": sum(1 for x in d if x > 1e-5)})
            ok = ok and d[-1] <= a.max_logp
    out["ok"] = ok
    print(json.dumps(out))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
