"""Heart-readiness Stage 0 extraction (2026-10-25): every CTM fight row of a game rescored as a Heart fight with the
Act-4 survival model (rA = actual HP, rF = HP set to max HP). Usage: extract.py 683|676 LO HI OUT.pkl; the §683 units
were read from a local --extract copy, the §676 units from /mnt/project-files/ctm-calibration-ab/units."""
import gzip, json, os, re, sys, tarfile, pickle
sys.path.insert(0, '/home/user/sts_ai/tools')
import numpy as np
from ctm_act4_survival import features, NAMES

def load_trees(path):
    tok = open(path).read().split()
    i = 0
    assert tok[i] == 'nfeat'; nf = int(tok[i+1]); i += 2
    sel = []
    for _ in range(nf):
        sel.append(NAMES.index(tok[i+1])); i += 2
    assert tok[i] == 'logistic'; i += 2
    assert tok[i] == 'base_score'; base = float(tok[i+1]); i += 2
    assert tok[i] == 'ntrees'; nt = int(tok[i+1]); i += 2
    trees = []
    for t in range(nt):
        assert tok[i] == 'tree'; nn = int(tok[i+2]); i += 3
        nodes = []
        for _ in range(nn):
            if tok[i] == 'L':
                nodes.append((-1, float(tok[i+1]), 0, 0)); i += 2
            else:
                nodes.append((sel[int(tok[i+1])], np.float32(tok[i+2]), int(tok[i+3]), int(tok[i+4]))); i += 5
        trees.append(nodes)
    return np.log(base/(1-base)), trees

BASE, TREES = load_trees('/home/user/sts_ai/models/candidates/ctm_act4_survival_trees.txt')

def p_death(x):
    m = BASE
    for nodes in TREES:
        n = 0
        while nodes[n][0] >= 0:
            f, th, y, no = nodes[n]
            n = y if x[f] < th else no
        m += nodes[n][1]
    return 1/(1+np.exp(-m))

def ready_variants(p):
    g = dict(p['globals']); g['encounter'] = 57
    out = {}
    q = dict(p); q['globals'] = g
    out['actual'] = 1 - p_death(features(q))
    g2 = dict(g); g2['curHp'] = g['maxHp']; q2 = dict(p); q2['globals'] = g2
    out['full'] = 1 - p_death(features(q2))
    return out

def game(jl, ctm):
    rows = [json.loads(x) for x in gzip.decompress(jl).splitlines()]
    foot = rows[-1]
    if foot.get('type') != 'outcome' or not foot.get('complete'):
        return None
    fights = []
    for line in gzip.decompress(ctm).splitlines():
        r = json.loads(line)
        p = r['predictorInput']; g = p['globals']
        rv = ready_variants(p)
        fights.append(dict(act=r['act'], floor=r['floor'], enc=r['encounter'], room=r['roomClass'],
                           curHp=g['curHp'], maxHp=g['maxHp'], deck=len(p['cards']),
                           upg=sum(c['upgraded'] for c in p['cards']), gold=g['gold'],
                           outcome=r['transition']['combatOutcome'], rA=rv['actual'], rF=rv['full']))
    return dict(kill=int(bool(foot['heartKilled'])), finalAct=foot['finalAct'], floor=foot['finalFloor'], fights=fights)

def main():
    which = sys.argv[1]; out = {}
    if which == '683':
        root = '/tmp/claude-0/-home-user-sts-ai/1f92af47-3350-54c1-9a01-50a6a653ef87/scratchpad/final/out/units'
        seeds = sorted(x for x in os.listdir(root) if x.isdigit())
        lo, hi = int(sys.argv[2]), int(sys.argv[3])
        for s in seeds[lo:hi]:
            for a in ('D', 'MAP', 'OFF'):
                d = os.path.join(root, s)
                out[(s, a)] = game(open(f'{d}/{a}-{s}.jsonl.gz', 'rb').read(), open(f'{d}/{a}-{s}.ctm.jsonl.gz', 'rb').read())
    else:
        root = '/mnt/project-files/ctm-calibration-ab/units'
        tars = sorted(os.listdir(root))
        lo, hi = int(sys.argv[2]), int(sys.argv[3])
        for t in tars[lo:hi]:
            tf = tarfile.open(os.path.join(root, t)); m = {x.name: x for x in tf.getmembers()}
            s = t.split('.')[0]
            for a in ('A', 'C'):
                b = f'out/units/{s}/{a}-{s}'
                if b + '.jsonl.gz' in m and b + '.ctm.jsonl.gz' in m:
                    out[(s, a)] = game(tf.extractfile(m[b+'.jsonl.gz']).read(), tf.extractfile(m[b+'.ctm.jsonl.gz']).read())
    pickle.dump(out, open(sys.argv[4], 'wb'))

main()
