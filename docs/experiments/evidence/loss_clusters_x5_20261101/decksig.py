"""Deck/relic signature inside each big death cluster. usage: decksig.py WORKDIR [MIN_SHARE]
For every stage that kills >= MIN_SHARE (default 2%) of primary runs: all entries to that fight, death ~ features.
Models (seed-grouped 5-fold CV log loss, games of the same seed share a fold):
  R  resources: entry HP, HP fraction, max HP, potions, potion slots, gold
  RD resources + deck/relic (card counts by id with upgrades, deck size, upgrades, curses, relic one-hots)
  GBM on RD (HistGradientBoosting) for interactions.
Reports the CV gain of deck over resources and, for RD's L2 logistic, the cards/relics most tied to death.
Deck risk quartiles: deaths by quartile of the out-of-fold deck-only part of the RD score."""
import sys, collections
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupKFold
from sklearn.metrics import log_loss
from sklearn.preprocessing import StandardScaler
from common import *
W = sys.argv[1]; MIN = float(sys.argv[2]) if len(sys.argv) > 2 else 0.02
G, _ = primary(load(W)); N = len(G)
CURSES = {k for k, v in CARD.items() if CTYPE and k < len(CTYPE) and CTYPE[k] == 'CURSE'}
ent = collections.defaultdict(list)
for g in G:
    for f in g['fights']:
        ent[stage(f)].append((g, f))
dead = lambda f: f['res'] == 2 or f['post'] <= 0
for s in sorted(ent, key=lambda s: -sum(dead(f) for _, f in ent[s])):
    rows = ent[s]; d = sum(dead(f) for _, f in rows)
    if d / N < MIN: continue
    cc = collections.Counter(); rc = collections.Counter()
    for _, f in rows:
        cc.update({c for c, _ in f['deck']}); rc.update(set(f['relics']))
    cards = [c for c, n in cc.items() if n >= 0.03 * len(rows)]; rels = [r for r, n in rc.items() if n >= 0.03 * len(rows)]
    ci = {c: i for i, c in enumerate(cards)}; ri = {r: i for i, r in enumerate(rels)}
    Xr, Xd, y, grp = [], [], [], []
    for g, f in rows:
        Xr.append([f['hp'], f['hp'] / f['maxhp'], f['maxhp'], len(f['pots']), f['cap'], f['gold'] or 0])
        v = np.zeros(len(cards) * 2 + len(rels) + 3)
        for c, u in f['deck']:
            if c in ci: v[2 * ci[c] + (1 if u else 0)] += 1
        for r in f['relics']:
            if r in ri: v[2 * len(cards) + ri[r]] = 1
        v[-3] = len(f['deck']); v[-2] = sum(u for _, u in f['deck']); v[-1] = sum(c in CURSES for c, _ in f['deck'])
        Xd.append(v); y.append(dead(f)); grp.append(g['seed'])
    Xr = np.array(Xr, float); Xd = np.array(Xd, float); y = np.array(y, int); grp = np.array(grp)
    Xrd = np.hstack([Xr, Xd])
    def cv(make, X):
        pr = np.zeros(len(y))
        for tr, te in GroupKFold(5).split(X, y, grp):
            m = make(); m.fit(X[tr], y[tr]); pr[te] = m.predict_proba(X[te])[:, 1]
        return pr
    lr = lambda: __import__('sklearn.pipeline', fromlist=['make_pipeline']).make_pipeline(StandardScaler(), LogisticRegression(C=0.05, max_iter=2000))
    pR = cv(lr, Xr)
    pRD = np.zeros(len(y)); zd = np.zeros(len(y))   # out-of-fold RD prediction and deck-only score
    for tr, te in GroupKFold(5).split(Xrd, y, grp):
        mm = lr(); mm.fit(Xrd[tr], y[tr]); pRD[te] = mm.predict_proba(Xrd[te])[:, 1]
        zd[te] = mm[0].transform(Xrd[te])[:, 6:] @ mm[-1].coef_[0][6:]
    pG = cv(lambda: HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0), Xrd)
    base = log_loss(y, np.full(len(y), y.mean()))
    # paired bootstrap over seeds of the RD-vs-R log-loss gain
    ll = lambda p: -(y * np.log(np.clip(p, 1e-6, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-6, 1)))
    gain = ll(pR) - ll(pRD); gainG = ll(pR) - ll(pG)
    us = np.unique(grp); idx = {u: np.where(grp == u)[0] for u in us}; rng = np.random.default_rng(1)
    def bci(v):
        b = []
        for _ in range(1000):
            pick = rng.choice(us, len(us)); ii = np.concatenate([idx[u] for u in pick]); b.append(v[ii].mean())
        return np.percentile(b, [2.5, 97.5])
    print(f'\n== {s}: entries {len(rows)}, deaths {d} ({d/N*100:.2f}% of runs, {y.mean()*100:.1f}% per fight)')
    print(f'   CV log loss: base {base:.4f}  R {ll(pR).mean():.4f}  RD {ll(pRD).mean():.4f}  GBM {ll(pG).mean():.4f}')
    print(f'   deck gain RD-R {gain.mean():+.4f} CI {bci(gain).round(4)};  GBM-R {gainG.mean():+.4f} CI {bci(gainG).round(4)}')
    m = lr(); m.fit(Xrd, y); coef = m[-1].coef_[0]
    names = ['hp', 'hpfrac', 'maxhp', 'potions', 'slots', 'gold'] + [f'{CARD.get(c,c)}{"+" if k else ""}' for c in cards for k in (0, 1)] + [f'R:{RELIC.get(r,r)}' for r in rels] + ['decksize', 'upgrades', 'curses']
    o = np.argsort(coef)
    print('   protective:', ', '.join(f'{names[i]} {coef[i]:+.2f}' for i in o[:8]))
    print('   risky:     ', ', '.join(f'{names[i]} {coef[i]:+.2f}' for i in o[::-1][:8]))
    # deck-only score quartiles
    q = np.quantile(zd, [.25, .5, .75]); qq = np.searchsorted(q, zd)
    print('   deaths by out-of-fold deck-risk quartile (per-fight rate, share of runs):', '; '.join(
        f'Q{k+1} {y[qq==k].mean()*100:.1f}% / {y[qq==k].sum()/N*100:.2f}%' for k in range(4)))
    # HP band x deck half
    hb = np.array([hpband(f) for _, f in rows]); hi = zd > np.median(zd)
    print('   per-fight death, HP band x deck risk (low/high):', '; '.join(
        f'{b} {y[(hb==b)&~hi].mean()*100:.0f}/{y[(hb==b)&hi].mean()*100:.0f}%' for b in ('<50%', '50-80%', '>=80%')))
