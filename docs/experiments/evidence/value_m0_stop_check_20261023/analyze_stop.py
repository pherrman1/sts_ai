"""Learned OOC stop on M0's Q scale: python3 -I analyze_stop.py OUT_DIR TREES.txt [OUT.json]

OUT_DIR holds A/ and M/ from run.sh (profiled games, every searched root at 4096 simulations). Rows are the root
checkpoints 128..2048 of tools/ooc_learned_stop.py (same loader, features and label: is the checkpoint's visit
leader the full search's choice). Each arm is scored with the deployed CompactTreeNet (TREES.txt):
  model  mean predicted P(same) against the observed rate, overall, at p >= TAU, and by act
  rule   the deployed fast-root rule (cap 1024): stop at the first checkpoint in 128/256/512 with p >= TAU and play
         its visit leader, else play the leader at 1024 (a root that ended below 1024 keeps its final pick). Shares
         of roots stopped, mean simulations, and agreement with the 1024-simulation leader and with the full search.
The stop was trained on X2-B-scale roots (§565); the A arm is today's stack on that scale, M the same with M0.
Intervals: 95% bootstrap over seeds (2,000 resamples, RNG 20261023)."""
import collections
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'tools'))
import ooc_learned_stop as ols  # noqa: E402  (loader, features and label of the stop's training data)

TAU = 0.99
FAST_CPS = (128, 256, 512)
CAP = 1024


def load_trees(path):
    lines = Path(path).read_text().split('\n')
    k = 0

    def nxt():
        nonlocal k
        k += 1
        return lines[k - 1].split()
    nfeat = int(nxt()[1])
    feats = [nxt()[1] for _ in range(nfeat)]
    assert nxt() == ['logistic', '1']
    base = float(nxt()[1])
    ntrees = int(nxt()[1])
    trees = []
    for _ in range(ntrees):
        tag, _, size = nxt()
        assert tag == 'tree'
        nodes = []
        for _ in range(int(size)):
            p = nxt()
            nodes.append((int(p[1]), np.float32(p[2]), int(p[3]), int(p[4])) if p[0] == 'S' else (-1, float(p[1]), 0, 0))
        trees.append(nodes)
    idx = [ols.NAMES.index(f) for f in feats]
    return idx, math.log(base / (1 - base)), trees


def predict(model, raw):
    idx, margin, trees = model
    x = np.asarray(raw, dtype=np.float32)
    m = margin
    for nodes in trees:
        i = 0
        while nodes[i][0] >= 0:
            f, thr, yes, no = nodes[i]
            i = yes if x[idx[f]] < thr else no
        m += nodes[i][1]
    return 1.0 / (1.0 + math.exp(-m))


def leader_at(r, c):
    cp = next((cp for cp in r['checkpoints'] if cp['simulations'] == c), None)
    return ols.leader(cp['actions'])['id'] if cp else None


def arm_stats(roots, model):
    rows, per_root = [], []
    for r in roots:
        p_at = {}
        for cp in r['checkpoints']:
            c = cp['simulations']
            if c in ols.CPS and c < r['completed_simulations']:
                p = predict(model, ols.features(r, cp))
                same = int(ols.leader(cp['actions'])['id'] == ols.final(r))
                rows.append((r['seed'], r['act'], c, p, same))
                p_at[c] = p
        full = ols.final(r)
        at_cap = leader_at(r, CAP) if r['completed_simulations'] > CAP else full
        stop = next((c for c in FAST_CPS if c in p_at and p_at[c] >= TAU), None)
        pick = leader_at(r, stop) if stop else at_cap
        sims = stop or min(CAP, r['completed_simulations'])
        per_root.append((r['seed'], r['act'], stop, sims, int(pick == at_cap), int(pick == full), int(at_cap == full)))
    return rows, per_root


def boot(seeds, fn, n=2000):
    rng = np.random.default_rng(20261023)
    u = sorted(set(seeds))
    vals = []
    for _ in range(n):
        s = collections.Counter(rng.choice(u, len(u)))
        v = fn(s)
        if v is not None:
            vals.append(v)
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def weighted_mean(items, s, key, val):
    num = den = 0.0
    for it in items:
        w = s.get(key(it), 0)
        num += w * val(it); den += w
    return num / den if den else None


def summarize(roots, model):
    rows, per_root = arm_stats(roots, model)
    seeds = [r[0] for r in per_root]
    hi = [x for x in rows if x[3] >= TAU]
    stopped = [x for x in per_root if x[2]]
    out = {
        'seeds': len(set(seeds)), 'roots': len(per_root), 'rows': len(rows),
        'model': {
            'meanP': float(np.mean([x[3] for x in rows])), 'sameRate': float(np.mean([x[4] for x in rows])),
            'rowsPAtLeastTau': len(hi), 'meanPAtLeastTau': float(np.mean([x[3] for x in hi])) if hi else None,
            'precisionAtLeastTau': float(np.mean([x[4] for x in hi])) if hi else None,
            'precisionAtLeastTauCI': boot([x[0] for x in hi], lambda s: weighted_mean(hi, s, lambda x: x[0], lambda x: x[4])) if hi else None,
            'byAct': {}},
        'rule': {
            'stoppedShare': len(stopped) / len(per_root),
            'stoppedShareCI': boot(seeds, lambda s: weighted_mean(per_root, s, lambda x: x[0], lambda x: float(bool(x[2])))),
            'stopAt': dict(collections.Counter(str(x[2]) for x in stopped)),
            'meanSims': float(np.mean([x[3] for x in per_root])),
            'agreeWith1024': float(np.mean([x[4] for x in per_root])),
            'agreeWith1024CI': boot(seeds, lambda s: weighted_mean(per_root, s, lambda x: x[0], lambda x: x[4])),
            'stoppedAgreeWith1024': float(np.mean([x[4] for x in stopped])) if stopped else None,
            'stoppedDisagree1024': int(sum(1 - x[4] for x in stopped)),
            'agreeWithFull': float(np.mean([x[5] for x in per_root])),
            'cap1024AgreeWithFull': float(np.mean([x[6] for x in per_root])),
            'byAct': {}}}
    for act in sorted({x[1] for x in per_root}):
        ra = [x for x in rows if x[1] == act]
        ha = [x for x in ra if x[3] >= TAU]
        pa = [x for x in per_root if x[1] == act]
        sa = [x for x in pa if x[2]]
        out['model']['byAct'][str(act)] = {'rows': len(ra), 'meanP': float(np.mean([x[3] for x in ra])),
                                           'sameRate': float(np.mean([x[4] for x in ra])), 'rowsPAtLeastTau': len(ha),
                                           'precisionAtLeastTau': float(np.mean([x[4] for x in ha])) if ha else None}
        out['rule']['byAct'][str(act)] = {'roots': len(pa), 'stoppedShare': len(sa) / len(pa),
                                          'meanSims': float(np.mean([x[3] for x in pa])),
                                          'stoppedAgreeWith1024': float(np.mean([x[4] for x in sa])) if sa else None}
    return out


def main():
    out_dir, trees = Path(sys.argv[1]), sys.argv[2]
    model = load_trees(trees)
    res = {'tau': TAU, 'trees': trees, 'arms': {}}
    for arm in ('A', 'M'):
        roots, digest = ols.load_roots([str(out_dir / arm)])
        res['arms'][arm] = {'data_sha256': digest, **summarize(roots, model)}
    text = json.dumps(res, indent=1)
    if len(sys.argv) > 3:
        Path(sys.argv[3]).write_text(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
