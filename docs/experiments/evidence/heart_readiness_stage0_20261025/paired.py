import pickle, glob, numpy as np
G = {}
for f in glob.glob('p683_*.pkl') + glob.glob('p676_*.pkl'):
    src = '683' if '683' in f else '676'
    for (s, a), v in pickle.load(open(f, 'rb')).items():
        if v: G[(src, s, a)] = v
lg = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
rng = np.random.default_rng(2)
PAIRS = [('683', 'MAP', 'OFF'), ('683', 'D', 'MAP'), ('683', 'D', 'OFF'), ('676', 'C', 'A')]
sig = lambda f: (f['enc'], f['floor'], f['curHp'], f['maxHp'], f['deck'], f['upg'], f['gold'], round(f['rF'], 9))

def seed_ci(R, key, n=2000):  # bootstrap over seeds (one seed can carry up to three dependent §683 pairs)
    by = {}
    for r in R:
        if r['dk'] != 0: by.setdefault(r['seed'], []).append(r)
    us = sorted(by); bs = []
    for _ in range(n):
        j = [r for u in rng.choice(us, len(us)) for r in by[u]]
        bs.append(conc([r[key] for r in j], [r['dk'] for r in j])[0])
    return np.percentile(bs, 2.5), np.percentile(bs, 97.5)


def conc(d, k):  # share of discordant-kill pairs where the killer has the larger value; ties = 1/2
    d, k = np.asarray(d), np.asarray(k)
    m = k != 0
    s = np.sign(d[m]) * k[m]
    return (np.sum(s > 0) + 0.5 * np.sum(s == 0)) / max(m.sum(), 1), int(m.sum()), int(np.sum(s == 0))

for mode in ('first_diff_fight', 'act3_entry', 'act4_entry'):
    rec = []
    for src, x, y in PAIRS:
        for s in sorted({k[1] for k in G if k[0] == src}):
            if (src, s, x) not in G or (src, s, y) not in G: continue
            gx, gy = G[(src, s, x)], G[(src, s, y)]
            if mode == 'first_diff_fight':
                fx, fy = gx['fights'], gy['fights']
                i = next((i for i in range(min(len(fx), len(fy))) if sig(fx[i]) != sig(fy[i])), None)
                if i is None: continue
                a, b = fx[i], fy[i]
            else:
                act = 3 if mode == 'act3_entry' else 4
                a = next((f for f in gx['fights'] if f['act'] == act), None); b = next((f for f in gy['fights'] if f['act'] == act), None)
                if not a or not b: continue
            rec.append(dict(seed=src + s, pair=f'{x}-{y}', dk=gx['kill'] - gy['kill'], dr=lg(a['rF']) - lg(b['rF']), dra=lg(a['rA']) - lg(b['rA']),
                            dhp=a['curHp'] - b['curHp'], dmax=a['maxHp'] - b['maxHp'], ddeck=a['deck'] - b['deck'], act=a['act'],
                            same_floor=a['floor'] == b['floor']))
    print(f'== {mode}: pairs {len(rec)}')
    for sub, R in (('all', rec), ('same_floor', [r for r in rec if r['same_floor']])):
        dk = [r['dk'] for r in R]
        out = []
        for key in ('dr', 'dra', 'dhp', 'dmax', 'ddeck'):
            c, n, t = conc([r[key] for r in R], dk)
            lo, hi = seed_ci(R, key)
            out.append(f'{key} {c:.3f} [{lo:.3f},{hi:.3f}] ties {t}')
        print(f'  {sub}: discordant-kill pairs {n}; ' + ' | '.join(out))
    # residual: within same-HP-direction strata, does dr add? logistic on discordant pairs: P(x killer) ~ dr + dhp + dmax (no intercept)
    R = [r for r in rec if r['dk'] != 0]
    if R:
        from sklearn.linear_model import LogisticRegression
        X = np.array([[r['dhp'], r['dmax'], r['ddeck'], r['dr']] for r in R], float); yk = np.array([r['dk'] > 0 for r in R])
        X = np.vstack([X, -X]); yk = np.concatenate([yk, ~yk])  # symmetric, no intercept
        sd = X.std(0) + 1e-9
        m = LogisticRegression(fit_intercept=False, C=1e3).fit(X / sd, yk)
        coefs = []
        for _ in range(500):
            j = rng.integers(0, len(R), len(R)); jj = np.concatenate([j, j + len(R)])
            coefs.append(LogisticRegression(fit_intercept=False, C=1e3).fit(X[jj] / sd, yk[jj]).coef_[0])
        lo, hi = np.percentile(coefs, [2.5, 97.5], axis=0)
        print('  std coefs dhp,dmax,ddeck,dr:', np.round(m.coef_[0], 3), 'CI lo', np.round(lo, 3), 'hi', np.round(hi, 3))
    for pr in ('MAP-OFF', 'D-MAP', 'D-OFF', 'C-A'):
        Rp = [r for r in rec if r['pair'] == pr]
        if Rp: print(f'  {pr}: n {len(Rp)} mean dr {np.mean([r["dr"] for r in Rp]):+.3f} mean dhp {np.mean([r["dhp"] for r in Rp]):+.2f} conc dr {conc([r["dr"] for r in Rp],[r["dk"] for r in Rp])[:2]}')
print('== first_diff_fight by act, deck-changed only (|dr|>0.05)')
rec = []
for src, x, y in PAIRS:
    for s in sorted({k[1] for k in G if k[0] == src}):
        if (src, s, x) not in G or (src, s, y) not in G: continue
        gx, gy = G[(src, s, x)], G[(src, s, y)]
        fx, fy = gx['fights'], gy['fights']
        i = next((i for i in range(min(len(fx), len(fy))) if sig(fx[i]) != sig(fy[i])), None)
        if i is None: continue
        a, b = fx[i], fy[i]
        # also the fight 3 fights later (if both have it)
        later = (fx[i + 3], fy[i + 3]) if i + 3 < min(len(fx), len(fy)) else None
        rec.append(dict(seed=src + s, dk=gx['kill'] - gy['kill'], dr=lg(a['rF']) - lg(b['rF']), dhp=a['curHp'] - b['curHp'], act=a['act'],
                        dr3=(lg(later[0]['rF']) - lg(later[1]['rF'])) if later else None))
for act in (1, 2, 3):
    R = [r for r in rec if r['act'] == act and abs(r['dr']) > 0.05]
    c = conc([r['dr'] for r in R], [r['dk'] for r in R]); h = conc([r['dhp'] for r in R], [r['dk'] for r in R])
    R3 = [r for r in rec if r['act'] == act and r['dr3'] is not None]
    c3 = conc([r['dr3'] for r in R3], [r['dk'] for r in R3])
    lo, hi = seed_ci(R, 'dr')
    print(f'  act {act}: n {len(R)} conc dr {c[0]:.3f} [{lo:.3f},{hi:.3f}] (disc {c[1]}), dhp {h[0]:.3f}; 3 fights later conc dr {c3[0]:.3f} (disc {c3[1]})')
