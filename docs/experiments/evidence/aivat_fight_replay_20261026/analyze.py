# Offline AIVAT-style control-variate estimate on paired A/B corpora.
# V(post-fight state) = P(Heart kill) GBM; E(pre) = E[V(post) | pre-fight state, encounter] GBM.
# Both are cross-fitted by DATASET (trained only on the other campaigns' seeds).
import json, sys, collections, numpy as np, xgboost as xgb
DS = {'676': ('h676.jsonl', ('A', 'C')), '661': ('h661.jsonl', ('A', 'M', 'S', 'MS')), '683': ('h683.jsonl', ('OFF', 'MAP', 'D'))}
runs = {k: [json.loads(l) for l in open(v[0])] for k, v in DS.items()}
cc = collections.Counter(); rc = collections.Counter()
for rs in runs.values():
    for r in rs:
        for f in r['fights']:
            cc.update(x // 2 for x in f['post']['deck']); rc.update(f['post']['rel'])
CARDS = [c for c, _ in cc.most_common(150)]; RELS = [c for c, _ in rc.most_common(120)]
ci = {c: i for i, c in enumerate(CARDS)}; ri = {c: i for i, c in enumerate(RELS)}
NB = 12 + len(CARDS) + len(RELS)
def feat(s):
    v = np.zeros(NB, np.float32)
    v[:12] = [s['act'], s['floor'], s['hp'], s['mhp'], s['hp'] / max(1, s['mhp']), s['gold'], s['pc'], len(s['pot']),
              len(s['deck']), sum(x & 1 for x in s['deck']), s['ctc'][0], s['ctc'][2]]
    for x in s['deck']:
        j = ci.get(x // 2)
        if j is not None: v[12 + j] += 1
    for x in s['rel']:
        j = ri.get(x)
        if j is not None: v[12 + len(CARDS) + j] = 1
    return v
RC = {'NORMAL': 0, 'ELITE': 1, 'BOSS': 2, 'OTHER': 3}
def is_heart(f): return f['pre']['act'] == 4 and f['rc'] == 'BOSS'
def rows(rs):
    Xp, Xq, yv, ids = [], [], [], []
    for ri_, r in enumerate(rs):
        for k, f in enumerate(r['fights']):
            Xq.append(np.concatenate([feat(f['pre']), [f['enc'], RC[f['rc']]]]))
            Xp.append(feat(f['post'])); yv.append(r['y']); ids.append((ri_, k))
    return np.array(Xp), np.array(Xq), np.array(yv), ids
P = dict(n_estimators=400, max_depth=5, learning_rate=0.05, subsample=0.8, colsample_bytree=0.5, n_jobs=4)
R = {}
for key in DS:
    train = [r for k, rs in runs.items() if k != key for r in rs]
    Xp, Xq, y, ids = rows(train)
    alive = np.array([train[i]['fights'][k]['out'] == 1 and not is_heart(train[i]['fights'][k]) for i, k in ids])
    vm = xgb.XGBClassifier(objective='binary:logistic', **P).fit(Xp[alive], y[alive])
    # out-of-fold V labels for the E model (by seed), so E learns held-out-quality V
    fold = np.array([train[i]['seed'] % 4 for i, k in ids]); vpost = np.zeros(len(y))
    for q in range(4):
        tr = alive & (fold != q)
        mq = xgb.XGBClassifier(objective='binary:logistic', **P).fit(Xp[tr], y[tr])
        vpost[fold == q] = mq.predict_proba(Xp[fold == q])[:, 1]
    vpost[~alive] = 0.0
    hrt = np.array([is_heart(train[i]['fights'][k]) for i, k in ids])
    vpost[hrt] = y[hrt]  # Heart post value is the outcome itself
    em = xgb.XGBRegressor(objective='reg:logistic', **P).fit(Xq, vpost)
    # score the held-out campaign
    Xp, Xq, y, ids = rows(runs[key])
    rs = runs[key]
    alive = np.array([rs[i]['fights'][k]['out'] == 1 for i, k in ids])
    hrt = np.array([is_heart(rs[i]['fights'][k]) for i, k in ids])
    vp = np.where(alive, vm.predict_proba(Xp)[:, 1], 0.0); vp[hrt] = y[hrt]
    e = em.predict(Xq)
    for (i, k), a, b in zip(ids, vp, e):
        rs[i]['fights'][k]['V'] = float(a); rs[i]['fights'][k]['E'] = float(b)
    R[key] = rs
    print(key, 'V/E fitted', file=sys.stderr)
json.dump({k: [dict(arm=r['arm'], seed=r['seed'], y=r['y'],
                    f=[(f['pre']['act'], f['rc'], f['out'], f['pre']['hp'], f['V'], f['E']) for f in r['fights']],
                    dec=r['dec']) for r in rs] for k, rs in R.items()}, open('scored.json', 'w'))
