# Screen1 analysis as in PREREG: tar xzf s1res.tgz && python3 analyze.py s1res result.json
import csv, glob, os, sys, json, re
import numpy as np
R = sys.argv[1]
LO, HI = 111410240, 111415359
arms = sorted(d for d in os.listdir(R) if os.path.isdir(os.path.join(R, d)))
data, curve, stall = {}, {}, {}
for a in arms:
    d = {}; c = {}
    for f in sorted(glob.glob(f"{R}/{a}/games-*.csv")):
        for r in csv.DictReader(open(f)):
            s = int(r["seed"]); k = int(r["heart_kill"]); it = int(r["iteration"])
            c.setdefault(it, []).append(k)
            if LO <= s <= HI: assert s not in d; d[s] = k
    data[a] = d; curve[a] = {i: np.mean(v) for i, v in c.items()}
    stall[a] = sorted(int(x) for x in re.findall(r"(\d{9})", open(f"{R}/{a}/stalled_seeds.txt").read()))
seeds = sorted(data["BASE"]); assert len(seeds) == 5120
for a in arms: assert sorted(data[a]) == seeds, a
allstall = set(s for a in arms for s in stall[a])
stall_last = sorted(s for s in allstall if LO <= s <= HI)
rng = np.random.default_rng(20261103)
idx = rng.integers(0, len(seeds), size=(10000, len(seeds)))
B = np.array([data["BASE"][s] for s in seeds])
def dstat(a, keep=None):
    x = np.array([data[a][s] for s in seeds]); dd = x - B
    if keep is not None: dd = dd[keep]
    i = idx if keep is None else np.random.default_rng(20261104).integers(0, len(dd), size=(10000, len(dd)))
    bs = dd[i].mean(1)
    return x.mean(), dd.mean(), np.percentile(bs, 2.5), np.percentile(bs, 97.5)
keep = np.array([s not in allstall for s in seeds])
noise = abs(dstat("BASE_S1")[1])
out = []
for a in arms:
    rate, d, lo, hi = dstat(a)
    _, ds, _, _ = dstat(a, keep)
    if a == "BASE": v = "-"
    elif lo > 0 and d > noise: v = "PROMISING"
    elif hi < 0: v = "WORSE"
    else: v = "NOT_SHOWN"
    st_last = sum(1 for s in stall[a] if LO <= s <= HI)
    out.append(dict(arm=a, rate=rate, D=d, lo=lo, hi=hi, Dsens=ds, verdict=v, stalls=len(stall[a]), stalls_last=st_last))
out.sort(key=lambda r: -r["D"])
print(f"noise |BASE_S1-BASE| = {100*noise:.2f} pp; stall seeds in last third: {stall_last}; kept {keep.sum()}")
print(f"{'arm':10s} {'rate%':>6s} {'D pp':>6s} {'CI':>16s} {'Dsens':>6s} {'stall(all/last)':>15s} verdict")
for r in out:
    print(f"{r['arm']:10s} {100*r['rate']:6.2f} {100*r['D']:+6.2f} [{100*r['lo']:+6.2f},{100*r['hi']:+6.2f}] {100*r['Dsens']:+6.2f} {r['stalls']:>7d}/{r['stalls_last']:<7d} {r['verdict']}")
# curves: first-third/middle/last-third rates (by seed block, comparable across G)
print("\ncurve by seed-third (rate%): first, middle, last; also first iteration (start net, pipeline) rate")
for a in arms:
    allrows = {}
    for f in glob.glob(f"{R}/{a}/games-*.csv"):
        for r in csv.DictReader(open(f)): allrows[int(r["seed"])] = int(r["heart_kill"])
    th = [np.mean([v for s, v in allrows.items() if l <= s <= h]) for l, h in [(111400000, 111405119), (111405120, 111410239), (LO, HI)]]
    print(f"{a:10s} " + " ".join(f"{100*x:5.2f}" for x in th))
json.dump(dict(noise=noise, stall_seeds_last_third=stall_last, arms=out), open(sys.argv[2] if len(sys.argv) > 2 else "result.json", "w"), indent=1)
