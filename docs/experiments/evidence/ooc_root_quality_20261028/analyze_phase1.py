#!/usr/bin/env python3
"""Phase-1 analysis (PREREG.md): validity, P_self (cross-fitted), sigma_D, rho_eff, seen gaps, horizon profile.

Usage: python3 -I analyze_phase1.py ROOTS_TSV DIR_OR_TAR... > phase1.json
A probed root is valid when main's state at the listed index is a card reward (Skip plus card candidates); the first
128 valid roots in seed order form the phase-1 sample. Bootstrap: 10,000 root resamples, seed 905.
"""
import gzip, json, math, random, statistics, sys, tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_fork_units import probe_rows  # noqa: E402

CHECKPOINTS = [256, 512, 1024, 2048, 4096, 8192, 16384]


def is_card_root(row):
    labels = [c["label"] for c in row.get("candidates", [])]
    return bool(labels) and any(l.startswith("Skip card") for l in labels) and any(l.startswith("Take card") for l in labels)


def picks(run):
    """{simulations: argmax id by mean Q over unpruned visited actions}, final included."""
    out = {}
    for cp in run["checkpoints"]:
        acts = [a for a in cp["actions"] if a[1] and not a[3]]
        out[cp["simulations"]] = max(acts, key=lambda a: a[2])[0]
    acts = [a for a in run["actions"] if a["visits"] and not a["pruned"]]
    out[run["simulations"]] = max(acts, key=lambda a: a["q"])["id"]
    return out


def final_q(run):
    return {a["id"]: a["q"] for a in run["actions"] if a["visits"] and not a["pruned"]}


def root_stats(row):
    ref_key = row["production"]["keys"][0]
    ref = next(c["id"] for c in row["candidates"] if c["key"] == ref_key)
    by_cfg = {}
    for g in row["grid"]:
        if "error" in g or g.get("aborted"):
            continue
        by_cfg.setdefault(f"{g['leaf']}:{g['horizon']}", []).append(g)
    out = {}
    for cfg, runs in by_cfg.items():
        runs.sort(key=lambda g: g["repeat"])
        if len(runs) < 4:
            continue
        r = {}
        # cross-fitted P_self: reference = argmax of mean Q of the other half at N_max
        halves = [(runs[0:2], runs[2:4]), (runs[2:4], runs[0:2])]
        pself = {n: [] for n in CHECKPOINTS}
        unresolved = 0
        for refs, scored in halves:
            qs = [final_q(g) for g in refs]
            ids = set(qs[0]) & set(qs[1])
            abar = max(ids, key=lambda i: (qs[0][i] + qs[1][i]) / 2)
            if max(qs[0], key=qs[0].get) != max(qs[1], key=qs[1].get):
                unresolved += 1
            for g in scored:
                p = picks(g)
                for n in CHECKPOINTS:
                    if n in p:
                        pself[n].append(float(p[n] != abar))
        r["pself"] = {n: statistics.mean(v) for n, v in pself.items() if v}
        r["unresolved_halves"] = unresolved
        # sigma_D per competitor at N_max over the 4 seeds; rho_eff from per-simulation moments
        qs = [final_q(g) for g in runs]
        sig, rho, gaps = {}, {}, {}
        for i in qs[0]:
            if i == ref:
                continue
            d = [q[ref] - q[i] for q in qs if i in q and ref in q]
            if len(d) < 2:
                continue
            sig[i] = statistics.stdev(d)
            gaps[i] = -statistics.mean(d)          # seen mu_i - mu_ref
            var = []
            for g in runs:
                v = {a["id"]: a["values"] for a in g["actions"] if "values" in a}
                n = v[ref]["count"]
                s2 = lambda x: x["sumSquares"] / x["count"] - (x["sum"] / x["count"]) ** 2
                var.append((s2(v[ref]) + s2(v[i])) / n)
            pred = statistics.mean(var)
            rho[i] = sig[i] ** 2 / pred if pred > 0 else math.nan
        r["sigma_d"], r["rho_eff"], r["seen_gap"] = sig, rho, gaps
        r["pick_ne_ref"] = statistics.mean(float(picks(g)[g["simulations"]] != ref) for g in runs)
        floors = {}
        for g in runs:
            for a in g["actions"]:
                for f, n in a.get("endpointFloors", {}).items():
                    floors[int(f) - row["floor"]] = floors.get(int(f) - row["floor"], 0) + n
        r["horizon_floors"] = floors
        r["max_depth"] = statistics.mean(g["maxDepth"] for g in runs)
        r["cpu"] = sum(g["cpuSeconds"] for g in runs)
        out[cfg] = r
    return out


def boot(values, reps=10000, seed=905):
    rng = random.Random(seed)
    n = len(values)
    means = sorted(statistics.mean(rng.choice(values) for _ in range(n)) for _ in range(reps))
    return [means[int(0.025 * reps)], means[int(0.975 * reps) - 1]]


def main():
    lines = [l.split("\t") for l in open(sys.argv[1]).read().splitlines()[1:]]
    order = [(int(l[0]), int(l[1])) for l in lines]
    offer712 = {(int(l[0]), int(l[1])): sorted(map(int, l[5].split(","))) for l in lines if len(l) > 5}
    rows = {(r["seed"], r["decisionIndex"]): r for r in probe_rows(sys.argv[2:])}
    valid, invalid, missing = [], [], []
    for key in order:
        if key not in rows:
            missing.append(key)
        elif is_card_root(rows[key]):
            valid.append(key)
        else:
            invalid.append(key)
    sample = valid[:128]
    stats = {k: root_stats(rows[k]) for k in sample}
    meta = {}
    for k in sample:
        offer = sorted(int(m.split(",")[1]) for c in rows[k]["candidates"]
                       for m in [c["key"].split("reward=")[1].split(":")[0]] if m.startswith("card,"))
        meta[f"{k[0]}/{k[1]}"] = {"K": len(rows[k]["candidates"]), "offer_matches_712": offer == offer712.get(k)}
    cfgs = sorted({c for s in stats.values() for c in s})
    summary = {}
    for cfg in cfgs:
        per = [s[cfg] for s in stats.values() if cfg in s]
        res = {"roots": len(per)}
        for n in CHECKPOINTS:
            v = [p["pself"][n] for p in per if n in p["pself"]]
            vr = [p["pself"][n] for p in per if n in p["pself"] and p["unresolved_halves"] == 0]
            if v:
                res[f"pself_{n}"] = {"mean": statistics.mean(v), "ci": boot(v),
                                     "resolved_only": statistics.mean(vr) if vr else None}
        res["unresolved_share"] = statistics.mean(p["unresolved_halves"] / 2 for p in per)
        sd = [x for p in per for x in p["sigma_d"].values()]
        rho = [x for p in per for x in p["rho_eff"].values() if not math.isnan(x)]
        gap = [abs(x) for p in per for x in p["seen_gap"].values()]
        res["sigma_d_rms"] = math.sqrt(statistics.mean(x * x for x in sd)) if sd else None
        res["rho_eff_median"] = statistics.median(rho) if rho else None
        res["seen_abs_gap_median"] = statistics.median(gap) if gap else None
        res["pick_ne_ref"] = statistics.mean(p["pick_ne_ref"] for p in per)
        hist = {}
        for p in per:
            tot = sum(p["horizon_floors"].values())
            for f, n in p["horizon_floors"].items():
                hist[f] = hist.get(f, 0) + n / tot / len(per)
        res["horizon_floor_share"] = dict(sorted(hist.items()))
        res["cpu_per_root"] = statistics.mean(p["cpu"] for p in per)
        summary[cfg] = res
    json.dump({"meta": meta, "K_gt5": sum(m["K"] > 5 for m in meta.values()),
               "offer_mismatch": sum(not m["offer_matches_712"] for m in meta.values()), "valid": len(valid), "invalid": invalid, "missing": missing, "sample": len(sample),
               "summary": summary, "per_root": {f"{k[0]}/{k[1]}": v for k, v in stats.items()}},
              sys.stdout, indent=1)


if __name__ == "__main__":
    main()
