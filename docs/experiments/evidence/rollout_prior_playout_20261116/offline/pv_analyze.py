#!/usr/bin/env python3
"""Analysis of one_combat playoutvaluebench on the factory's validation rows.

usage: python3 -I pv_analyze.py ROWS.jsonl OUT1.jsonl [OUT2.jsonl ...] RESULT.json
Per arm and row group: the mean playout score (N playouts) against
  ref   = the played fight's recorded score (G16's actual outcome from this root on; roots only, unbiased, noisy),
  qb    = the row's recorded max-backed root value (16k search for roots, 2k label search for extra rows; both
          searches use g7f_E playouts, so this reference leans toward g7f_E),
and the win fraction against the fight's result (Brier). Paired arm - g7f_E differences with a seed bootstrap.
"""
import collections, json, sys
import numpy as np


def main(rows_path, *rest):
    outs, res_path = rest[:-1], rest[-1]
    meta = {}
    for l in open(rows_path):
        r = json.loads(l)
        meta[(int(r["seed"]), int(r["fight"]), int(r["decision"]))] = r["k"]
    data = collections.defaultdict(dict)   # (key) -> arm -> (mean score, win frac)
    errors = collections.Counter()
    for p in outs:
        for l in open(p):
            r = json.loads(l)
            if "error" in r:
                errors[r["error"][:60]] += 1
                continue
            arm = r["arm"].split("/")[-1].replace(".txt", "")
            k = (int(r["seed"]), int(r["fight"]), int(r["decision"]))
            data[k][arm] = (float(np.mean(r["scores"])), r["wins"] / r["playouts"], float(np.var(r["scores"])))
    arms = sorted({a for v in data.values() for a in v})
    keys = [k for k, v in data.items() if all(a in v for a in arms)]
    seeds = np.array([k[0] for k in keys])
    useed, inv = np.unique(seeds, return_inverse=True)
    kind = np.array([meta[k]["kind"] for k in keys])
    enc = np.array([meta[k]["enc"] for k in keys])
    qb = np.array([float(meta[k]["qb"]) for k in keys])
    has_ref = np.array([meta[k]["ref"] is not None for k in keys])
    ref = np.array([float(meta[k]["ref"]["score"]) if meta[k]["ref"] else np.nan for k in keys])
    won = np.array([float(meta[k]["ref"]["won"] in (True, "True")) if meta[k]["ref"] else np.nan for k in keys])
    M = {a: np.array([data[k][a][0] for k in keys]) for a in arms}
    W = {a: np.array([data[k][a][1] for k in keys]) for a in arms}
    rng = np.random.default_rng(20261116)
    B = rng.integers(0, len(useed), (1000, len(useed)))

    def boot(x, m):
        s = np.bincount(inv[m], x[m], len(useed)); n = np.bincount(inv[m], None, len(useed))
        bs = s[B].sum(1) / np.maximum(n[B].sum(1), 1)
        return float(s.sum() / n.sum()), [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))]

    groups = {"root": kind == "root", "tree": kind == "tree", "playout": kind == "playout",
              "root/heart": (kind == "root") & (enc == "THE_HEART"),
              "root/shield-spear": (kind == "root") & (enc == "SHIELD_AND_SPEAR"),
              "root/act1-3 bosses": (kind == "root") & ~np.isin(enc, ["THE_HEART", "SHIELD_AND_SPEAR"])}
    res = {"rows": len(keys), "seeds": int(len(useed)), "arms": arms, "errors": dict(errors), "groups": {}}
    for g, m in groups.items():
        if not m.any():
            continue
        e = {"rows": int(m.sum())}
        for a in arms:
            d = {"mean": float(M[a][m].mean()), "mse_qb": float(((M[a] - qb)[m] ** 2).mean()),
                 "bias_qb": float((M[a] - qb)[m].mean())}
            mr = m & has_ref
            if mr.any():
                d.update(mse_ref=float(((M[a] - ref)[mr] ** 2).mean()), bias_ref=float((M[a] - ref)[mr].mean()),
                         brier=float(((W[a] - won)[mr] ** 2).mean()), win=float(W[a][mr].mean()),
                         corr_ref=float(np.corrcoef(M[a][mr], ref[mr])[0, 1]))
            if a != "g7f_E":
                d["d_mse_qb"] = boot((M[a] - qb) ** 2 - (M["g7f_E"] - qb) ** 2, m)
                if mr.any():
                    d["d_mse_ref"] = boot((M[a] - ref) ** 2 - (M["g7f_E"] - ref) ** 2, mr)
                    d["d_brier"] = boot((W[a] - won) ** 2 - (W["g7f_E"] - won) ** 2, mr)
            e[a] = d
        if (m & has_ref).any():
            e["ref_win"] = float(won[m & has_ref].mean()); e["ref_mean"] = float(ref[m & has_ref].mean())
        res["groups"][g] = e
    json.dump(res, open(res_path, "w"), indent=1)
    for g, e in res["groups"].items():
        print(f"== {g}: rows {e['rows']}" + (f", ref win {e.get('ref_win', 0):.3f}" if "ref_win" in e else ""))
        for a in arms:
            d = e[a]
            line = f"  {a:8s} mean {d['mean']:7.2f} mse_qb {d['mse_qb']:8.1f}"
            if "mse_ref" in d:
                line += f" mse_ref {d['mse_ref']:8.1f} bias_ref {d['bias_ref']:+6.2f} brier {d['brier']:.4f} corr {d['corr_ref']:.3f}"
            for k in ("d_mse_ref", "d_brier", "d_mse_qb"):
                if k in d:
                    line += f"  {k} {d[k][0]:+.3f} [{d[k][1][0]:+.3f},{d[k][1][1]:+.3f}]"
            print(line)


if __name__ == "__main__":
    main(*sys.argv[1:])
