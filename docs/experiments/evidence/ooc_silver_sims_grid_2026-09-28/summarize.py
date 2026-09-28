import csv, glob, math, os, re, sys, json
G = os.path.dirname(os.path.abspath(__file__))
rows = {}
for p in glob.glob(f"{G}/runs/*.csv"):
    m = re.search(r"s(\d+)_o(\d+)_seed(\d+)\.csv$", p)
    if not m: continue
    r = list(csv.DictReader(open(p)))
    if not r: continue
    rows[(int(m[1]), int(m[2]), int(m[3]))] = r[0]
def wilson(k, n, z=1.96):
    if n == 0: return (float('nan'),)*2
    ph = k/n; d = 1+z*z/n; c = ph+z*z/(2*n); h = z*math.sqrt(ph*(1-ph)/n+z*z/(4*n*n))
    return ((c-h)/d, (c+h)/d)
S = [1000, 10000, 100000]
out = []
print(f"{'silver':>7} {'ooc':>7} {'n':>3} {'wins':>4} {'win%':>6} {'95% CI':>15} {'floor':>6} {'s/run':>8}")
for s in S:
    for o in S:
        rs = [v for (a,b,_),v in rows.items() if a==s and b==o]
        n = len(rs); k = sum(int(v['won']) for v in rs)
        if n == 0:
            print(f"{s:>7} {o:>7} {0:>3}  (pending)"); continue
        lo, hi = wilson(k, n)
        fl = sum(float(v['floor']) for v in rs)/n; sec = sum(float(v['sec']) for v in rs)/n
        print(f"{s:>7} {o:>7} {n:>3} {k:>4} {100*k/n:>5.1f}% [{100*lo:4.1f},{100*hi:5.1f}] {fl:>6.2f} {sec:>8.1f}")
        out.append(dict(silver=s, ooc=o, n=n, wins=k, win_rate=k/n, wilson95=[lo,hi], mean_floor=fl, mean_sec=sec))
json.dump(out, open(f"{G}/summary.json","w"), indent=1)
