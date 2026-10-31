"""Pilot gate (README "Analysis"): ENS_rc (exp8) vs ENS_rc + Act-4 entry perturbation rows, #915 CV, real dev rows.

usage: VA4_DATA=DIR gate.py OUT.json A4P_JSON...
DIR is the #915 data dir (design_2.pkl, P_exp8.pkl, ...). Perturbation rows (children 1-15) enter only the training
part of an outer fold whose test fold and inner early-stopping fold both exclude their seed.
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'value_a4_improve_20261030', 'tools'))
import core, feats  # noqa: E402
from exp3lib import xg, lr  # noqa: E402

out_path, paths = sys.argv[1], sys.argv[2:]
d = core.build(2); es = core.entries(2); recs = [e['entry']['record'] for e in es]
pos = {e['seed']: (e['entry']['act'], e['entry']['floor']) for e in es if e['src'] == 'run1'}  # entry act/floor per seed
N = len(d['y'])

# perturbation rows
prs, py, pseed, pop = [], [], [], []
for p in paths:
    r = json.load(open(p))
    for c in r['children']:
        if c['child'] == 0:
            continue
        prs.append(c['entryRecord']); py.append(float(c['heartKilled'])); pseed.append(r['seed']); pop.append(c['op'])
M = len(prs); pseed = np.array(pseed); py = np.array(py)
model = core.F.load_trees(os.path.join(core.REPO, 'models/candidates/ctm_act4_survival_trees.txt'))
Xp, _ = core.R.design([dict(entry=dict(record=r, act=pos[s][0], floor=pos[s][1]), ctm=[]) for r, s in zip(prs, pseed)], model)
cep = np.array([[core.F.tree_pred(model, core.ctm_entry_feats(r, 0)), core.F.tree_pred(model, core.ctm_entry_feats(r, 1))]
                for r in prs])


def design(X, ce, R, run1, strong, pert):
    lce = core.logit(ce); cp = core.logit((1 - ce[:, 0]) * (1 - ce[:, 1]))
    X0 = np.hstack([X, cp[:, None], lce, feats.eng(R), np.c_[run1, strong, pert].astype(np.float32)])
    return np.hstack([X0, feats.relic_counters(R), feats.card_state(R)])


XA = design(d['X'], d['ce'], recs, d['src'] == 'run1', d['strong'], np.zeros(N))
XP = design(Xp, cep, prs, np.zeros(M), np.ones(M), np.ones(M))
XB = np.vstack([XA, XP]); yB = np.r_[d['y'], py]; nB = np.r_[d['n'], np.ones(M)]
pool = (d['seed'] % 4) != 3; dc = pool & (d['src'] != 'extra')
assert set(pseed) <= set(d['seed'][dc]), 'perturbation seeds must be dev seeds with a real entry'


def oof_aug(fp, k=5, reps=(0, 1, 2)):
    """core.oof on the real pool rows; perturbation rows join tr only (never te or iv)."""
    out = np.full((len(reps), N), np.nan)
    for ri, rep in enumerate(reps):
        fo = core.folds(d['seed'], k, rep); sf = dict(zip(d['seed'], fo)); pf = np.array([sf[s] for s in pseed])
        for f in range(k):
            te = pool & (fo == f); trall = pool & (fo != f)
            iv = trall & (fo == (f + 1) % k); tr = trall & ~iv
            ptr = N + np.where((pf != f) & (pf != (f + 1) % k))[0]
            out[ri, te] = fp(np.r_[np.where(tr)[0], ptr], np.where(te)[0], np.where(iv)[0])
    return out


if os.environ.get('GATE_CHECK'):  # wrapper with no perturbation rows must reproduce exp8 (GBM, rep 0)
    pseed_saved = pseed; pseed = pseed[:0]
    g = oof_aug(xg(XA, d['y'], d['n']), reps=(0,)); pseed = pseed_saved
    P8 = __import__('pickle').load(open(core.D + 'P_exp8.pkl', 'rb'))
    print('max |wrapper - exp8| GBM rep0:', float(np.nanmax(np.abs(g[0] - P8['GBM_rc'][0])))); sys.exit(0)
P8 = __import__('pickle').load(open(core.D + 'P_exp8.pkl', 'rb'))
PA = P8['ENS_rc']
PB = (oof_aug(xg(XB, yB, nB)) + oof_aug(lr(XB, yB, nB, 0.003))) / 2
LA, LB = core.per_seed_loss(PA, d, dc), core.per_seed_loss(PB, d, dc)
diff, ci = core.paired(LB, LA, d, dc)
pil = dc & np.isin(d['seed'], pseed); rest = dc & ~np.isin(d['seed'], pseed)
res = dict(n_pert_rows=M, n_units=len(paths), pert_kill_rate=float(py.mean()),
           A=core.score(PA, d, dc), B=core.score(PB, d, dc),
           gate=dict(diff=diff, ci=ci, verdict='PASS' if ci[1] < 0 else 'NOT_SHOWN'),
           pilot_seeds=core.paired(LB, LA, d, pil), other_seeds=core.paired(LB, LA, d, rest))
print(json.dumps(res, indent=1))
json.dump(res, open(out_path, 'w'), indent=1)
