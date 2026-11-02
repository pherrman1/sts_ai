"""Value-gate checks (a) and (b) on the V_A4 data of #915 (value_a4_improve_20261030), offline, no seeds.

usage: VA4_DATA=DIR va4_checks.py OUT.json        (DIR holds a4.pkl, run1_a4.pkl, more_a4.pkl as in #915's README)

Same protocol as #915: dev pool seed % 4 != 3, 5-fold CV grouped by seed x 3 fold assignments, scored on dev core
entries (stage-2 + run-1), per-game BCE and Brier R2, paired seed-cluster bootstrap (core.paired).
(a) Incense-holder subgroup: ENS_rc (with relic-counter one-hots) - ENS_all (without), on Incense holders vs the
    rest vs all; plus ENS_all + per-phase logit offsets fitted out of fold on holders only (minimal-capacity probe).
(b) learning curve: ENS_rc trained on nested seed subsets (fraction 1/8, 1/4, 1/2, 1 of each fold's training seeds,
    hash rule), test folds unchanged; R2 and BCE per point, power-law fits R2(n) = Rinf - a n^-b, extrapolated to
    n = 1e5 training entries, with a seed bootstrap of the fit.
"""
import sys, os, json, hashlib
import numpy as np
T = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'value_a4_improve_20261030', 'tools')
sys.path.insert(0, os.path.abspath(T))
import core, feats  # noqa: E402
from exp3lib import xg, lr  # noqa: E402
from scipy.optimize import curve_fit  # noqa: E402

out = sys.argv[1]
d = core.build(2); recs = [e['entry']['record'] for e in core.entries(2)]
E = feats.eng(recs); RC = feats.relic_counters(recs); CS = feats.card_state(recs)
lce = core.logit(d['ce']); cp = core.logit((1 - d['ce'][:, 0]) * (1 - d['ce'][:, 1]))
X0 = np.hstack([d['X'], cp[:, None], lce, E, np.c_[d['src'] == 'run1', d['strong'], np.zeros(len(d['y']))].astype(np.float32)])
XR = np.hstack([X0, RC, CS]); y, n = d['y'], d['n']
pool = (d['seed'] % 4) != 3; dc = pool & (d['src'] != 'extra')
inc = RC[:, 0:6]; hold = inc.sum(1) > 0
R = {'rows': int(len(y)), 'dev_core_rows': int(dc.sum()), 'dev_core_games': float(n[dc].sum()), 'features_X0': int(X0.shape[1]), 'features_XR': int(XR.shape[1])}
print(json.dumps(R), flush=True)

# ---------- (a)
P = {}
for k, X in (('all', X0), ('rc', XR)):
    g = core.oof(xg(X, y, n), d, pool); l = core.oof(lr(X, y, n, 0.003), d, pool)
    P['ENS_' + k] = (g + l) / 2
# per-phase logit offsets on top of ENS_all, fitted out of fold (same folds) on holders of the training folds
Pp = np.full_like(P['ENS_all'], np.nan)
for ri, rep in enumerate((0, 1, 2)):
    fo = core.folds(d['seed'], 5, rep); base = core.logit(P['ENS_all'][ri])
    for f in range(5):
        te = pool & (fo == f); tr = pool & (fo != f) & hold
        off = np.zeros(6)
        for ph in range(6):  # one Newton-free 1-d fit per phase: minimise weighted BCE of sigmoid(base + o)
            m = tr & (inc[:, ph] > 0)
            if m.sum() < 5: continue
            grid = np.linspace(-1, 1, 401)
            L = [float((core.wbce(1 / (1 + np.exp(-(base[m] + o))), y[m]) * n[m]).sum()) for o in grid]
            # ridge toward 0 (prior sd 0.5 on the logit) so tiny phases do not overfit
            L = np.array(L) + 0.5 * (grid / 0.5) ** 2
            off[ph] = grid[int(np.argmin(L))]
        adj = base.copy()
        for ph in range(6):
            mm = te & (inc[:, ph] > 0); adj[mm] = base[mm] + off[ph]
        Pp[ri, te] = 1 / (1 + np.exp(-adj[te]))
P['ENS_all+phase'] = Pp
A = {}
for gname, gm in (('all', dc), ('incense_holders', dc & hold), ('non_holders', dc & ~hold)):
    w = n[gm]; pb = float((y[gm] * w).sum() / w.sum())
    A[gname] = {'rows': int(gm.sum()), 'games': float(w.sum()), 'seeds': int(len(np.unique(d['seed'][gm]))), 'kill_rate': pb}
    for k in P:
        s = core.score(P[k], d, gm)['all']; A[gname][k] = {'bce': s['bce'], 'r2': s['r2']}
    for a_, b_ in (('ENS_rc', 'ENS_all'), ('ENS_all+phase', 'ENS_all')):
        A[gname][f'{a_} - {b_}'] = core.paired(core.per_seed_loss(P[a_], d, gm), core.per_seed_loss(P[b_], d, gm), d, gm)
# observed kill rate by entry phase (dev core holders) and the BCE an ideal phase term would buy (pi * D^2 / (2p(1-p)))
ph_rate = []
for ph in range(6):
    m = dc & (inc[:, ph] > 0); ph_rate.append([int(m.sum()), float((y[m] * n[m]).sum() / n[m].sum()) if m.any() else None])
A['phase_kill_rate_dev_core'] = ph_rate
p = A['incense_holders']['kill_rate']
A['ideal_gain_on_holders_for_D'] = {str(D): D * D / (2 * p * (1 - p)) for D in (0.03, 0.06, 0.12)}
A['holder_share_dev_core_games'] = A['incense_holders']['games'] / A['all']['games']
R['a'] = A
print(json.dumps(A, indent=1), flush=True)

# ---------- (b)
def u(s):
    return int(hashlib.sha256(str(int(s)).encode()).hexdigest()[:8], 16) / 2 ** 32
us = np.array([u(s) for s in d['seed']])
fracs = (0.125, 0.25, 0.5, 1.0)
curve = []; L_by_f = {}
for fr in fracs:
    keep = us < fr
    g = core.oof(xg(XR, y, n, trainmask=keep), d, pool); l = core.oof(lr(XR, y, n, 0.003, trainmask=keep), d, pool)
    Pf = (g + l) / 2
    # training size per fold: mean over folds and reps of kept training rows (entries) and games
    sizes = []
    for rep in (0, 1, 2):
        fo = core.folds(d['seed'], 5, rep)
        for f in range(5):
            m = pool & (fo != f) & keep; sizes.append((m.sum(), n[m].sum(), (m & d['strong']).sum()))
    sz = np.mean(sizes, 0)
    s = core.score(Pf, d, dc)
    row = {'frac': fr, 'train_entries': float(sz[0]), 'train_games': float(sz[1]), 'train_strong_entries': float(sz[2]),
           'bce': s['all']['bce'], 'r2': s['all']['r2'], 'r2_run1': s['run1']['r2'], 'bce_run1': s['run1']['bce']}
    curve.append(row); L_by_f[fr] = core.per_seed_loss(Pf, d, dc)
    print(json.dumps(row), flush=True)
    np.save(os.path.join(os.path.dirname(os.path.abspath(out)), f'lc_pred_{fr}.npy'), Pf)

def pl(x, r, a, b): return r - a * x ** (-b)
def fit(xs, ys):
    try:
        p, _ = curve_fit(pl, xs, ys, p0=(ys[-1] + 0.05, 1.0, 0.5), bounds=([-1, 0, 0.01], [1, 1e4, 3]), maxfev=20000)
        return p
    except Exception:
        return None
xs = np.array([c['train_entries'] for c in curve])
B = {}
for key in ('r2', 'r2_run1'):
    ys = np.array([c[key] for c in curve]); p_ = fit(xs, ys)
    B[key] = {'fit': None if p_ is None else dict(Rinf=p_[0], a=p_[1], b=p_[2]),
              'pred_1e5': None if p_ is None else float(pl(1e5, *p_)),
              'pred_4e4': None if p_ is None else float(pl(4e4, *p_)),
              'loglinear_slope_per_doubling': float(np.polyfit(np.log2(xs), ys, 1)[0]),
              'loglinear_pred_1e5': float(np.polyval(np.polyfit(np.log2(xs), ys, 1), np.log2(1e5)))}
# seed bootstrap of the R2 (all) curve: resample dev-core seeds, recompute R2 per point from per-entry Brier
sd = d['seed'][dc]; usd, inv = np.unique(sd, return_inverse=True)
Pfs = {fr: np.load(os.path.join(os.path.dirname(os.path.abspath(out)), f'lc_pred_{fr}.npy')) for fr in fracs}
yy, nn = y[dc], n[dc]
brier = {fr: np.mean([((p[dc] - yy) ** 2 + yy * (1 - yy)) * nn for p in Pfs[fr]], 0) for fr in fracs}
rng = np.random.default_rng(11); preds = []; preds_ll = []
for _ in range(1000):
    k = rng.integers(0, len(usd), len(usd)); wsum = np.bincount(inv, nn)[k].sum()
    ysum = np.bincount(inv, yy * nn)[k].sum(); pb = ysum / wsum
    b0 = (np.bincount(inv, ((pb - yy) ** 2 + yy * (1 - yy)) * nn)[k]).sum() / wsum
    ys = np.array([1 - np.bincount(inv, brier[fr])[k].sum() / wsum / b0 for fr in fracs])
    p_ = fit(xs, ys)
    if p_ is not None: preds.append(pl(1e5, *p_))
    preds_ll.append(np.polyval(np.polyfit(np.log2(xs), ys, 1), np.log2(1e5)))
B['r2']['pred_1e5_boot_ci'] = [float(np.percentile(preds, 2.5)), float(np.percentile(preds, 97.5))]
B['r2']['pred_1e5_boot_p_ge_0.33'] = float(np.mean(np.array(preds) >= 0.33))
B['r2']['loglinear_pred_1e5_boot_ci'] = [float(np.percentile(preds_ll, 2.5)), float(np.percentile(preds_ll, 97.5))]
# Bernoulli ceiling of the per-game Brier R2 on dev core, using run-1's within-entry outcome variance share 0.59 (§720)
B['curve'] = curve
R['b'] = B
print(json.dumps(B, indent=1), flush=True)
json.dump(R, open(out, 'w'), indent=1)
