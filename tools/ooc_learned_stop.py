"""Learned OOC MCTS stop model: P(the root visit leader at a checkpoint is the full search's choice).

usage:
  cv     OUT_DIR DATA_DIR [DATA_DIR ...]      leave-seeds-out scores of the learned rule and the gap ladder
  export OUT_DIR TREES.txt DATA_DIR [...]     fit on every row, write CompactTreeNet text, parity.csv and
                                              fixture.jsonl (256 checkpoints for ooclearnedstoptest)

DATA_DIR holds STS_RUN_PROFILE S-a20-SEED.runprof.jsonl files with their S-a20-SEED.env; only runs whose
effective STS_OOC_MCTS_SIMS is 4096 are used. Rows are root checkpoints 128..2048 below the completed
simulations of searched, non-aborted roots with at least two actions. "same_action" is an offline proxy (the
action kept by the rule vs the action the full search chose), not winrate; "est_cpu" scales each root's thread
CPU linearly by the simulations kept, an estimate. Features match oocLearnedStopFeatures in
apps/one_combat/ooc_mcts_adapter.cpp.
"""
import collections, glob, hashlib, json, os, re, sys
from pathlib import Path
import numpy as np

CPS = (128, 256, 512, 1024, 2048)
NAMES = ['log2_sims', 'gap_frac', 'top_visit_frac', 'second_visit_frac', 'top_prior', 'second_prior',
         'top_is_prior_argmax', 'top_q_minus_best_other_q', 'top_q_minus_second_q', 'best_q_minus_top_q',
         'n_actions', 'act', 'floor', 'screen']
PARAMS = dict(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8, min_child_weight=5,
              eval_metric='logloss', n_jobs=1, random_state=0)


def load_roots(dirs):
    roots, digest = [], hashlib.sha256()
    for d in dirs:
        for f in sorted(glob.glob(os.path.join(d, '*.runprof.jsonl'))):
            env = dict(l.strip().split('=', 1) for l in open(f.replace('.runprof.jsonl', '.env')) if '=' in l)
            if env.get('STS_OOC_MCTS_SIMS') != '4096': continue
            digest.update(open(f, 'rb').read())
            for l in open(f):
                r = json.loads(l)
                if r.get('kind') != 'ooc_decision' or r.get('aborted') or r.get('singleton_bypass'): continue
                if not r.get('checkpoints') or len(r['actions']) < 2: continue
                r['stack'] = 'silver4' if 'STS_OOC_MCTS_ACT4_SILVER_SIMS' in env else 'ctm4'
                roots.append(r)
    return roots, digest.hexdigest()


# Label: most visits, ties to the lower id. The planner's own selection (visits_q_id) breaks visit ties by Q, so
# on an exact final visit tie the label can name a different action than the one played; rare, and the online
# rule only reads checkpoint statistics.
def final(r): return max(r['actions'], key=lambda a: a['visits'])['id']


def leader(actions):
    # The planner's visit selection: most visits, ties to the lower id (input order is by id).
    return max(actions, key=lambda a: (a['visits'], -a['id']))


def features(r, cp):
    acts = cp['actions']; c = cp['simulations']
    top = leader(acts)
    sec = max((a for a in acts if a['id'] != top['id']), key=lambda a: (a['visits'], -a['id']))
    prior_top = max(acts, key=lambda a: (a['prior'], -a['id']))
    others = [a['q'] for a in acts if a['visits'] > 0 and a['id'] != top['id']]
    visited = [a['q'] for a in acts if a['visits'] > 0]
    return [np.log2(c), (top['visits'] - sec['visits']) / c, top['visits'] / c, sec['visits'] / c,
            top['prior'], sec['prior'], float(prior_top['id'] == top['id']),
            top['q'] - (max(others) if others else top['q']), top['q'] - sec['q'],
            max(visited) - top['q'], len(acts), r['act'], r['floor'], r['screen']]


def rows(roots):
    X, y, owner, sims = [], [], [], []
    for i, r in enumerate(roots):
        for cp in r['checkpoints']:
            if cp['simulations'] in CPS and cp['simulations'] < r['completed_simulations']:
                X.append(features(r, cp)); y.append(int(leader(cp['actions'])['id'] == final(r)))
                owner.append(i); sims.append(cp['simulations'])
    return np.array(X, dtype=np.float32), np.array(y), np.array(owner), np.array(sims)


def model():
    import xgboost as xgb
    return xgb.XGBClassifier(**PARAMS)


def cv(out, dirs):
    roots, digest = load_roots(dirs)
    X, y, owner, sims = rows(roots)
    seeds = sorted({r['seed'] for r in roots})
    fold = {s: k % 4 for k, s in enumerate(seeds)}
    rfold = np.array([fold[r['seed']] for r in roots])
    pred = np.zeros(len(y))
    for k in range(4):
        tr = rfold[owner] != k
        m = model(); m.fit(X[tr], y[tr]); pred[~tr] = m.predict_proba(X[~tr])[:, 1]
    by_root = collections.defaultdict(list)
    for j in range(len(y)): by_root[owner[j]].append(j)

    def score(stop, sub):
        agree = cpu = 0.0
        for i in sub:
            r = roots[i]; used, pick = r['completed_simulations'], final(r)
            for j in sorted(by_root[i], key=lambda j: sims[j]):
                if stop(j):
                    used = sims[j]
                    pick = leader(next(cp for cp in r['checkpoints'] if cp['simulations'] == used)['actions'])['id']
                    break
            agree += pick == final(r); cpu += r['thread_cpu_seconds'] * used / r['completed_simulations']
        return round(agree / len(sub), 4), int(len(sub) - agree), round(cpu / sum(roots[i]['thread_cpu_seconds'] for i in sub), 3)

    result = {'data_sha256': digest, 'seeds': len(seeds), 'roots': len(roots), 'rows': int(len(y)),
              'by_stack': dict(collections.Counter(r['stack'] for r in roots)), 'params': PARAMS, 'groups': {}}
    for name in ['all'] + sorted({r['stack'] for r in roots}):
        sub = [i for i, r in enumerate(roots) if name == 'all' or r['stack'] == name]
        g = result['groups'][name] = {'roots': len(sub)}
        for lad, gap in (((1024,), 0.7), ((512, 1024), 0.8), ((512, 1024), 0.7)):
            g[f'gap {",".join(map(str, lad))}:{gap}'] = score(
                lambda j, lad=lad, gap=gap: sims[j] in lad and X[j][1] >= gap, sub)
        for tau in (0.995, 0.99, 0.98, 0.97):
            g[f'learned tau={tau}'] = score(lambda j, tau=tau: pred[j] >= tau, sub)
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / 'cv.json').write_text(json.dumps(result, indent=1) + '\n')
    print(json.dumps(result, indent=1))


def export(out, trees_path, dirs):
    roots, digest = load_roots(dirs)
    X, y, owner, sims = rows(roots)
    m = model(); m.fit(X, y)
    bst = m.get_booster(); bst.feature_names = NAMES
    dumps = bst.get_dump(dump_format='json')
    used = sorted({n for t in dumps for n in re.findall(r'"split": "([^"]+)"', t)}, key=NAMES.index)
    base_score = float(json.loads(bst.save_config())['learner']['learner_model_param']['base_score'].strip('[]'))
    lines = [f'nfeat {len(used)}'] + [f'feat {n}' for n in used] + ['logistic 1', f'base_score {base_score!r}',
                                                                      f'ntrees {len(dumps)}']
    position = {n: i for i, n in enumerate(used)}
    for t, text in enumerate(dumps):
        order, queue = [], [json.loads(text)]
        while queue:  # breadth-first, so the last node is a leaf
            node = queue.pop(0)
            order.append(node)
            queue += node.get('children', [])
        index = {n['nodeid']: i for i, n in enumerate(order)}
        lines.append(f'tree {t} {len(order)}')
        for n in order:
            if 'leaf' in n:
                lines.append(f'L {n["leaf"]!r}')
            else:
                lines.append(f'S {position[n["split"]]} {float(n["split_condition"])!r} {index[n["yes"]]} '
                             f'{index[n["no"]]}')
    Path(trees_path).write_text('\n'.join(lines) + '\n')
    Path(out).mkdir(parents=True, exist_ok=True)
    p = m.predict_proba(X)[:, 1]
    with open(Path(out) / 'parity.csv', 'w') as f:
        f.write(','.join(NAMES) + ',p_same\n')
        for x, v in zip(X, p):
            f.write(','.join(repr(float(a)) for a in x) + f',{float(v)!r}\n')
    roots_cp = [(owner[j], sims[j]) for j in range(len(y))]
    with open(Path(out) / 'fixture.jsonl', 'w') as f:
        for j in np.linspace(0, len(y) - 1, 256).astype(int):
            r = roots[roots_cp[j][0]]
            cp = next(c for c in r['checkpoints'] if c['simulations'] == roots_cp[j][1])
            f.write(json.dumps({'act': r['act'], 'floor': r['floor'], 'screen': r['screen'],
                                'simulations': cp['simulations'], 'actions': cp['actions'],
                                'p_same': float(p[j])}) + '\n')
    sha = hashlib.sha256(Path(trees_path).read_bytes()).hexdigest()
    (Path(out) / 'export.json').write_text(json.dumps({
        'data_sha256': digest, 'seeds': len({r['seed'] for r in roots}), 'roots': len(roots), 'rows': int(len(y)),
        'params': PARAMS, 'trees': len(dumps), 'features': used, 'base_score': base_score,
        'trees_sha256': sha}, indent=1) + '\n')
    print(trees_path, len(dumps), 'trees', len(used), 'features', 'sha256', sha)


if __name__ == '__main__':
    if len(sys.argv) < 4: sys.exit(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == 'cv':
        cv(args[0], args[1:])
    elif cmd == 'export':
        export(args[0], args[1], args[2:])
    else:
        sys.exit(__doc__)
