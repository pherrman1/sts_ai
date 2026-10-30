"""heart1.pt encoder probe at the Act-4 entry (Philipp 14:26Z). Same CV as exp1-8.
usage: VA4_DATA=DIR exp9_heart1_probe.py heart1_embed.npz   (from heart1_embed.py on the PC)
Arms: LR on pooled embeddings alone (C grid), heart1 value output alone, ENS_rc design + embeddings (GBM, LR)."""
import sys, json, pickle, numpy as np, core, feats
from exp3lib import xg, lr
Z = np.load(sys.argv[1]); print(Z['identity'])
d = core.build(2); y, n, src = d['y'], d['n'], d['src']
assert (Z['i'] == np.arange(len(y))).all()
H = Z['pooled'].astype(np.float32); V = Z['value'].astype(np.float32)
recs = [e['entry']['record'] for e in core.entries(2)]
lce = core.logit(d['ce']); cp = core.logit((1 - d['ce'][:, 0]) * (1 - d['ce'][:, 1]))
X0 = np.hstack([d['X'], cp[:, None], lce, feats.eng(recs), np.c_[src == 'run1', d['strong'], np.zeros(len(y))].astype(np.float32),
                feats.relic_counters(recs), feats.card_state(recs)])
pool = (d['seed'] % 4) != 3; dc = pool & (src != 'extra')
srcf = np.c_[src == 'run1', d['strong']].astype(np.float32)
# decodability sanity: R2 of linear readout of HP fraction / deck size / gold from the embedding (dev pool, CV-free ridge)
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import cross_val_score, GroupKFold
for name, t in (('hp_frac', d['X'][:, -1]), ('deck_size', np.array([len(r['obs.deck.cards']) for r in recs], float)),
                ('gold', np.array([r['obs.fixed_observation'][2] for r in recs], float)), ('ctm_survival_logit', cp)):
    s = cross_val_score(RidgeCV(alphas=np.logspace(-2, 3, 12)), H[pool], t[pool], groups=d['seed'][pool], cv=GroupKFold(5), scoring='r2')
    print('decode', name, round(float(s.mean()), 3))
P8 = pickle.load(open(core.D + 'P_exp8.pkl', 'rb')); P = {}
arms = {f'LR_emb_C{C}': lr(np.hstack([H, srcf]), y, n, C) for C in (0.001, 0.01, 0.1)}
if not np.isnan(V).all(): arms['LR_value'] = lr(np.hstack([V, srcf]), y, n, 1e3)
arms['GBM_rc_emb'] = xg(np.hstack([X0, H]), y, n); arms['LR_rc_emb'] = lr(np.hstack([X0, H]), y, n, 0.003)
for k, fp in arms.items():
    P[k] = core.oof(fp, d, pool); print(k, json.dumps(core.score(P[k], d, dc)), flush=True)
P['ENS_rc_emb'] = (P['GBM_rc_emb'] + P['LR_rc_emb']) / 2; print('ENS_rc_emb', json.dumps(core.score(P['ENS_rc_emb'], d, dc)))
pickle.dump(P, open(core.D + 'P_exp9.pkl', 'wb'))
for k in P:
    print(k, '- ENS_rc', core.paired(core.per_seed_loss(P[k], d, dc), core.per_seed_loss(P8['ENS_rc'], d, dc), d, dc))
