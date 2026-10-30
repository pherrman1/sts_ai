"""Drop-in V_A4 (P(Heart kill) at the Act-4 entry) on the public state record only.
    import va4_model; m = va4_model.load(); p = m.predict([state, ...])
state = a heart1-public-record-v2 state row: {'act': 4, 'floor': .., 'record': {...}} (the Act-4 entry, as in extract_a4.py).
Model = mean of an XGBoost GBM and an L2 logistic regression (fit_va4.py) on: the s0 public-record features + HP fraction,
the Act-4 CTM (ctm_act4_survival_trees) evaluated on the ENTRY record (S&S and Heart death logits + survival product),
deck aggregates, relic counters and card state (feats.py). No post-entry information (no CTM S&S row)."""
import os, json, numpy as np
import core, feats
HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(HERE, '..', 'model')
_CTM = None


def ctm():
    global _CTM
    if _CTM is None: _CTM = core.F.load_trees(os.path.join(core.REPO, 'models/candidates/ctm_act4_survival_trees.txt'))
    return _CTM


def design(states, run1=1.0, strong=1.0):
    """Feature matrix. run1/strong: source indicators used in training; deploy at today's default = (1, 1)."""
    s0 = core.s0; m = ctm(); N = len(states)
    X = np.zeros((N, s0.N_FEAT + 1), np.float32); ce = np.zeros((N, 2))
    for i, s in enumerate(states):
        rec = s['record']; c, v = s0.features(s); X[i, c] = v
        fo = rec['obs.fixed_observation']; X[i, -1] = fo[0] / max(fo[1], 1)
        ce[i] = core.F.tree_pred(m, core.ctm_entry_feats(rec, 0)), core.F.tree_pred(m, core.ctm_entry_feats(rec, 1))
    recs = [s['record'] for s in states]
    return assemble(X, ce, recs, np.full(N, run1), np.full(N, strong))


def assemble(X, ce, recs, run1, strong):
    """exp8 design: exp6 ENS_all columns + relic-counter one-hots + Ritual Dagger / Searing Blow state."""
    lce = core.logit(ce); cp = core.logit((1 - ce[:, 0]) * (1 - ce[:, 1]))
    return np.hstack([X, cp[:, None], lce, feats.eng(recs), np.c_[run1, strong, np.zeros(len(X))].astype(np.float32),
                      feats.relic_counters(recs), feats.card_state(recs)])


class VA4:
    def __init__(self, d=MODEL_DIR):
        import xgboost as xgb
        self.gbm = xgb.Booster(); self.gbm.load_model(os.path.join(d, 'va4_gbm.ubj'))
        j = json.load(open(os.path.join(d, 'va4_lr.json')))
        self.mu, self.sd, self.w, self.b = (np.array(j[k]) for k in ('mean', 'scale', 'coef', 'intercept'))

    def predict_matrix(self, Z):
        import xgboost as xgb
        pg = self.gbm.predict(xgb.DMatrix(Z))
        pl = 1 / (1 + np.exp(-(((Z - self.mu) / self.sd) @ self.w + self.b)))
        return (pg + pl) / 2

    def predict(self, states, **kw):
        return self.predict_matrix(design(states, **kw))


def load(d=MODEL_DIR): return VA4(d)
