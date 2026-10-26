"""AIVAT-style paired A/B estimate with replayed fights as the luck baseline (2026-10-26).

For every run and every replayed fight k, the fight's luck is V(actual post) - mean_r V(replay post r), where the
replays (`one_combat fightreplay`, replicates >= 1) are fresh independent draws of the same fight under the same
combat policy. Its expectation is exactly zero, so

    Y_hat = Y - beta * sum_k [V(actual post_k) - mean_r V(replay post_{k,r})]

is unbiased for the kill rate for ANY fixed V and beta. beta = m / (m + 1) (m replicates) is the variance-optimal
coefficient when V is the true value. V(post) is 0 after a death and the fight outcome after the Heart; other
post-fight states are scored by a frozen value model (`train`), which must not be fit on the evaluated campaign.

  train  OUT_PREFIX UNIT.tar ...               fit V = P(Heart kill | post-fight state) (xgboost) on other campaigns
  estimate MODEL_PREFIX REPLAYS.jsonl UNITS.tar ... --pair B,A [--rooms BOSS,ELITE] [--act4]
"""
import argparse
import gzip
import hashlib
import json
import os
import sys
import tarfile

import numpy as np

HEART = 57  # MonsterEncounter::THE_HEART


def runs_from_units(paths):
    """{(arm, seed): (y, [post states of real fights])} from heartoutcomegen unit tars."""
    runs = {}
    for p in paths:
        with tarfile.open(p) as tf:
            members = {os.path.basename(m.name): m for m in tf.getmembers() if m.isfile()}
            for name, m in members.items():
                if not name.endswith('.ctm.jsonl.gz'):
                    continue
                tag = name[:-len('.ctm.jsonl.gz')]
                arm, seed = tag.rsplit('-', 1)
                traj = gzip.decompress(tf.extractfile(members[tag + '.jsonl.gz']).read()).splitlines()
                out = json.loads(traj[-1])
                if out.get('type') != 'outcome' or not out.get('integrityPassed'):
                    raise SystemExit(f'{p}:{tag}: no integrity-passed outcome row')
                fights = [json.loads(l) for l in gzip.decompress(tf.extractfile(m).read()).splitlines() if l]
                runs[(arm, int(seed))] = (int(out['heartKilled']), fights)
    return runs


class Features:
    def __init__(self, cards, relics):
        self.cards, self.relics = list(cards), list(relics)
        self.ci = {c: i for i, c in enumerate(self.cards)}
        self.ri = {r: i for i, r in enumerate(self.relics)}
        self.n = 12 + len(self.cards) + len(self.relics)

    def __call__(self, s, act, floor):
        v = np.zeros(self.n, np.float32)
        deck = s['deck']
        pots = [p for p in s.get('potions', []) if p != 1]
        v[:12] = [act, floor, s['curHp'], s['maxHp'], s['curHp'] / max(1, s['maxHp']), s.get('gold', 0),
                  s.get('potionCount', 0), len(pots), len(deck), sum(bool(c['upgraded']) for c in deck),
                  s['cardTypeCounts'][0], s['cardTypeCounts'][2]]
        for c in deck:
            j = self.ci.get(c['id'])
            if j is not None:
                v[12 + j] += 1
        for r in s['relics']:
            j = self.ri.get(r['id'])
            if j is not None:
                v[12 + len(self.cards) + j] = 1
        return v


def load_model(prefix):
    import xgboost as xgb
    spec = json.load(open(prefix + '.spec.json'))
    model = xgb.XGBClassifier()
    model.load_model(prefix + '.xgb.json')
    sha = hashlib.sha256(open(prefix + '.xgb.json', 'rb').read()).hexdigest()
    return model, Features(spec['cards'], spec['relics']), sha


def train(args):
    import xgboost as xgb
    from collections import Counter
    runs = runs_from_units(args.units)
    cc, rc = Counter(), Counter()
    for y, fights in runs.values():
        for f in fights:
            cc.update(c['id'] for c in f['transition']['post']['deck'])
            rc.update(r['id'] for r in f['transition']['post']['relics'])
    feat = Features([c for c, _ in cc.most_common(150)], [r for r, _ in rc.most_common(120)])
    X, y = [], []
    for (arm, seed), (label, fights) in runs.items():
        for f in fights:
            if f['transition']['combatOutcome'] == 1 and f['encounter'] != HEART:
                X.append(feat(f['transition']['post'], f['act'], f['floor']))
                y.append(label)
    model = xgb.XGBClassifier(objective='binary:logistic', n_estimators=400, max_depth=5, learning_rate=0.05,
                              subsample=0.8, colsample_bytree=0.5, n_jobs=4, random_state=0)
    model.fit(np.array(X), np.array(y))
    model.save_model(args.out + '.xgb.json')
    json.dump({'cards': feat.cards, 'relics': feat.relics, 'runs': len(runs), 'rows': len(y),
               'units': [os.path.basename(u) for u in args.units]}, open(args.out + '.spec.json', 'w'))
    print(f'train: {len(runs)} runs, {len(y)} post-fight states -> {args.out}.xgb.json')


def estimate(args):
    model, feat, sha = load_model(args.model)
    runs = runs_from_units(args.units)
    b, a = args.pair.split(',')
    reps = {}
    for line in open(args.replays):
        r = json.loads(line)
        if 'error' in r or not r.get('valid'):
            raise SystemExit(f'invalid replay row: {line[:200]}')
        if r['replicate'] == 0:
            if not r.get('identity'):
                raise SystemExit(f'identity replay mismatch: {line[:200]}')
            continue
        reps.setdefault((r['arm'], r['sourceSeed'], r['fightIdx']), []).append(r)

    # V of every actual and replayed post state; the model is called once on all live non-Heart states.
    pending, values = [], {}
    for (arm, seed), (y, fights) in runs.items():
        for f in fights:
            k = (arm, seed, f['fightIdx'])
            if k not in reps:
                continue
            posts = [('real', f['transition']['post'], f['transition']['combatOutcome'])]
            posts += [(f'r{r["replicate"]}', r['post'], r['combatOutcome']) for r in reps[k]]
            for tag, post, outcome in posts:
                if outcome != 1:
                    values[(k, tag)] = 0.0           # death
                elif f['encounter'] == HEART:
                    values[(k, tag)] = 1.0           # a won Heart is the kill
                else:
                    pending.append(((k, tag), feat(post, f['act'], f['floor'])))
    if pending:
        pr = model.predict_proba(np.array([x for _, x in pending]))[:, 1]
        for (key, _), p in zip(pending, pr):
            values[key] = float(p)
    seeds = sorted({s for (arm, s) in runs if arm == b} & {s for (arm, s) in runs if arm == a})
    ms = {len(v) for v in reps.values()}
    if len(ms) != 1:
        raise SystemExit(f'unequal replicate counts {sorted(ms)}')
    m = ms.pop()
    beta = args.beta if args.beta is not None else m / (m + 1)

    def per_run(arm, seed):
        y, fights = runs[(arm, seed)]
        luck = 0.0
        for f in fights:
            k = (arm, seed, f['fightIdx'])
            if k in reps:
                rep = np.mean([values[(k, f'r{r["replicate"]}')] for r in reps[k]])
                luck += values[(k, 'real')] - rep
        return y, luck

    D_raw, D_cv = [], []
    for s in seeds:
        yb, lb = per_run(b, s)
        ya, la = per_run(a, s)
        D_raw.append(yb - ya)
        D_cv.append((yb - beta * lb) - (ya - beta * la))
    D_raw, D_cv = np.array(D_raw), np.array(D_cv)
    rng = np.random.default_rng(0)
    idx = rng.integers(0, len(seeds), (args.boot, len(seeds)))

    def ci(d):
        mm = d[idx].mean(1)
        return [float(np.percentile(mm, 2.5)), float(np.percentile(mm, 97.5))]

    res = {'pair': f'{b}-{a}', 'seeds': len(seeds), 'replicates': m, 'beta': beta, 'value_model_sha256': sha,
           'replayed_fights': len(reps),
           'raw': {'diff': float(D_raw.mean()), 'ci': ci(D_raw), 'sd': float(D_raw.std(ddof=1))},
           'aivat': {'diff': float(D_cv.mean()), 'ci': ci(D_cv), 'sd': float(D_cv.std(ddof=1))}}
    res['sd_ratio'] = res['aivat']['sd'] / res['raw']['sd']
    res['effective_seed_multiplier'] = 1 / res['sd_ratio'] ** 2
    json.dump(res, sys.stdout, indent=1)
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    t = sub.add_parser('train')
    t.add_argument('out')
    t.add_argument('units', nargs='+')
    e = sub.add_parser('estimate')
    e.add_argument('model')
    e.add_argument('replays')
    e.add_argument('units', nargs='+')
    e.add_argument('--pair', required=True, help='B,A: report B minus A')
    e.add_argument('--beta', type=float, default=None)
    e.add_argument('--boot', type=int, default=4000)
    a = ap.parse_args()
    (train if a.cmd == 'train' else estimate)(a)


if __name__ == '__main__':
    main()
