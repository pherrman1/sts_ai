#!/usr/bin/env python3
"""Map-root value-of-computation audit (#927 item 6): offline, from logged OOC MCTS decision rows.

Usage: analyze.py ARM UNITS_DIR OUT_JSON
Reads every <seed>.wNN.tar in UNITS_DIR, takes <ARM>-<seed>.jsonl.gz, and tabulates for every searched,
non-singleton map root (screen 5, by=mcts, attempts > 0): prior top, prior argmax, played action, the
most-visited action at each logged checkpoint (ties: visits, then q, then lower id, the production
selection rule visits_q_id), and simulations spent.
"""
import collections, gzip, io, json, math, os, sys, tarfile

ARM, UNITS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
BINS = [0.0, 0.5, 0.8, 0.9, 0.95, 0.98, 0.99, 0.999, 1.0000001]
LEAF_SD = 0.13  # within-state SD of one rollout3 leaf (rollout-cost measurement 2026-10-31); rough, ignores tree correlation
MS_PER_SIM = {1: 7.5, 2: 10.6, 3: 14.4, 4: 14.4}  # rollout-cost measurement 2026-10-31 (acts 1-3); act 4 = act 3


def pick(actions):
    actions = [a for a in actions if not a.get("pruned")] or actions
    return sorted(actions, key=lambda a: (-a["visits"], -a["q"], a["id"]))[0]["id"]


def bin_of(p):
    for lo, hi in zip(BINS, BINS[1:]):
        if lo <= p < hi:
            return f"[{lo:g},{min(hi, 1):g}{']' if hi > 1 else ')'}"
    raise ValueError(p)


roots, games, other = [], 0, collections.Counter()
for name in sorted(os.listdir(UNITS)):
    if not name.endswith(".tar"):
        continue
    seed = name.split(".")[0]
    with tarfile.open(os.path.join(UNITS, name)) as tf:
        try:
            m = tf.getmember(f"out/units/{seed}/{ARM}-{seed}.jsonl.gz")
        except KeyError:
            other["missing_arm_file"] += 1
            continue
        data = gzip.decompress(tf.extractfile(m).read()).decode()
    rows = [json.loads(l) for l in data.splitlines() if l.strip()]
    out = [r for r in rows if r.get("type") == "outcome"]
    if not out or not out[0].get("complete"):
        other["incomplete_game"] += 1
        continue
    games += 1
    for r in rows:
        if r.get("type") != "decision" or not r.get("searched"):
            continue
        root = r["root"]
        if r.get("screen") != 5:
            other[f"searched_screen_{r.get('screen')}"] += 1
            continue
        if root.get("singleton") or not root.get("attempts"):
            other["singleton_or_zero"] += 1
            continue
        if root.get("aborted"):
            other["aborted"] += 1
            continue
        cands = root["candidates"]
        top = max(cands, key=lambda c: (c["prior"], -c["id"]))
        cps = {c["simulations"]: pick(c["actions"]) for c in root.get("checkpoints", [])}
        byid = {c["id"]: c for c in cands}
        pl, pa = byid[root["selectedId"]], byid[top["id"]]
        qgap = pl["q"] - pa["q"]
        z = qgap / (LEAF_SD * math.sqrt(1 / max(1, pl["visits"]) + 1 / max(1, pa["visits"])))
        roots.append(dict(qgap=qgap, z=z, v_played=pl["visits"], v_prior=pa["visits"], seed=int(seed), act=r["act"], floor=r["floor"], n=len(cands),
                          prior_top=top["prior"], prior_arg=top["id"], played=root["selectedId"],
                          sims=root["completedSimulations"], full=root.get("fullBudget"),
                          cp=cps, top_visit_share=root["maxVisits"] / max(1, root["rootVisits"])))

total_sims = sum(x["sims"] for x in roots)
total_cpu = sum(x["sims"] * MS_PER_SIM[x["act"]] for x in roots)


def summarize(sel):
    n = len(sel)
    if n == 0:
        return dict(roots=0)
    dep = sum(x["played"] != x["prior_arg"] for x in sel)
    have_full = [x for x in sel if x["sims"] in x["cp"]]
    res = dict(roots=n, final_checkpoint_matches_played=sum(x["cp"][x["sims"]] == x["played"] for x in have_full),
               final_checkpoint_rows=len(have_full), share_roots=n / len(roots),
               share_sims=sum(x["sims"] for x in sel) / total_sims,
               share_cpu_est=sum(x["sims"] * MS_PER_SIM[x["act"]] for x in sel) / total_cpu,
               departs_prior=dep, departs_prior_rate=dep / n,
               departs_prior_se=math.sqrt(dep / n * (1 - dep / n) / n),
               mean_top_visit_share=sum(x["top_visit_share"] for x in sel) / n)
    deps = [x for x in sel if x["played"] != x["prior_arg"]]
    if deps:
        g = sorted(x["qgap"] for x in deps); zz = sorted(x["z"] for x in deps)
        res.update(dep_qgap_median=g[len(g) // 2], dep_qgap_p90=g[int(0.9 * (len(g) - 1))],
                   dep_z_median=zz[len(zz) // 2], dep_z_gt2=sum(z > 2 for z in zz),
                   dep_prior_visits_median=sorted(x["v_prior"] for x in deps)[len(deps) // 2],
                   dep_played_visits_median=sorted(x["v_played"] for x in deps)[len(deps) // 2])
    for k in (128, 256, 512, 1024, 2048):
        have = [x for x in sel if k in x["cp"]]
        fl = sum(x["cp"][k] != x["played"] for x in have)
        res[f"flip_{k}_to_final"] = fl
        res[f"flip_{k}_to_final_rate"] = fl / len(have) if have else None
        # of those flips, how many move toward the prior argmax (checkpoint off-prior, final on prior)
        res[f"flip_{k}_toward_prior"] = sum(x["cp"][k] != x["played"] and x["played"] == x["prior_arg"] for x in have)
        res[f"departs_prior_at_{k}"] = sum(x["cp"][k] != x["prior_arg"] for x in have)
    return res


by_bin = collections.OrderedDict()
for lo, hi in zip(BINS, BINS[1:]):
    by_bin[bin_of(lo)] = summarize([x for x in roots if lo <= x["prior_top"] < hi])
by_act = {a: summarize([x for x in roots if x["act"] == a]) for a in sorted({x["act"] for x in roots})}
hi98 = summarize([x for x in roots if x["prior_top"] >= 0.98])
lo98 = summarize([x for x in roots if x["prior_top"] < 0.98])
res = dict(arm=ARM, units_dir=UNITS, games=games, searched_map_roots=len(roots), total_sims=total_sims,
           sims_per_game=total_sims / games, skipped=dict(other), all=summarize(roots),
           prior_ge_098=hi98, prior_lt_098=lo98, by_prior_top_bin=by_bin, by_act=by_act,
           ms_per_sim=MS_PER_SIM)
json.dump(res, open(OUT, "w"), indent=1)
print(json.dumps({k: v for k, v in res.items() if k not in ("by_prior_top_bin", "by_act")}, indent=1))
for k, v in by_bin.items():
    print(k, {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()})
