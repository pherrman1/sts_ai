import pickle, glob, zlib, numpy as np, json
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, log_loss
G = {}
for f in sorted(glob.glob('p683_*.pkl')):
    for (s, a), v in pickle.load(open(f, 'rb')).items(): G[('683', s, a)] = v
for f in sorted(glob.glob('p676_*.pkl')):
    for (s, a), v in pickle.load(open(f, 'rb')).items(): G[('676', s, a)] = v
G = {k: v for k, v in G.items() if v}
print('games', len(G))
lg = lambda p: np.log(np.clip(p, 1e-6, 1-1e-6) / (1 - np.clip(p, 1e-6, 1-1e-6)))
rng = np.random.default_rng(1)

def entry(v, act):
    fs = [f for f in v['fights'] if f['act'] == act]
    return fs[0] if fs else None

def cv(X, y, groups, k=5):
    p = np.zeros(len(y)); fold = np.array([zlib.crc32(g.encode()) % k for g in groups])
    for i in range(k):
        m = LogisticRegression(C=1e3, max_iter=2000).fit(X[fold != i], y[fold != i]); p[fold == i] = m.predict_proba(X[fold == i])[:, 1]
    return p

def compare(name, rows, y, groups, sets):
    out = {'n': len(y), 'rate': float(y.mean())}
    P = {}
    for sn, cols in sets.items():
        X = np.column_stack([rows[c] for c in cols]); X = (X - X.mean(0)) / (X.std(0) + 1e-9)
        P[sn] = cv(X, y, groups)
        out[sn] = {'auc': round(roc_auc_score(y, P[sn]), 4), 'logloss': round(log_loss(y, P[sn]), 4)}
    # bootstrap by seed group: delta auc / logloss of last set vs first
    keys = list(sets); b0, b1 = keys[0], keys[-1]
    ug = np.array(sorted(set(groups))); gi = {g: np.where(groups == g)[0] for g in ug}
    da, dl = [], []
    for _ in range(1000):
        idx = np.concatenate([gi[g] for g in rng.choice(ug, len(ug))])
        if 0 < y[idx].sum() < len(idx):
            da.append(roc_auc_score(y[idx], P[b1][idx]) - roc_auc_score(y[idx], P[b0][idx]))
            dl.append(log_loss(y[idx], P[b1][idx]) - log_loss(y[idx], P[b0][idx]))
    out[f'd_auc_{b1}-{b0}'] = [round(float(np.mean(da)), 4)] + [round(float(x), 4) for x in np.percentile(da, [2.5, 97.5])]
    out[f'd_ll_{b1}-{b0}'] = [round(float(np.mean(dl)), 4)] + [round(float(x), 4) for x in np.percentile(dl, [2.5, 97.5])]
    print(name, json.dumps(out)); return out

R = {}
# T1 sanity: Heart rows, model's own prediction
hr = [(v['kill'], f) for k, v in G.items() for f in v['fights'] if f['enc'] == 57]
y = np.array([1 - (f['outcome'] == 2) for _, f in hr])
print('T1 heart rows', len(hr), 'win', y.mean(), 'AUC model', roc_auc_score(y, [f['rA'] for _, f in hr]),
      'AUC curHp', roc_auc_score(y, [f['curHp'] for _, f in hr]), 'AUC rF', roc_auc_score(y, [f['rF'] for _, f in hr]))

for act in (2, 3, 4):
    keys = [k for k, v in G.items() if entry(v, act)]
    E = [entry(G[k], act) for k in keys]
    rows = {'hp': np.array([e['curHp'] for e in E], float), 'maxhp': np.array([e['maxHp'] for e in E], float),
            'deck': np.array([e['deck'] for e in E], float), 'upg': np.array([e['upg'] for e in E], float),
            'floor': np.array([e['floor'] for e in E], float), 'gold': np.array([e['gold'] for e in E], float),
            'rF': lg(np.array([e['rF'] for e in E])), 'rA': lg(np.array([e['rA'] for e in E]))}
    y = np.array([G[k]['kill'] for k in keys]); groups = np.array([k[0] + k[1] for k in keys])
    R[f'act{act}_entry_kill'] = compare(f'act{act} entry -> kill', rows, y, groups, {
        'hp': ['hp', 'maxhp'], 'hp_deck': ['hp', 'maxhp', 'deck', 'upg', 'floor', 'gold'], 'rF': ['rF'],
        'hp_deck_rF': ['hp', 'maxhp', 'deck', 'upg', 'floor', 'gold', 'rF']})
    R[f'act{act}_entry_kill_hp_vs_rF'] = compare(f'act{act} entry hp vs hp+rF', rows, y, groups, {
        'hp': ['hp', 'maxhp'], 'hp_rF': ['hp', 'maxhp', 'rF']})
    if act < 4:  # Heart conversion given arrival, predicted from act-k entry
        m = np.array([G[k]['finalAct'] >= 4 for k in keys])
        sub = {c: v[m] for c, v in rows.items()}
        R[f'act{act}_entry_convert'] = compare(f'act{act} entry -> kill | act4', sub, y[m], groups[m], {
            'hp_deck': ['hp', 'maxhp', 'deck', 'upg', 'floor', 'gold'], 'hp_deck_rF': ['hp', 'maxhp', 'deck', 'upg', 'floor', 'gold', 'rF']})
        R[f'act{act}_entry_reach4'] = compare(f'act{act} entry -> reach act4', rows, m.astype(int), groups, {
            'hp_deck': ['hp', 'maxhp', 'deck', 'upg', 'floor', 'gold'], 'hp_deck_rF': ['hp', 'maxhp', 'deck', 'upg', 'floor', 'gold', 'rF']})

# T4 mechanism: MAP vs OFF readiness at Act-4 entry
for x, yy in (('MAP', 'OFF'), ('D', 'OFF'), ('C', 'A')):
    src = '676' if x == 'C' else '683'
    seeds = sorted({k[1] for k in G if k[0] == src})
    both = [s for s in seeds if (src, s, x) in G and (src, s, yy) in G and entry(G[(src, s, x)], 4) and entry(G[(src, s, yy)], 4)]
    d = [lg(entry(G[(src, s, x)], 4)['rF']) - lg(entry(G[(src, s, yy)], 4)['rF']) for s in both]
    dh = [entry(G[(src, s, x)], 4)['curHp'] - entry(G[(src, s, yy)], 4)['curHp'] for s in both]
    diff = [s for s in both if entry(G[(src, s, x)], 4)['rF'] != entry(G[(src, s, yy)], 4)['rF']]
    bs = [np.mean(rng.choice(d, len(d))) for _ in range(2000)]
    only = {a: [lg(entry(G[(src, s, a)], 4)['rF']) for s in seeds if (src, s, a) in G and entry(G[(src, s, a)], 4) and not ((src, s, b) in G and entry(G[(src, s, b)], 4))] for a, b in ((x, yy), (yy, x))}
    print(f'T4 {x}-{yy}: shared arrivals {len(both)} (deck/state differs {len(diff)}), mean dlogit rF {np.mean(d):.3f} CI {np.percentile(bs,[2.5,97.5]).round(3)}, dHP {np.mean(dh):.2f};',
          f'only-{x} n={len(only[x])} mean logit rF {np.mean(only[x]):.3f}; only-{yy} n={len(only[yy])} {np.mean(only[yy]):.3f}; shared {x} {np.mean([lg(entry(G[(src,s,x)],4)["rF"]) for s in both]):.3f}')
json.dump(R, open('stage0.json', 'w'), indent=1)
