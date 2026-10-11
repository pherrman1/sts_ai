"""Resolve ambiguous recorded choices (several actions with the same successor fingerprint).
For each seed whose replay diverges, switch the latest ambiguous decision before the first
mismatch to its next alternative and replay (prod arm, 1 search), until the seed matches up to its
last target or alternatives run out. Writes force_fixed.csv."""
import pickle, csv, collections, subprocess, os, sys, itertools
G = os.path.expanduser('~/g')
hdr, rows = pickle.load(open(f'{G}/gold_all.pkl', 'rb'))
NF = len(hdr) - 7
iA, iC = hdr.index('action'), hdr.index('chosen')
gold = collections.defaultdict(list); alts = collections.defaultdict(list)
for x in rows:
    gold[int(x[0])].append(x)
    if x[iC] == '1' and x[iA] != '-1': alts[(int(x[0]), int(x[1]))].append(int(x[iA]))
force = {}
for l in open(f'{G}/force.csv'):
    s, d, b = l.strip().split(','); force[(int(s), int(d))] = int(b)
targets = collections.defaultdict(list)
for l in open(f'{G}/targets.csv'):
    s, d = l.strip().split(','); targets[int(s)].append(int(d))

def first_mismatch(path, s):
    mine = [x for x in csv.reader(open(path)) if x and x[0].isdigit()]
    g = gold[s]; i = 0
    while i < len(mine) and i < len(g) and mine[i][:NF] == g[i][:NF]: i += 1
    lastTargetRow = max(j for j, x in enumerate(mine) if int(x[1]) == max(targets[s])) if any(int(x[1]) == max(targets[s]) for x in mine) else -1
    return (None if i > lastTargetRow and lastTargetRow >= 0 else i), mine

def replay(s, fpath, tag):
    d = f'{G}/fix/{s}'; os.makedirs(d, exist_ok=True)
    out = f'{d}/{tag}.csv'; js = f'{d}/{tag}.jsonl'
    for p in (out, js):
        if os.path.exists(p): os.remove(p)
    env = dict(os.environ)
    cmd = f'export ARM=prod; source {G}/env_common.sh; export STRATEGIC_MCTS_FORCE={fpath} STRATEGIC_MCTS_OUT={js} STRATEGIC_MCTS_REPS=1; ' \
          f'bash tools/seed_guard.sh {G}/one_combat strategicgen2 1 2000 20 {out} {s} > {d}/{tag}.log 2>&1'
    subprocess.run(['bash', '-c', cmd], cwd='/home/user/sts_ai', env=env, check=True)
    return out

def fix_seed(s, first_csv):
    fm, mine = first_mismatch(first_csv, s)
    tried = set(); cur = dict(force); n = 0
    while fm is not None and n < 12:
        decs = sorted({int(x[1]) for x in mine[:fm + 1]})
        cand = [d for d in decs if len(alts[(s, d)]) > 1]
        # latest ambiguous decision before the mismatch with an untried alternative
        choice = None
        for d in reversed(cand):
            for b in alts[(s, d)]:
                if (d, b) not in tried and cur.get((s, d)) != b: choice = (d, b); break
            if choice: break
        if not choice: return None, fm
        tried.add(choice); cur[(s, choice[0])] = choice[1]; n += 1
        fp = f'{G}/fix/{s}/force-{n}.csv'
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, 'w') as f:
            for (a, d), b in cur.items():
                if a == s: f.write(f'{a},{d},{b}\n')
        nfm, mine = first_mismatch(replay(s, fp, f'try{n}'), s)
        if nfm is not None and nfm <= fm: cur[(s, choice[0])] = force[(s, choice[0])]  # no progress: revert
        else: fm = nfm
    return ({k: v for k, v in cur.items() if k[0] == s} if fm is None else None), fm

if __name__ == '__main__':
    arm = sys.argv[1]
    fixed = dict(force); log = []
    for path in sorted(os.listdir(f'{G}/out/{arm}')):
        if not path.endswith('.csv'): continue
        s = int(path.split('.')[0])
        fm, _ = first_mismatch(f'{G}/out/{arm}/{path}', s)
        if fm is None: continue
        res, left = fix_seed(s, f'{G}/out/{arm}/{path}')
        log.append((s, fm, res is not None, left)); print(s, 'first mismatch row', fm, 'fixed' if res else f'NOT fixed (row {left})', flush=True)
        if res: fixed.update(res)
    with open(f'{G}/force_fixed.csv', 'w') as f:
        for (s, d), b in sorted(fixed.items()): f.write(f'{s},{d},{b}\n')
    with open(f'{G}/fix_log.csv', 'w') as f:
        for r in log: f.write(','.join(map(str, r)) + '\n')
