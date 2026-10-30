"""V_A4 improvement harness: build entries + features once, grouped CV on the dev pool (seed % 4 != 3)."""
import sys, os, pickle, collections, math
import numpy as np
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *['..'] * 5))
EV = os.path.join(REPO, 'docs/experiments/evidence')
sys.path.insert(0, os.path.join(EV, 'value_clean_labels_20261029', 'tools'))
sys.path.insert(0, os.path.join(EV, 'value_clean_labels_run1_20261029'))
import fit_a4 as F  # noqa
import fit_a4_run1 as R  # noqa
s0 = F.s0
D = os.environ.get('VA4_DATA', '.').rstrip('/') + '/'  # a4.pkl, run1_a4.pkl, more_a4.pkl, states_a4.pkl; design caches go here
EXTRA = {'ctm-calibration-ab', 'az-gen3-explore'}  # Act-4 not strong


def entries(include_extra=False):
    if include_extra == 2:
        es = entries(True); seen = set()
        for r in pickle.load(open(D + 'more_a4.pkl', 'rb')):
            if not r['reachedA4']: continue
            key = (r['seed'], repr(r['entry']['record']), r['heartKilled'])
            if key in seen: continue
            seen.add(key)
            es.append(dict(src='extra', camp=r['campaign'], seed=r['seed'], entry=r['entry'], ctm=[], kills=[r['heartKilled']], strong=False))
        return es
    st2 = pickle.load(open(D + 'a4.pkl', 'rb')); r1 = pickle.load(open(D + 'run1_a4.pkl', 'rb'))
    es, bad = R.entries(st2, r1)
    for e in es: e['strong'] = True; e['camp'] = e['src']
    if include_extra:
        for r in st2:
            if r['campaign'] in EXTRA and r['reachedA4']:
                es.append(dict(src='extra', camp=r['campaign'], seed=r['seed'], entry=r['entry'], ctm=r.get('ctm_a4', []),
                               kills=[r['heartKilled']], strong=False))
    return es


def ctm_entry_feats(rec, heart):
    """CTM feature dict from the Act-4 ENTRY record (no post-shop info)."""
    fo = rec['obs.fixed_observation']; cards = rec['obs.deck.cards']; ups = rec['obs.deck.upgrades']
    pots = [p for p in rec['obs.potions'] if p > 1]
    x = dict(heart=float(heart), cur_hp=fo[0], max_hp=fo[1], hp_frac=np.float32(fo[0]) / np.float32(max(fo[1], 1)), gold=fo[2],
             potion_capacity=len(rec['obs.potions']), potion_count=len(pots), deck_size=len(cards), upgraded=sum(1 for u in ups if u))
    for c in cards: x[f'card_{c}'] = x.get(f'card_{c}', 0) + 1
    for r in rec['obs.relics.relics']: x[f'relic_{r}'] = 1
    for p in pots: x[f'potion_{p}'] = x.get(f'potion_{p}', 0) + 1
    return x


def logit(p): p = np.clip(p, 1e-4, 1 - 1e-4); return np.log(p / (1 - p))


def build(include_extra=False, cache=True):
    fn = D + f'design_{int(include_extra)}.pkl'
    if cache and os.path.exists(fn): return pickle.load(open(fn, 'rb'))
    es = entries(include_extra)
    model = F.load_trees(os.path.join(REPO, 'models/candidates/ctm_act4_survival_trees.txt'))
    X, c_ss = R.design(es, model)  # base features + hp frac; c_ss = CTM at the S&S row (post-shop: LEAKS future)
    ce = np.zeros((len(es), 2))
    for i, e in enumerate(es):
        rec = e['entry']['record']
        ce[i, 0] = F.tree_pred(model, ctm_entry_feats(rec, 0)); ce[i, 1] = F.tree_pred(model, ctm_entry_feats(rec, 1))
    d = dict(X=X, c_ss=c_ss, ce=ce,
             n=np.array([len(e['kills']) for e in es], float), y=np.array([np.mean(e['kills']) for e in es]),
             y1=np.array([float(e['kills'][0]) for e in es]), seed=np.array([e['seed'] for e in es]),
             src=np.array([e['src'] for e in es]), camp=np.array([e['camp'] for e in es]), strong=np.array([e['strong'] for e in es]))
    pickle.dump(d, open(fn, 'wb')); return d


def wbce(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6); return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def folds(seed, k=5, rep=0):
    us = np.unique(seed); rng = np.random.default_rng(1000 + rep); perm = rng.permutation(us)
    f = {s: i % k for i, s in enumerate(perm)}; return np.array([f[s] for s in seed])


def oof(fit_predict, d, mask, k=5, reps=(0, 1, 2)):
    """Out-of-fold predictions on mask rows; fit_predict(tr_idx, te_idx, inner_va_idx) -> p for te_idx."""
    out = np.full((len(reps), len(d['y'])), np.nan)
    for ri, rep in enumerate(reps):
        fo = folds(d['seed'], k, rep)
        for f in range(k):
            te = mask & (fo == f); trall = mask & (fo != f)
            # inner validation for early stopping: one other fold
            iv = trall & (fo == (f + 1) % k); tr = trall & ~iv
            out[ri, te] = fit_predict(np.where(tr)[0], np.where(te)[0], np.where(iv)[0])
    return out


def score(P, d, mask):
    """per-game BCE + Brier skill on mask (all games), and on run-1 entries only; P: reps x N."""
    y, n = d['y'], d['n']; res = {}
    for name, m in (('all', mask), ('run1', mask & (d['src'] == 'run1'))):
        w = n[m]; pb = (y[m] * w).sum() / w.sum()
        bces = [float((wbce(p[m], y[m]) * w).sum() / w.sum()) for p in P]
        # Brier per game: E[(p-Y)^2] = (p-y)^2 + y(1-y) for an entry mean y over n games
        br = [float((((p[m] - y[m]) ** 2 + y[m] * (1 - y[m])) * w).sum() / w.sum()) for p in P]
        b0 = float(((((pb - y[m]) ** 2) + y[m] * (1 - y[m])) * w).sum() / w.sum())
        res[name] = dict(bce=float(np.mean(bces)), bce_sd=float(np.std(bces)), brier=float(np.mean(br)), r2=1 - float(np.mean(br)) / b0)
    return res


def per_seed_loss(P, d, mask):
    """mean over reps of per-entry summed BCE (games) -> for paired bootstrap."""
    L = np.mean([wbce(p, d['y']) * d['n'] for p in P], 0); return L


def paired(La, Lb, d, mask, nb=2000):
    s = d['seed'][mask]; diff = (La - Lb)[mask]; w = d['n'][mask]
    us, inv = np.unique(s, return_inverse=True); ds = np.bincount(inv, diff); ws = np.bincount(inv, w)
    rng = np.random.default_rng(7); bs = []
    for _ in range(nb):
        k = rng.integers(0, len(us), len(us)); bs.append(ds[k].sum() / ws[k].sum())
    return float(ds.sum() / ws.sum()), [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]
