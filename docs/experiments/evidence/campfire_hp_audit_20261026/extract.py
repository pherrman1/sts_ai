import gzip, json, glob, os, sys, pickle, re
from concurrent.futures import ProcessPoolExecutor
EFF = {0:'smith',17:'rest',18:'recall',19:'lift',20:'dig',21:'leave'}
def fo(r): return r['record']['obs.fixed_observation']
def ups(r): return sum(r['record']['obs.deck.upgrades'])
def one(path):
    arm, seed = re.match(r'.*/([A-Z]+)-(\d+)\.jsonl\.gz$', path).groups()
    rows = [json.loads(l) for l in gzip.open(path, 'rt')]
    out = rows[-1] if rows[-1]['type'] == 'outcome' else None
    states = {r['index']: r for r in rows if r['type'] == 'state'}
    decs = {r['stateIndex']: r for r in rows if r['type'] == 'decision' and 'stateIndex' in r}
    fires = []
    for i, s in sorted(states.items()):
        if s.get('screen') != 7: continue
        d = decs.get(i, {})
        f = fo(s); nxt = None
        for j in range(i + 1, i + 6):
            t = states.get(j)
            if t is not None and t.get('screen') not in (7, 4): nxt = t; break
        eff = None
        if d.get('selectedKey'):
            m = re.search(r'effect=(\d+)', d['selectedKey']); eff = EFF.get(int(m.group(1)), m.group(1))
        elif d.get('by') == 'heart_key': eff = 'recall'
        inferred = None
        if nxt is not None:
            g = fo(nxt)
            if g[7] > f[7]: inferred = 'recall'
            elif ups(nxt) > ups(s): inferred = 'smith'
            elif g[0] > f[0]: inferred = 'rest'
            else: inferred = 'other'
        legal = []
        if d.get('root'):
            for c in d['root']['candidates']:
                m = re.search(r'effect=(\d+)', c['key']); legal.append(EFF.get(int(m.group(1)), m.group(1)))
        pri = {}
        if d.get('root'):
            for c in d['root']['candidates']:
                m = re.search(r'effect=(\d+)', c['key']); e = EFF.get(int(m.group(1)), m.group(1))
                pri[e] = pri.get(e, 0) + c['prior']
        fires.append(dict(act=s['act'], floor=s['floor'], hp=f[0], maxhp=f[1], ruby=f[7], by=d.get('by'),
                          eff=eff, inferred=inferred, legal=sorted(set(legal)), prior=pri, nups=ups(s)))
    fights = []
    cp = path.replace('.jsonl.gz', '.ctm.jsonl.gz')
    if os.path.exists(cp):
        for l in gzip.open(cp, 'rt'):
            r = json.loads(l); g = r['predictorInput']['globals']
            fights.append(dict(act=r['act'], floor=r['floor'], enc=r['encounter'], room=r['roomClass'], hp=g['curHp'],
                               maxhp=g['maxHp'], relics=[x['relicId'] for x in r['predictorInput']['relics']], out=r['transition']['combatOutcome'], post=r['transition']['post']['curHp']))
    return (int(seed), arm), dict(out=out and {k: out.get(k) for k in ('heartKilled','finalAct','finalFloor','complete','integrityPassed')}, fires=fires, fights=fights)
if __name__ == '__main__':
    root, dst = sys.argv[1], sys.argv[2]
    paths = [p for p in glob.glob(root + '/out/units/*/*.jsonl.gz') if not p.endswith('.ctm.jsonl.gz')]
    with ProcessPoolExecutor(4) as ex: R = dict(ex.map(one, paths, chunksize=16))
    pickle.dump(R, open(dst, 'wb')); print(len(R))
