"""#397 hidden-queue pilot analysis (pre-registered in PREREG.md). Usage: analyze.py PILOT_DIR"""
import csv, glob, json, math, os, re, sys
import random

def load(d, arm):
    rows = {}
    for f in sorted(glob.glob(f"{d}/{arm}-*.csv")):
        for r in csv.DictReader(open(f)):
            s = int(r["seed"]); assert s not in rows, f"duplicate {s}"
            rows[s] = r
    return rows

def receipts(d, arm):
    out = {}
    for f in glob.glob(f"{d}/{arm}-*.log"):
        for m in re.finditer(r"\[public OOC receipt seed=(\d+) futures=(\d+) scorers=(\d+)\]", open(f).read()):
            out[int(m[1])] = (int(m[2]), int(m[3]))
    return out

def boot(diffs, n=10000, seed=397):
    rng = random.Random(seed); k = len(diffs)
    ms = sorted(sum(diffs[rng.randrange(k)] for _ in range(k)) / k for _ in range(n))
    return ms[int(0.025 * n)], ms[int(0.975 * n) - 1]

def mcnemar(b, c):
    n = b + c
    if n == 0: return 1.0
    p = sum(math.comb(n, i) for i in range(0, min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * p)

def main(d):
    seeds = list(range(74015000, 74015128))
    L, P = load(d, "legacy"), load(d, "public8")
    rc = [open(f).read().strip() for f in sorted(glob.glob(f"{d}/*.done"))]
    valid = all(s in L and s in P for s in seeds) and len(L) == len(P) == 128 and all(x.endswith("rc=0") for x in rc)
    rp, rl = receipts(d, "public8"), receipts(d, "legacy")
    rec_ok = all(s in rp and rp[s][0] == 8 and rp[s][1] > 0 for s in seeds) and not any(v[1] > 0 for v in rl.values())
    res = {"valid": valid, "receipts_ok": rec_ok, "done": rc}
    if not valid:
        res["label"] = "INVALID"; print(json.dumps(res, indent=1)); return
    dw = [int(P[s]["won"]) - int(L[s]["won"]) for s in seeds]
    df = [int(P[s]["floor"]) - int(L[s]["floor"]) for s in seeds]
    lo, hi = boot(dw); flo, fhi = boot(df)
    b = sum(x == 1 for x in dw); c = sum(x == -1 for x in dw)
    label = "LEAK_HELPS" if hi < 0 else "PUBLIC8_BETTER" if lo > 0 else "LEAK_NOT_SHOWN"
    res.update({
        "wins_legacy": sum(int(L[s]["won"]) for s in seeds), "wins_public8": sum(int(P[s]["won"]) for s in seeds),
        "dwin_pp": 100 * sum(dw) / 128, "dwin_ci_pp": [100 * lo, 100 * hi],
        "public8_only_wins": b, "legacy_only_wins": c, "mcnemar_p": mcnemar(b, c),
        "dfloor": sum(df) / 128, "dfloor_ci": [flo, fhi],
        "sec_per_run_legacy": sum(float(L[s]["sec"]) for s in seeds) / 128,
        "sec_per_run_public8": sum(float(P[s]["sec"]) for s in seeds) / 128,
        "public_scorers_per_run": sum(rp[s][1] for s in seeds if s in rp) / 128,
        "seeds_same_outcome_and_floor": sum(L[s]["won"] == P[s]["won"] and L[s]["floor"] == P[s]["floor"] for s in seeds),
        "deaths_act_legacy": {a: sum(1 for s in seeds if L[s]["won"] == "0" and L[s]["act"] == a) for a in "123"},
        "deaths_act_public8": {a: sum(1 for s in seeds if P[s]["won"] == "0" and P[s]["act"] == a) for a in "123"},
        "label": label})
    print(json.dumps(res, indent=1))

if __name__ == "__main__":
    main(sys.argv[1])
