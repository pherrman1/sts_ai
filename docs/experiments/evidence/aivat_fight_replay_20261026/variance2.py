import json, numpy as np
S = json.load(open('scored2.json'))
PAIRS = {'676': [('C', 'A')], '661': [('M', 'A'), ('S', 'A'), ('MS', 'A')], '683': [('MAP', 'OFF'), ('D', 'OFF')]}
SUB = {'bosses+act4': lambda a, rc: rc == 'BOSS' or a == 4,
       'heart': lambda a, rc: a == 4 and rc == 'BOSS',
       'act4': lambda a, rc: a == 4,
       'boss+elite': lambda a, rc: rc in ('BOSS', 'ELITE'),
       'all fights': lambda a, rc: True}
rng = np.random.default_rng(0)
def boot(d, n=4000):
    idx = rng.integers(0, len(d), (n, len(d))); m = d[idx].mean(1); return np.percentile(m, [2.5, 97.5])
out = {}
for ds, pairs in PAIRS.items():
    by = {}
    for r in S[ds]:
        by[(r['arm'], r['seed'])] = r
    seeds = sorted({r['seed'] for r in S[ds]})
    def arr(arm, sub):
        y = np.array([by[(arm, s)]['y'] for s in seeds], float)
        C = np.array([sum(V - E for a, rc, o, hp, V, E, vr in by[(arm, s)]['f'] if SUB[sub](a, rc)) for s in seeds])
        Q = np.array([sum(vr for a, rc, o, hp, V, E, vr in by[(arm, s)]['f'] if SUB[sub](a, rc)) for s in seeds])
        return y, C, Q
    for b, a in pairs:
        yb, _, _ = arr(b, 'heart'); ya, _, _ = arr(a, 'heart')
        D = yb - ya; sd0 = D.std(ddof=1)
        res = dict(n=len(seeds), raw_diff=D.mean(), raw_ci=list(boot(D)), sd_raw=sd0,
                   sd_unpaired=np.sqrt(yb.var(ddof=1) + ya.var(ddof=1)))
        for sub in SUB:
            _, cb, qb = arr(b, sub); _, ca, qa = arr(a, sub)
            DC = cb - ca; Dh = D - DC
            row = dict(sd_beta1=Dh.std(ddof=1), diff=Dh.mean(), ci=list(boot(Dh)),
                       meanC_b=cb.mean(), meanC_a=ca.mean(), biasDC=DC.mean(), biasDC_ci=list(boot(DC)))
            for m in (1, 2, 4, 8):
                pen = (qa + qb).mean() / m
                beta = np.cov(D, DC)[0, 1] / (DC.var(ddof=1) + pen)
                row[f'sd_replay_m{m}'] = np.sqrt((D - beta * DC).var(ddof=1) + beta ** 2 * pen)
                row[f'beta_m{m}'] = beta
            res[sub] = row
        out[f'{ds} {b}-{a}'] = res
def f(x): return f'{x:.3f}'
for k, r in out.items():
    print(f"\n== {k}: n={r['n']} raw diff {100*r['raw_diff']:+.2f} pp CI [{100*r['raw_ci'][0]:+.2f},{100*r['raw_ci'][1]:+.2f}]  SD paired {f(r['sd_raw'])} (unpaired {f(r['sd_unpaired'])})")
    for sub in SUB:
        x = r[sub]
        print(f"  {sub:11s} exact-E SD {f(x['sd_beta1'])} ({x['sd_beta1']/r['sd_raw']:.2f}x) diff {100*x['diff']:+.2f} [{100*x['ci'][0]:+.2f},{100*x['ci'][1]:+.2f}]"
              f" | model-bias dC {100*x['biasDC']:+.2f} [{100*x['biasDC_ci'][0]:+.2f},{100*x['biasDC_ci'][1]:+.2f}] meanC {100*x['meanC_a']:+.2f}/{100*x['meanC_b']:+.2f}"
              f" | replay SD m1 {f(x['sd_replay_m1'])} m2 {f(x['sd_replay_m2'])} m4 {f(x['sd_replay_m4'])} m8 {f(x['sd_replay_m8'])}")
json.dump(out, open('variance2.json', 'w'), indent=1, default=float)
