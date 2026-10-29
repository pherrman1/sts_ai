#!/usr/bin/env python3
"""Exploratory (not pre-registered; written after phase-1 data): the search's own regret and the leaf agreement.

Usage: python3 -I explore_self_regret.py PHASE1_JSON DIR_OR_TAR... > explore.json
Self-regret(N) of one seed = Qbar(abar) - Qbar(pick_N), Qbar = mean final Q of the other half's two seeds (cross-fitted
as P_self), in the leaf's own value scale. "Clear" roots: the reference half's best mean Q leads the second by > 1 pp.
Leaf agreement: share of roots where the 4-seed final mean-Q argmax of two configurations coincide, and where it equals
the production pick. Bootstrap: 10,000 root resamples, seed 905.
"""
import json, statistics, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_phase1 import CHECKPOINTS, boot, final_q, picks  # noqa: E402
from make_fork_units import probe_rows  # noqa: E402


def runs_by_cfg(row):
    by = {}
    for g in row["grid"]:
        if "error" not in g and not g.get("aborted"):
            by.setdefault(f"{g['leaf']}:{g['horizon']}", []).append(g)
    return {c: sorted(r, key=lambda g: g["repeat"]) for c, r in by.items() if len(r) >= 4}


def main():
    sample = set(json.loads(Path(sys.argv[1]).read_text())["per_root"])
    rows = [r for r in probe_rows(sys.argv[2:]) if f"{r['seed']}/{r['decisionIndex']}" in sample]
    regret, pself_clear, clear_share, best = {}, {}, {}, {}
    for row in rows:
        ref_key = row["production"]["keys"][0]
        ref = next(c["id"] for c in row["candidates"] if c["key"] == ref_key)
        for cfg, runs in runs_by_cfg(row).items():
            reg = {n: [] for n in CHECKPOINTS}
            pc = {n: [] for n in CHECKPOINTS}
            clear = []
            for refs, scored in ((runs[0:2], runs[2:4]), (runs[2:4], runs[0:2])):
                qs = [final_q(g) for g in refs]
                ids = set(qs[0]) & set(qs[1])
                qbar = {i: (qs[0][i] + qs[1][i]) / 2 for i in ids}
                order = sorted(qbar.values(), reverse=True)
                abar = max(qbar, key=qbar.get)
                is_clear = len(order) > 1 and order[0] - order[1] > 0.01
                clear.append(float(is_clear))
                for g in scored:
                    p = picks(g)
                    for n in CHECKPOINTS:
                        if n in p and p[n] in qbar:
                            reg[n].append(qbar[abar] - qbar[p[n]])
                            if is_clear:
                                pc[n].append(float(p[n] != abar))
            regret.setdefault(cfg, {n: [] for n in CHECKPOINTS})
            pself_clear.setdefault(cfg, {n: [] for n in CHECKPOINTS})
            for n in CHECKPOINTS:
                if reg[n]:
                    regret[cfg][n].append(statistics.mean(reg[n]))
                if pc[n]:
                    pself_clear[cfg][n].append(statistics.mean(pc[n]))
            clear_share.setdefault(cfg, []).append(statistics.mean(clear))
            qs = [final_q(g) for g in runs]
            ids = set.intersection(*(set(q) for q in qs))
            best.setdefault((row["seed"], row["decisionIndex"]), {"ref": ref})[cfg] = max(
                ids, key=lambda i: sum(q[i] for q in qs))
    out = {"roots": len(rows), "self_regret_pp": {}, "pself_clear": {}, "clear_share": {}, "agreement": {}}
    for cfg in sorted(regret):
        out["self_regret_pp"][cfg] = {n: {"mean": 100 * statistics.mean(v), "ci": [100 * x for x in boot(v)]}
                                      for n, v in regret[cfg].items() if v}
        out["pself_clear"][cfg] = {n: {"roots": len(v), "mean": statistics.mean(v), "ci": boot(v)}
                                   for n, v in pself_clear[cfg].items() if v}
        out["clear_share"][cfg] = statistics.mean(clear_share[cfg])
    cfgs = sorted(regret)
    for a in cfgs:
        out["agreement"][f"{a}=production"] = statistics.mean(float(b[a] == b["ref"]) for b in best.values() if a in b)
        for c in cfgs:
            if a < c:
                v = [float(b[a] == b[c]) for b in best.values() if a in b and c in b]
                out["agreement"][f"{a}={c}"] = statistics.mean(v)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
