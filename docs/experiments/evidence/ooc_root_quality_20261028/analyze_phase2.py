#!/usr/bin/env python3
"""Phase-2 analysis (PREREG.md): calibration beta per (leaf, horizon), advantage curves, c bracket, coverage q.

Usage: python3 -I analyze_phase2.py SELECTION_JSON PHASE1_DIR_OR_TAR FORK_DIR_OR_TAR... > phase2.json
Z = Heart kill of a forked game; a_ref = production key; selection inclusion probabilities from make_fork_units.py.
Primary: beta_SR at h = 3, N_max (decision rule in PREREG). Bootstrap: 10,000 two-stage resamples (roots, salts), seed 906.
"""
import gzip, json, math, random, statistics, sys, tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_fork_units import probe_rows  # noqa: E402
from analyze_phase1 import picks, final_q, CHECKPOINTS  # noqa: E402

REPS, SEED = 10000, 906


def fork_games(paths):
    """yield (seed, index, salt, key, outcome_row, forced_ok)"""
    def parse(env_text, jsonl_text):
        env = dict(l.split("=", 1) for l in env_text.splitlines() if "=" in l)
        idx, salt, key = env["STS_OOC_FORCE_DECISION"].split(":", 2)
        rows = [json.loads(l) for l in jsonl_text.splitlines() if l.strip()]
        out = rows[-1] if rows and rows[-1].get("type") == "outcome" else None
        seed = next((r.get("seed") for r in rows if r.get("seed") is not None), None)
        forced = [r for r in rows if r.get("type") == "decision" and r.get("decisionIndex") == int(idx)]
        ok = bool(forced) and (forced[0].get("by") == "forced_decision" or key == "-")
        return int(idx), int(salt), key, out, ok, seed
    for p in map(Path, paths):
        tars = [p] if p.suffix == ".tar" else sorted(p.rglob("*.tar"))
        for tar in tars:
            with tarfile.open(tar) as t:
                members = {m.name: m for m in t.getmembers()}
                for name, m in members.items():
                    if name.endswith(".env") and "/fork-" in name:
                        base = name[:-4]
                        j = members.get(base + ".jsonl.gz")
                        if j is None:
                            continue
                        seed = int(Path(base).name.split("-")[1])
                        idx, salt, key, out, ok, _ = parse(t.extractfile(m).read().decode(),
                                                           gzip.decompress(t.extractfile(j).read()).decode())
                        yield seed, idx, salt, key, out, ok


def two_stage(units, stat, rng):
    """units: {root: [values per salt]} -> bootstrap CI of stat(list of (root, values))."""
    roots = list(units)
    vals = []
    for _ in range(REPS):
        sample = []
        for _ in roots:
            r = rng.choice(roots)
            v = units[r]
            sample.append((r, [rng.choice(v) for _ in v]))
        vals.append(stat(sample))
    vals.sort()
    return [vals[int(0.025 * REPS)], vals[int(0.975 * REPS) - 1]]


def main():
    sel = json.load(open(sys.argv[1]))
    roots = {(r["seed"], r["index"]): r for r in sel["roots"]}
    probes = {(r["seed"], r["decisionIndex"]): r for r in probe_rows([sys.argv[2]]) if (r["seed"], r["decisionIndex"]) in roots}
    Z, T, bad = {}, {}, []
    for seed, idx, salt, key, out, ok in fork_games(sys.argv[3:]):
        if (seed, idx) not in roots:
            continue
        if out is None or not ok or not out.get("complete", False):
            bad.append([seed, idx, salt, key])
            continue
        Z[(seed, idx, salt, key)] = float(bool(out["heartKilled"]))
        T[(seed, idx, salt, key)] = out["finalFloor"]
    salts = [1, 2, 3, 4]
    rng = random.Random(SEED)
    # effect representative per candidate id
    rep_key, ids = {}, {}
    for k, pr in probes.items():
        eff = {}
        for c in pr["candidates"]:
            e = c.get("effect", c["key"])
            eff.setdefault(e, c["key"])
            rep_key[(k, c["id"])] = eff[e]
        ids[k] = {c["id"]: c["key"] for c in pr["candidates"]}
    complete = [k for k in roots if k in probes and all((k[0], k[1], s, roots[k]["keys"][i]) in Z
                for s in salts for i in range(len(roots[k]["keys"])))]
    w = {k: 1.0 / roots[k]["inclusion"] for k in complete}
    z = lambda k, s, cid: Z[(k[0], k[1], s, rep_key[(k, cid)])]
    ref_id = {k: next(c["id"] for c in probes[k]["candidates"] if c["key"] == roots[k]["ref"]) for k in complete}
    runs = {}
    for k in complete:
        for g in probes[k]["grid"]:
            if "error" not in g and not g.get("aborted"):
                runs.setdefault((k, f"{g['leaf']}:{g['horizon']}"), []).append(g)
    cfgs = sorted({c for (_, c) in runs})
    out = {"roots": len(complete), "bad_games": bad, "games": len(Z), "calibration": {}, "advantage": {}}
    # calibration beta per config at N_max
    for cfg in cfgs:
        rows, sig2 = [], []
        for k in complete:
            gs = runs.get((k, cfg), [])
            if len(gs) < 2:
                continue
            qs = [final_q(g) for g in gs]
            r0 = ref_id[k]
            for cid in qs[0]:
                if cid == r0 or rep_key[(k, cid)] == rep_key[(k, r0)]:
                    continue
                d = [q[cid] - q[r0] for q in qs if cid in q and r0 in q]
                x = statistics.mean(d)
                sig2.append(statistics.variance(d) / len(d) if len(d) > 1 else 0.0)
                for s in salts:
                    rows.append((k, x, z(k, s, cid) - z(k, s, r0)))
        if len(rows) < 10:
            continue
        def fit(rs):
            xs = [r[1] for r in rs]; ys = [r[2] for r in rs]
            mx, my = statistics.mean(xs), statistics.mean(ys)
            sxx = sum((a - mx) ** 2 for a in xs)
            b = sum((a - mx) * (c - my) for a, c in zip(xs, ys)) / sxx if sxx else math.nan
            return b, my - b * mx, mx, sxx
        b, a, mx, sxx = fit(rows)
        # root-clustered sandwich SE
        byroot = {}
        for r in rows:
            byroot.setdefault(r[0], []).append(r)
        meat = sum(sum((r[1] - mx) * (r[2] - a - b * r[1]) for r in rs) ** 2 for rs in byroot.values())
        se = math.sqrt(meat) / sxx
        pair_x = [x for x in {(r[0], r[1]): r[1] for r in rows}.values()]
        varx = statistics.variance(pair_x) if len(pair_x) > 1 else 0.0
        lam = 1 - statistics.mean(sig2) / varx if varx > 0 else math.nan
        lam = lam if lam > 0.05 else math.nan   # x mostly search noise: no attenuation correction
        out["calibration"][cfg] = {"beta": b, "alpha": a, "se_beta": se, "ci_beta": [b - 1.96 * se, b + 1.96 * se],
                                   "reliability": lam, "beta_corrected": b / lam, "pairs": len(rows),
                                   "roots": len(byroot)}
    # advantage curves A(theta) with HT weights; theta = (cfg, N)
    for cfg in cfgs:
        for n in CHECKPOINTS:
            units = {}
            for k in complete:
                gs = runs.get((k, cfg), [])
                ps = [picks(g).get(n) for g in gs]
                ps = [p for p in ps if p is not None]
                if not ps:
                    continue
                units[k] = [statistics.mean(z(k, s, p) - z(k, s, ref_id[k]) for p in ps) for s in salts]
            if not units:
                continue
            stat = lambda smp: sum(w[r] * statistics.mean(v) for r, v in smp) / sum(w[r] for r, _ in smp)
            est = stat(list(units.items()))
            out["advantage"][f"{cfg}@{n}"] = {"mean": est, "ci": two_stage(units, stat, rng), "roots": len(units)}
    # c bracket: cross-fitted hindsight gain (choose on salts {1,2}, evaluate on {3,4}, and swap); in-sample upper
    halves = [([1, 2], [3, 4]), ([3, 4], [1, 2])]
    cross, insample = {}, {}
    for k in complete:
        cands = list(ids[k])
        def gain(choose, evaluate):
            best = max(cands, key=lambda c: statistics.mean(z(k, s, c) - z(k, s, ref_id[k]) for s in choose))
            return [z(k, s, best) - z(k, s, ref_id[k]) for s in evaluate]
        cross[k] = gain(*halves[0]) + gain(*halves[1])
        insample[k] = [max(statistics.mean(z(k, s, c) - z(k, s, ref_id[k]) for s in salts) for c in cands)] * 4
    stat = lambda smp: sum(w[r] * statistics.mean(v) for r, v in smp) / sum(w[r] for r, _ in smp)
    out["c_bracket"] = {"cross_fitted": stat(list(cross.items())), "cross_fitted_ci": two_stage(cross, stat, rng),
                        "in_sample": stat(list(insample.items()))}
    # coverage q(h): discordant (root, i, salt) vs a_ref; T = final floor of the losing arm
    out["coverage"] = {}
    for cfg in cfgs:
        num = den = 0.0
        for k in complete:
            gs = runs.get((k, cfg), [])
            if not gs:
                continue
            r0 = ref_id[k]
            for cid in ids[k]:
                if rep_key[(k, cid)] == rep_key[(k, r0)]:
                    continue
                floors = {}
                for g in gs:
                    for a in g["actions"]:
                        if a["id"] == cid:
                            for f, c in a.get("endpointFloors", {}).items():
                                floors[int(f)] = floors.get(int(f), 0) + c
                tot = sum(floors.values())
                if not tot:
                    continue
                for s in salts:
                    zi, zr = z(k, s, cid), z(k, s, r0)
                    if zi == zr:
                        continue
                    loser = rep_key[(k, cid)] if zi < zr else rep_key[(k, r0)]
                    tf = T[(k[0], k[1], s, loser)]
                    num += w[k] * sum(c for f, c in floors.items() if f >= tf) / tot
                    den += w[k]
        if den:
            out["coverage"][cfg] = {"q": num / den, "weight": den}
    # Per-root table (Philipp 2026-10-28 22:14Z; noisy per root by design, SE per pair ~0.45/sqrt(4)) and the
    # method-of-moments RMS of the relative bias B_ab = x - Delta_ref per (root, competitor) at N_max:
    # E[(x - D)^2] = B^2 + Var(D | root) + Var(x), D = mean over salts of Z_i - Z_ref.
    out["per_root"], out["rms_relative_bias"] = {}, {}
    for cfg in cfgs:
        terms, table = [], []
        for k in complete:
            gs = runs.get((k, cfg), [])
            if len(gs) < 2:
                continue
            qs = [final_q(g) for g in gs]
            r0 = ref_id[k]
            mean_q = {c: statistics.mean(q[c] for q in qs if c in q) for c in qs[0]}
            ref_q = {c: statistics.mean(z(k, s, c) for s in salts) for c in ids[k]}
            best_ref = max(ref_q, key=ref_q.get)
            chosen = [picks(g)[g["simulations"]] for g in gs]
            for c in qs[0]:
                if c == r0 or rep_key[(k, c)] == rep_key[(k, r0)]:
                    continue
                d = [z(k, s, c) - z(k, s, r0) for s in salts]
                dx = [q[c] - q[r0] for q in qs if c in q and r0 in q]
                x, dm = statistics.mean(dx), statistics.mean(d)
                vd = statistics.variance(d) / len(d)
                vx = statistics.variance(dx) / len(dx) if len(dx) > 1 else 0.0
                terms.append(((x - dm) ** 2 - vd - vx, w[k], k))
                table.append({"root": f"{k[0]}/{k[1]}", "competitor": ids[k][c], "delta_ref": dm,
                              "delta_mcts": x, "B_ab": x - dm, "se_ref": math.sqrt(vd), "search_sd": math.sqrt(vx * len(dx))})
            out["per_root"].setdefault(cfg, {})[f"{k[0]}/{k[1]}"] = {
                "rows": [t for t in table if t["root"] == f"{k[0]}/{k[1]}"],
                "mcts_best_eq_ref_best_insample": statistics.mean(float(rep_key[(k, c)] == rep_key[(k, best_ref)]) for c in chosen),
                "regret_vs_insample_best": statistics.mean(ref_q[best_ref] - ref_q[c] for c in chosen),
                "max_depth": statistics.mean(g["maxDepth"] for g in gs)}
        if terms:
            m2 = sum(t * wt for t, wt, _ in terms) / sum(wt for _, wt, _ in terms)
            boot = []
            for _ in range(2000):
                byr = {}
                for t in terms:
                    byr.setdefault(t[2], []).append(t)
                keys = list(byr)
                smp = [t for _ in keys for t in byr[rng.choice(keys)]]   # root-clustered
                boot.append(sum(t * wt for t, wt, _ in smp) / sum(wt for _, wt, _ in smp))
            boot.sort()
            out["rms_relative_bias"][cfg] = {"mean_square": m2, "rms": math.sqrt(max(0.0, m2)),
                                             "mean_square_ci": [boot[50], boot[1949]], "pairs": len(terms)}
    json.dump(out, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
