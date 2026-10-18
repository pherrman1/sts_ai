"""Gen-7 prior A/B analysis (PREREG.md). Reads every A-u*.jsonl.gz / B-u*.jsonl.gz under DIR (the extracted worker
tars), pairs fights by (seed, replicate), and reports the paired win-rate difference B - A (g7_E - g6_E) with a
cluster bootstrap over source runs (10,000 resamples, numpy seed 0), plus the secondary end-HP difference.
usage: python3 analyze.py DIR OUT.json"""
import glob, gzip, json, os, sys
import numpy as np

d, out_path = sys.argv[1:3]
fights = {"A": {}, "B": {}}
for arm in fights:
    paths = sorted(glob.glob(os.path.join(d, "**", f"{arm}-u*.jsonl.gz"), recursive=True))
    for p in paths:
        with gzip.open(p, "rt") as f:
            for line in f:
                if '"kind":"fight"' not in line:
                    continue
                r = json.loads(line)
                k = (r["seed"], r["perturbation"]["replicate"])
                assert k not in fights[arm], f"duplicate fight {arm} {k}"
                fights[arm][k] = r
keys = sorted(set(fights["A"]) & set(fights["B"]))
only = {a: len(set(fights[a]) - set(keys)) for a in fights}
rows = []
for k in keys:
    a, b = fights["A"][k], fights["B"][k]
    assert a["perturbation"]["sourceSeed"] == b["perturbation"]["sourceSeed"] and a["encounter"] == b["encounter"]
    assert a["preHp"] == b["preHp"], k
    rows.append((a["perturbation"]["sourceSeed"], a["encounter"], int(a["won"]), int(b["won"]),
                 a["endHp"] if a["won"] else 0, b["endHp"] if b["won"] else 0, int(a["valid"] and b["valid"])))
src = np.array([r[0] for r in rows]); enc = np.array([r[1] for r in rows])
wa, wb, ha, hb, valid = (np.array([r[i] for r in rows], float) for i in range(2, 7))
runs, inv = np.unique(src, return_inverse=True)
rng = np.random.default_rng(0)


def summary(mask):
    n = int(mask.sum())
    if n == 0:
        return {"pairs": 0}
    dw, dh = (wb - wa)[mask], (hb - ha)[mask]
    cl = inv[mask]; ncl = len(runs)
    sw = np.bincount(cl, dw, ncl); sh = np.bincount(cl, dh, ncl); cnt = np.bincount(cl, minlength=ncl)
    used = np.flatnonzero(cnt)
    bw, bh = [], []
    for _ in range(10000):
        pick = rng.choice(used, len(used))
        c = cnt[pick].sum()
        bw.append(sw[pick].sum() / c); bh.append(sh[pick].sum() / c)
    return {"pairs": n, "source_runs": int(len(used)), "winA": float(wa[mask].mean()), "winB": float(wb[mask].mean()),
            "dWin": float(dw.mean()), "dWin_ci95": [float(x) for x in np.percentile(bw, [2.5, 97.5])],
            "endHpA": float(ha[mask].mean()), "endHpB": float(hb[mask].mean()), "dEndHp": float(dh.mean()),
            "dEndHp_ci95": [float(x) for x in np.percentile(bh, [2.5, 97.5])],
            "discordant": {"B_only_win": int(((wb == 1) & (wa == 0))[mask].sum()),
                           "A_only_win": int(((wa == 1) & (wb == 0))[mask].sum())}}


res = {"fights": {a: len(fights[a]) for a in fights}, "unpaired": only, "invalid_pairs": int((valid == 0).sum()),
       "all": summary(np.ones(len(rows), bool))}
for e in sorted(set(enc)):
    res[e] = summary(enc == e)
lo, hi = res["all"]["dWin_ci95"]
res["verdict"] = "SHOWN" if lo > 0 else ("HARM" if hi < 0 else "NOT_SHOWN")
json.dump(res, open(out_path, "w"), indent=1)
print(json.dumps(res))
