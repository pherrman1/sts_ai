#!/usr/bin/env python3
"""Leaf pilot interim training, step 2 (exploratory; plan in PLAN.md, written before this script was run).

usage: train_eval.py PREFIX[,PREFIX...] OUT.json
5-fold cross-fitting by unit (fold = sha256(unit) mod 5); every model trains on 4 folds (10% of those units for
early stopping) and predicts the 5th. Models: C (per act x variant constant D), L (default Silver leaf L, scale per
act), V0 (net-0420 value head, scale per act), H0 (MLP head on the frozen trunk + scalars, levels only), H1 / H1w
(H0 + CRN pair term, lambda 4 / 1), G (LightGBM on base features + change -> D).
Metrics on out-of-fold predictions: within-cell slope b of D on the predicted D (cell = act x variant), skill
1 - MSE/MSE(C), and level BCE/AUC on base copies; unit-cluster bootstrap (B=1000, seed 20261107).
"""
import collections, hashlib, json, os, sys
import numpy as np
import torch
import lightgbm as lgb
import warnings; warnings.filterwarnings('ignore')

PREFIX, OUT = sys.argv[1:3]
torch.set_num_threads(4)
rng_np = np.random.default_rng(20261107)
meta, _pl, _vl = [], [], []
for _p in PREFIX.split(','):               # several snapshot prefixes, comma-separated (no unit overlap allowed)
    meta += [json.loads(l) for l in open(_p + '.meta.jsonl')]
    _z = np.load(_p + '.npz'); _pl.append(_z['pooled']); _vl.append(_z['value'])
pooled, value = np.concatenate(_pl), np.concatenate(_vl).astype(np.float64)
assert len(meta) == len(pooled) == len(value)
# IPW (env TE_WEIGHTS = src_weights.py JSON): w = eligible / sampled of the fork's source run, on every copy and pair;
# all fits, losses, cell means and metrics are w-weighted. Without TE_WEIGHTS, w = 1 (the unweighted v2 run).
if os.environ.get('TE_WEIGHTS'):
    _SW = json.load(open(os.environ['TE_WEIGHTS']))
    wcopy = np.array([_SW[str(m['unit'])][str(m['seed'])][0] / _SW[str(m['unit'])][str(m['seed'])][1] for m in meta])
else:
    wcopy = np.ones(len(meta))
N = len(meta)
col = lambda k: np.array([m[k] for m in meta], dtype=np.float64)
y = col('y'); act = col('act').astype(int); unit = col('unit').astype(np.int64)
ROOM = {'NORMAL': 0, 'ELITE': 1, 'BOSS': 2}
room = np.array([ROOM.get(m['room'], 3) for m in meta], float)
hp, maxhp, gold = col('hp'), col('maxHp'), col('gold')
SC = np.stack([act, col('floor'), hp, maxhp, hp / np.maximum(maxhp, 1), gold, col('potionCount'),
               col('potionScore'), col('deathSave'), col('fairy'), col('lizardTail'), col('deck'), col('relics'),
               room, col('potionCapacity'), col('incense')], 1)
SC_NAMES = ['act', 'floor', 'hp', 'maxHp', 'hpFrac', 'gold', 'potionCount', 'potionScore', 'deathSave', 'fairy',
            'lizardTail', 'deck', 'relics', 'room', 'potionCapacity', 'incense']
silverL = col('silverL')
fold = np.array([int(hashlib.sha256(str(u).encode()).hexdigest(), 16) % 5 for u in unit])
# Pairs (base, variant) per fork.
forks = collections.defaultdict(dict)
for i, m in enumerate(meta):
    forks[(m['unit'], m['seed'], m['fork'])][m['variant']] = i
fork_id = np.zeros(N, np.int64)
pairs, pfam, pvar = [], [], []
for fi, (k, vs) in enumerate(forks.items()):
    for v, i in vs.items():
        fork_id[i] = fi
    if 'base' not in vs:
        continue
    for v, i in vs.items():
        if v != 'base':
            pairs.append((vs['base'], i)); pfam.append(meta[i]['family']); pvar.append(v)
pairs = np.array(pairs); pb, pv = pairs[:, 0], pairs[:, 1]
pfam = np.array(pfam); pvar = np.array(pvar)
D = y[pv] - y[pb]
pact = act[pb]; punit = unit[pb]; pfold = fold[pb]; wpair = wcopy[pb]
GROUPS = {'hp': ['hp:-3', 'hp:-8', 'hp:-15'], 'pot': ['pot'], 'maxhp': ['maxhp:-5'], 'gold': ['gold:-50']}
cell = np.array([f'{a}|{v if f != "pot" else "pot"}' for a, v, f in zip(pact, pvar, pfam)])
cellf = np.array([f'{c}|{k}' for c, k in zip(cell, fold[pb])])   # slope cells: act x variant x fold
print(f'copies {N}, forks {len(forks)}, pairs {len(pairs)}, units {len(set(unit))}', flush=True)

pred = {}  # model -> OOF predicted D per pair
lev = {}   # model -> OOF P(y) per copy


def fit_scale(dx, mask_train):
    """D_hat = c_act * dx, c_act least squares through the origin on training pairs, per act."""
    out = np.zeros(len(D))
    for a in (1, 2, 3, 4):
        tr = mask_train & (pact == a); den = (wpair[tr] * dx[tr] ** 2).sum()
        c = (wpair[tr] * dx[tr] * D[tr]).sum() / den if den > 0 else 0.0
        out[pact == a] = c * dx[pact == a]
    return out


# C, L, V0
pred['C'] = np.zeros(len(D)); pred['L'] = np.zeros(len(D)); pred['V0'] = np.zeros(len(D))
for k in range(5):
    tr, te = pfold != k, pfold == k
    for c in np.unique(cell):
        mc = cell == c
        trc = tr & mc
        pred['C'][te & mc] = (wpair[trc] * D[trc]).sum() / wpair[trc].sum() if trc.any() else 0.0
    pred['L'][te] = fit_scale(silverL[pv] - silverL[pb], tr)[te]
    pred['V0'][te] = fit_scale(value[pv] - value[pb], tr)[te]

# Platt scaling of the net's value for levels
lev['V0'] = np.zeros(N)
for k in range(5):
    tr, te = fold != k, fold == k
    a_, b_ = 0.0, 0.0
    vt = torch.tensor(value[tr]); yt = torch.tensor(y[tr]); wtr = torch.tensor(wcopy[tr])
    w = torch.zeros(2, dtype=torch.float64, requires_grad=True)
    opt = torch.optim.LBFGS([w], max_iter=200)
    def closure():
        opt.zero_grad(); l = torch.nn.functional.binary_cross_entropy_with_logits(w[0] * vt + w[1], yt, weight=wtr); l.backward(); return l
    opt.step(closure)
    lev['V0'][te] = torch.sigmoid(w[0] * torch.tensor(value[te]) + w[1]).detach().numpy()


# Heads on the frozen trunk
class Anchor(torch.nn.Module):
    """H2 (added after the first run, exploratory): logit = a*v + c + delta . [trunk, scalars], delta zero-init,
    (a, c) from Platt scaling of net-0420's value v on the training fold."""
    def __init__(self, d, a0, c0):
        super().__init__()
        self.a = torch.nn.Parameter(torch.tensor(float(a0))); self.c = torch.nn.Parameter(torch.tensor(float(c0)))
        self.lin = torch.nn.Linear(d, 1); torch.nn.init.zeros_(self.lin.weight); torch.nn.init.zeros_(self.lin.bias)
    def forward(self, x):
        return (self.a * x[:, :1] + self.c + self.lin(x[:, 1:]))


def train_head(lam, tr_mask, te_mask, seed, kind='mlp'):
    g = torch.Generator().manual_seed(seed)
    tr_units = np.unique(unit[tr_mask]); r = np.random.default_rng(seed); r.shuffle(tr_units)
    va_units = set(tr_units[: max(1, len(tr_units) // 10)].tolist())
    va = tr_mask & np.isin(unit, list(va_units)); fit = tr_mask & ~va
    X = np.concatenate([pooled, SC], 1).astype(np.float32)
    mu, sd = X[fit].mean(0), X[fit].std(0) + 1e-6
    yt = torch.tensor(y, dtype=torch.float32)
    wt = torch.tensor(wcopy, dtype=torch.float32); wp_t = torch.tensor(wpair, dtype=torch.float32)
    torch.manual_seed(seed)
    if kind == 'anchor':
        w = torch.zeros(2, dtype=torch.float64, requires_grad=True)
        vt_, yt_, wf_ = torch.tensor(value[fit]), torch.tensor(y[fit]), torch.tensor(wcopy[fit])
        o2 = torch.optim.LBFGS([w], max_iter=200)
        def cl():
            o2.zero_grad(); l = torch.nn.functional.binary_cross_entropy_with_logits(w[0] * vt_ + w[1], yt_, weight=wf_); l.backward(); return l
        o2.step(cl)
        Xt = torch.tensor(np.concatenate([value[:, None].astype(np.float32), (X - mu) / sd], 1))
        net = Anchor(X.shape[1], float(w[0]), float(w[1]))
        opt = torch.optim.AdamW([{'params': [net.a, net.c], 'weight_decay': 0.0},
                                 {'params': net.lin.parameters(), 'weight_decay': 1e-2}], lr=1e-3)
    else:
        Xt = torch.tensor((X - mu) / sd)
        net = torch.nn.Sequential(torch.nn.Linear(X.shape[1], 64), torch.nn.GELU(), torch.nn.Dropout(0.1),
                                  torch.nn.Linear(64, 1))
        for p_ in net.parameters():
            if p_.dim() > 1: torch.nn.init.xavier_uniform_(p_, generator=g)
        opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=1e-3)
    fit_forks = np.unique(fork_id[fit]); va_idx = np.where(va)[0]
    pair_fork = fork_id[pb]
    pv_t, pb_t, D_t = torch.tensor(pv), torch.tensor(pb), torch.tensor(D, dtype=torch.float32)
    va_pairs = np.isin(pair_fork, np.unique(fork_id[va]))

    def loss_on(idx_copies, pair_sel, train):
        net.train(train)
        logit = torch.zeros(N)
        lo = net(Xt[idx_copies]).squeeze(-1)
        logit = logit.index_put((torch.tensor(idx_copies),), lo)
        wi = wt[idx_copies]
        l = (torch.nn.functional.binary_cross_entropy_with_logits(lo, yt[idx_copies], reduction='none') * wi).sum() / wi.sum()
        if lam > 0 and pair_sel.any():
            ps = torch.tensor(np.where(pair_sel)[0])
            pr = torch.sigmoid(logit[pv_t[ps]]) - torch.sigmoid(logit[pb_t[ps]])
            l = l + lam * (((pr - D_t[ps]) ** 2) * wp_t[ps]).sum() / wp_t[ps].sum()
        return l

    best, best_state, bad = np.inf, None, 0
    copies_of = collections.defaultdict(list)
    for i in np.where(fit)[0]:
        copies_of[fork_id[i]].append(i)
    for ep in range(60):
        r.shuffle(fit_forks)
        for s in range(0, len(fit_forks), 256):
            bf = fit_forks[s:s + 256]
            idx = np.concatenate([copies_of[f] for f in bf])
            psel = np.isin(pair_fork, bf)
            opt.zero_grad(); l = loss_on(idx, psel, True); l.backward(); opt.step()
        with torch.no_grad():
            lv = float(loss_on(va_idx, va_pairs, False))
        if lv < best - 1e-5:
            best, bad = lv, 0; best_state = {k: v.clone() for k, v in net.state_dict().items()}
        else:
            bad += 1
            if bad >= 5: break
    net.load_state_dict(best_state); net.eval()
    with torch.no_grad():
        p_all = torch.sigmoid(net(Xt).squeeze(-1)).numpy().astype(np.float64)
    return p_all, ep


for name, lam, kind in (('H0', 0.0, 'mlp'), ('H1', 4.0, 'mlp'), ('H1w', 1.0, 'mlp'), ('H2', 4.0, 'anchor')):
    lev[name] = np.zeros(N); pred[name] = np.zeros(len(D)); eps = []
    for k in range(5):
        p_all, ep = train_head(lam, fold != k, fold == k, seed=1000 + k, kind=kind)
        te = fold == k; lev[name][te] = p_all[te]
        tp = pfold == k; pred[name][tp] = (p_all[pv] - p_all[pb])[tp]; eps.append(ep)
    print(name, 'epochs', eps, flush=True)

# G: LightGBM on pairs
base_feat = SC[pb]; dfeat = SC[pv] - SC[pb]
GX = np.concatenate([base_feat, dfeat[:, [2, 3, 5, 6, 7]]], 1)
pred['G'] = np.zeros(len(D)); g_iters = []
for k in range(5):
    tr = pfold != k; te = pfold == k
    tr_units = np.unique(punit[tr]); r = np.random.default_rng(2000 + k); r.shuffle(tr_units)
    va = tr & np.isin(punit, tr_units[: len(tr_units) // 10]); fit = tr & ~va
    m = lgb.LGBMRegressor(n_estimators=3000, learning_rate=0.02, num_leaves=15, min_child_samples=200,
                          subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, verbose=-1,
                          random_state=2000 + k, n_jobs=4)
    m.fit(GX[fit], D[fit], sample_weight=wpair[fit], eval_set=[(GX[va], D[va])], eval_sample_weight=[wpair[va]],
          callbacks=[lgb.early_stopping(100, verbose=False)])
    pred['G'][te] = m.predict(GX[te]); g_iters.append(int(m.best_iteration_ or 0))
print('G iters', g_iters, flush=True)

# Metrics with a unit-cluster bootstrap
units_u, uinv = np.unique(punit, return_inverse=True)
lev_units, linv = np.unique(unit, return_inverse=True)
B = 1000
W = rng_np.multinomial(len(units_u), np.full(len(units_u), 1 / len(units_u)), size=B).astype(float)


def slope_skill(model, sel):
    d, dh, dc, c = D[sel], pred[model][sel], pred['C'][sel], cellf[sel]
    ui = uinv[sel]; wip = wpair[sel]
    cells, ci = np.unique(c, return_inverse=True)

    def stats(w):
        w = w * wip
        # weighted cell centering
        sw = np.bincount(ci, w, len(cells)); sw = np.where(sw > 0, sw, 1)
        u = dh - (np.bincount(ci, w * dh, len(cells)) / sw)[ci]
        v = d - (np.bincount(ci, w * d, len(cells)) / sw)[ci]
        b = (w * u * v).sum() / max((w * u * u).sum(), 1e-12)
        sk = 1 - (w * (d - dh) ** 2).sum() / (w * (d - dc) ** 2).sum()
        return b, sk
    b0, s0 = stats(np.ones(sel.sum()))
    bs = np.array([stats(W[i][ui]) for i in range(B)])
    return {'b': b0, 'b_ci': np.percentile(bs[:, 0], [2.5, 97.5]).tolist(),
            'skill_bp': 1e4 * s0, 'skill_ci_bp': (1e4 * np.percentile(bs[:, 1], [2.5, 97.5])).tolist()}


def auc(p, t, w=None):
    """(weighted) AUC = P(p_pos > p_neg) with weights w_i w_j, ties count 1/2."""
    w = np.ones(len(p)) if w is None else w
    o = np.argsort(p, kind='mergesort'); p, t, w = p[o], t[o], w[o]
    _, start = np.unique(p, return_index=True); g_ = np.repeat(np.arange(len(start)), np.diff(np.append(start, len(p))))
    wn = np.bincount(g_, w * (t == 0)); wpos = np.bincount(g_, w * (t == 1))
    below = np.cumsum(wn) - wn
    return float((wpos * (below + 0.5 * wn)).sum() / (wpos.sum() * wn.sum()))


res = {'weighted': bool(os.environ.get('TE_WEIGHTS')), 'copies': N, 'forks': len(forks), 'pairs': len(pairs), 'units': int(len(lev_units)),
       'discordance_by_group': {}, 'models': {}}
for g, vs in GROUPS.items():
    sel = np.isin(np.where(pfam == 'pot', 'pot', pvar), vs)
    res['discordance_by_group'][g] = {'pairs': int(sel.sum()),
                                      'discordance': float((wpair[sel] * (D[sel] != 0)).sum() / wpair[sel].sum())}
for model in ('L', 'V0', 'H0', 'H1', 'H1w', 'H2', 'G'):
    out = {}
    for g, vs in GROUPS.items():
        sel = np.isin(np.where(pfam == 'pot', 'pot', pvar), vs)
        st = slope_skill(model, sel)
        # within-cell spread of the model's predicted D
        dh = pred[model][sel]; c = cellf[sel]
        ws_ = wpair[sel]; cm = {x: (ws_[c == x] * dh[c == x]).sum() / ws_[c == x].sum() for x in np.unique(c)}
        st['sd_within_pp'] = 100 * float(np.sqrt((ws_ * (dh - np.array([cm[x] for x in c])) ** 2).sum() / ws_.sum()))
        out[g] = st
    if model in lev:
        bm = np.array([m['variant'] == 'base' for m in meta])
        p = np.clip(lev[model][bm], 1e-6, 1 - 1e-6); t = y[bm]; wb = wcopy[bm]
        out['levels'] = {'bce': float((wb * -(t * np.log(p) + (1 - t) * np.log(1 - p))).sum() / wb.sum()),
                         'auc': auc(p, t, wb)}
    res['models'][model] = out
# mean predicted vs observed D per act x group (pp)
res['cells_pp'] = {}
for a in (1, 2, 3, 4):
    for g, vs in GROUPS.items():
        sel = (pact == a) & np.isin(np.where(pfam == 'pot', 'pot', pvar), vs)
        if sel.sum() == 0: continue
        ws_ = wpair[sel]
        res['cells_pp'][f'{a}|{g}'] = {'pairs': int(sel.sum()), 'obs': 100 * float((ws_ * D[sel]).sum() / ws_.sum()),
                                        **{m: 100 * float((ws_ * pred[m][sel]).sum() / ws_.sum())
                                           for m in ('C', 'L', 'V0', 'H1', 'H2', 'G')}}
_bm = np.array([m['variant'] == 'base' for m in meta]); base_rate = float((wcopy[_bm] * y[_bm]).sum() / wcopy[_bm].sum())
pc = np.clip(np.full(1, base_rate), 1e-6, 1 - 1e-6)[0]
res['levels_constant_bce'] = float(-(base_rate * np.log(pc) + (1 - base_rate) * np.log(1 - pc)))
json.dump(res, open(OUT, 'w'), indent=1, default=float)
np.savez(OUT.replace('.json', '') + '.oof.npz', D=D, pb=pb, pv=pv, cell=cell, cellf=cellf, pfam=pfam, pvar=pvar,
         **{'pred_' + k: v for k, v in pred.items()}, **{'lev_' + k: v for k, v in lev.items()})
print(json.dumps({m: {g: (round(v['b'], 2), [round(x, 2) for x in v['b_ci']], round(v['skill_bp'], 1))
                      for g, v in d.items() if g != 'levels'} for m, d in res['models'].items()}, indent=1))
print(json.dumps({m: d.get('levels') for m, d in res['models'].items()}))
