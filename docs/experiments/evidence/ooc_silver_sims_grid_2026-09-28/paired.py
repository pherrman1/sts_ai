import csv, glob, math, os, re
E = os.path.dirname(os.path.abspath(__file__))
R = {}
for p in glob.glob(f"{E}/runs/s*_o*_seed*.csv"):
    m = re.search(r"s(\d+)_o(\d+)_seed(\d+)\.csv$", p); r = list(csv.DictReader(open(p)))
    if r: R[(int(m[1]), int(m[2]), int(m[3]))] = r[0]
seeds = sorted({k[2] for k in R})
def paired(a, b):
    d = [int(R[b+(s,)]['won']) - int(R[a+(s,)]['won']) for s in seeds]
    df = [float(R[b+(s,)]['floor']) - float(R[a+(s,)]['floor']) for s in seeds]
    n = len(d); md = sum(d)/n; sd = math.sqrt(sum((x-md)**2 for x in d)/(n-1))
    mf = sum(df)/n; sf = math.sqrt(sum((x-mf)**2 for x in df)/(n-1))
    t = 2.04  # t_{0.975, 31}
    up = sum(x == 1 for x in d); dn = sum(x == -1 for x in d)
    return f"{a} -> {b}: win {100*md:+.1f} pp [{100*(md-t*sd/math.sqrt(n)):+.1f}, {100*(md+t*sd/math.sqrt(n)):+.1f}] (discordant +{up}/-{dn}); floor {mf:+.2f} [{mf-t*sf/math.sqrt(n):+.2f}, {mf+t*sf/math.sqrt(n):+.2f}]"
for a, b in [((1000,1000),(10000,1000)), ((10000,1000),(100000,1000)), ((1000,10000),(10000,10000)), ((10000,10000),(100000,10000)),
             ((1000,1000),(1000,10000)), ((10000,1000),(10000,10000)), ((100000,1000),(100000,10000))]:
    print(paired(a, b))
