import pickle, numpy as np, core, feats
from multiprocessing import Pool
F = core.F; s0 = core.s0
model = F.load_trees(core.REPO + '/models/candidates/ctm_act4_survival_trees.txt')
def rows(g):
    out = []; seen = set(); f0 = g['states'][0]['floor']
    for s in g['states']:
        if s['floor'] == f0 or s['floor'] in seen: continue
        seen.add(s['floor']); out.append(s)
    return [(g['seed'], g['heartKilled'], g['campaign'], s) for s in out]
def feat(t):
    seed, k, camp, s = t; rec = s['record']
    x = np.zeros(s0.N_FEAT + 1, np.float32); c, v = s0.features(s); x[c] = v; fo = rec['obs.fixed_observation']; x[-1] = fo[0] / max(fo[1], 1)
    ce = [F.tree_pred(model, core.ctm_entry_feats(rec, 0)), F.tree_pred(model, core.ctm_entry_feats(rec, 1))]
    return x, ce, seed, float(k), s['floor'] - 0
if __name__ == '__main__':
    G = pickle.load(open(core.D + 'states_a4.pkl', 'rb'))
    T = [t for g in G for t in rows(g)]
    print(len(G), len(T))
    with Pool(4) as p: R = p.map(feat, T, chunksize=64)
    X = np.array([r[0] for r in R]); ce = np.array([r[1] for r in R]); seed = np.array([r[2] for r in R]); y = np.array([r[3] for r in R])
    E = feats.eng([t[3]['record'] for t in T])
    gid = np.array([hash((t[0], t[2], id(g))) for g in G for t in rows(g)])
    pickle.dump(dict(X=X, ce=ce, seed=seed, y=y, E=E, camp=np.array([t[2] for t in T])), open(core.D + 'aug.pkl', 'wb'))
