#!/usr/bin/env python3
"""Pre-registered analysis of the turn-dominance campaign (README.md).

usage: analyze.py UNITS_DIR [OUT.json]

UNITS_DIR is searched recursively for T-<seed>.jsonl.gz (verify_campaign.py --extract layout).
"""
import gzip
import json
import random
import sys
from collections import defaultdict
from pathlib import Path


def load(units_dir):
    roots, summaries = [], []
    files = sorted(Path(units_dir).rglob("T-*.jsonl.gz"))
    seen = set()
    for f in files:
        seed = f.name[2:].split(".")[0]
        if seed in seen:   # duplicate tar of a queue unit: first one wins
            continue
        seen.add(seed)
        with gzip.open(f, "rt") as fh:
            for line in fh:
                r = json.loads(line)
                (summaries if r.get("summary") else roots).append(r)
    return roots, summaries


def rate_ci(roots, pred, seeds, n_boot=2000):
    by_seed = defaultdict(lambda: [0, 0])
    for r in roots:
        by_seed[r["seed"]][0] += 1
        by_seed[r["seed"]][1] += 1 if pred(r) else 0
    n = sum(v[0] for v in by_seed.values())
    k = sum(v[1] for v in by_seed.values())
    if n == 0:
        return {"n": 0, "k": 0, "rate": None, "ci95": None}
    rng = random.Random(111380000)
    keys = list(by_seed)
    boots = []
    for _ in range(n_boot):
        tn = tk = 0
        for s in (rng.choice(keys) for _ in keys):
            tn += by_seed[s][0]
            tk += by_seed[s][1]
        boots.append(tk / tn if tn else 0.0)
    boots.sort()
    return {"n": n, "k": k, "rate": k / n, "ci95": [boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot) - 1]]}


def main():
    roots, summaries = load(sys.argv[1])
    seeds = sorted({s["seed"] for s in summaries})
    ok = [r for r in roots if r.get("status") == "ok"]
    out = {
        "runs": len(summaries),
        "run_errors": sum(1 for s in summaries if "error" in s),
        "heart_kills": sum(1 for s in summaries if s.get("won")),
        "roots": len(roots),
        "skipped_roots": sum(s.get("skippedRoots", 0) for s in summaries),
        "status": {k: sum(1 for r in roots if r.get("status", "").split(":")[0] == k) for k in ("ok", "capped", "error")},
    }
    # Headline: Silver's chosen root edge reaches only dominated end-of-turn states.
    out["chosen_material"] = rate_ci(ok, lambda r: r["chosenMaterial"], seeds)
    out["chosen_material_gate_safe"] = rate_ci([r for r in ok if r["gateSafe"]], lambda r: r["chosenMaterial"], seeds)
    out["chosen_dominated"] = rate_ci(ok, lambda r: r["chosenDominated"], seeds)
    out["chosen_dominated_gate_safe"] = rate_ci([r for r in ok if r["gateSafe"]], lambda r: r["chosenDominated"], seeds)
    out["any_edge_dominated"] = rate_ci(ok, lambda r: any(e[3] == 1 for e in r["edges"]), seeds)
    out["chosen_closed"] = rate_ci(ok, lambda r: r["chosen"] >= 0 and r["edges"][r["chosen"]][2] == 0, seeds)
    out["all_edges_closed"] = rate_ci(ok, lambda r: all(e[2] == 0 for e in r["edges"]), seeds)
    by = defaultdict(list)
    for r in ok:
        by["room=" + r["room"]].append(r)
        by["act=%d" % r["act"]].append(r)
    out["chosen_material_by"] = {k: rate_ci(v, lambda r: r["chosenMaterial"], seeds) for k, v in sorted(by.items())}
    out["chosen_dominated_by"] = {k: rate_ci(v, lambda r: r["chosenDominated"], seeds) for k, v in sorted(by.items())}
    # Visit share Silver spends on dominated root edges (what pruning would free).
    shares = []
    for r in ok:
        tot = sum(e[0] for e in r["edges"])
        if tot > 0:
            shares.append(sum(e[0] for e in r["edges"] if e[3] == 1) / tot)
    out["dominated_visit_share_mean"] = sum(shares) / len(shares) if shares else None
    # Silver's own Q gap on materially flagged roots: Q(chosen) - best Q among non-dominated edges.
    gaps = []
    for r in ok:
        if not r["chosenMaterial"]:
            continue
        qc = r["edges"][r["chosen"]][1]
        alt = [e[1] for e in r["edges"] if e[3] != 1 and e[1] is not None]
        if qc is not None and alt:
            gaps.append(qc - max(alt))
    gaps.sort()
    out["flagged_q_gap"] = {"n": len(gaps), "median": gaps[len(gaps) // 2] if gaps else None,
                            "share_chosen_q_higher": sum(1 for g in gaps if g > 0) / len(gaps) if gaps else None}
    turns = defaultdict(bool)
    for r in ok:
        turns[(r["seed"], r["fight"], r["turn"])] |= r["chosenMaterial"]
    out["turns"] = {"n": len(turns), "with_material_flagged_choice": sum(turns.values())}
    enc = defaultdict(int)
    for r in ok:
        if r["chosenMaterial"]:
            enc[r["encounter"]] += 1
    out["flagged_by_encounter"] = dict(sorted(enc.items(), key=lambda kv: -kv[1]))
    execs = sorted(r["execs"] for r in ok)
    out["cost"] = {
        "execs_median": execs[len(execs) // 2] if execs else None,
        "execs_p99": execs[int(0.99 * len(execs))] if execs else None,
        "enum_sec_total": sum(s.get("enumSec", 0) for s in summaries),
        "run_sec_total": sum(s.get("sec", 0) for s in summaries),
    }
    rate = out["chosen_material"]["rate"]
    out["decision"] = None if rate is None else ("DROP" if rate < 0.01 else "INSPECT")
    text = json.dumps(out, indent=1)
    print(text)
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(text + "\n")


if __name__ == "__main__":
    main()
