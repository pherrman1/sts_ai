"""Elite profile + map-root elite options from §683 records.
python3 -I elite_extract.py UNITS_DIR OUT.pkl"""
import gzip, json, os, sys, pickle
from multiprocessing import Pool

ELITE, REST = 3, 1


def maxcount(xs, ys, rt, pxs, typ):
    idx = {(x, y): i for i, (x, y) in enumerate(zip(xs, ys))}
    memo = {}
    def go(i):
        if i in memo: return memo[i]
        e = 1 if rt[i] == typ else 0
        nxt = [idx[(nx, ys[i] + 1)] for nx in pxs[i] if nx >= 0 and (nx, ys[i] + 1) in idx]
        memo[i] = e + (max(go(j) for j in nxt) if nxt else 0)
        return memo[i]
    return go


def downstream(xs, ys, rt, pxs):
    """Per node: (min, max) elites on any path from this node (inclusive) to the last row."""
    idx = {(x, y): i for i, (x, y) in enumerate(zip(xs, ys))}
    memo = {}

    def go(i):
        if i in memo: return memo[i]
        e = 1 if rt[i] == ELITE else 0
        nxt = [idx[(nx, ys[i] + 1)] for nx in pxs[i] if nx >= 0 and (nx, ys[i] + 1) in idx]
        if not nxt:
            memo[i] = (e, e)
        else:
            ch = [go(j) for j in nxt]
            memo[i] = (e + min(c[0] for c in ch), e + max(c[1] for c in ch))
        return memo[i]
    return idx, go


def game(path_jl, path_ctm):
    rows = [json.loads(x) for x in gzip.open(path_jl).read().splitlines()]
    foot = rows[-1]
    states = {r['index']: r for r in rows if r.get('type') == 'state'}
    roots = []
    for d in rows:
        if d.get('type') != 'decision' or not d.get('executed', True): continue
        s = states.get(d['stateIndex'])
        if not s or s['screen'] != 5 or s['act'] > 3: continue
        r = s['record']
        xs, ys, rt, pxs = r['obs.map.xs'], r['obs.map.ys'], r['obs.map.roomTypes'], r['obs.map.pathXs']
        idx, go = downstream(xs, ys, rt, pxs)
        my = r['obs.mapY']
        cy = my + 1
        fo = r['obs.fixed_observation']
        root = d.get('root') or {}
        cand = {c['id']: c for c in root.get('candidates', [])}
        kids = []
        for x in r['paths_offered']:
            i = idx.get((x, cy))
            if i is None: continue
            mn, mx = go(i)
            c = cand.get(x, {})
            kids.append(dict(x=x, room=rt[i], burning=(x == r['obs.map.burningEliteX'] and cy == r['obs.map.burningEliteY']),
                             emin=mn, emax=mx, prior=c.get('prior'), q=c.get('q'), visits=c.get('visits')))
        sel = d.get('selectedBits')
        if sel is None and 'selectedKey' in d: sel = int(d['selectedKey'].split(':')[1])
        if sel is None:
            for j in range(d['stateIndex'] + 1, d['stateIndex'] + 6):
                n = states.get(j)
                if n and n['act'] == s['act'] and n['record']['obs.mapY'] == cy:
                    sel = n['record']['obs.mapX']; break
        feats = {}
        if cy == 0:
            for name, typ in (('rest', 1), ('shop', 0), ('event', 2), ('monster', 4)):
                gm = maxcount(xs, ys, rt, pxs, typ)
                feats[name] = max(gm(idx[(x, cy)]) for x in r['paths_offered'] if (x, cy) in idx)
            feats['n_elite_nodes'] = sum(1 for v in rt if v == ELITE)
        roots.append(dict(act=s['act'], row=cy, feats=feats, hp=fo[0], maxhp=fo[1], gold=fo[2], by=d.get('by'), sel=sel,
                          searched=bool(d.get('searched')), kids=kids))
    fights = []
    for x in gzip.open(path_ctm).read().splitlines():
        f = json.loads(x)
        g = f['predictorInput']['globals']
        post = f['transition'].get('post')
        fights.append(dict(act=f['act'], floor=f['floor'], room=f['roomClass'], enc=f['encounter'], hp=g['curHp'],
                           maxhp=g['maxHp'], win=f['transition']['combatOutcome'] == 1,
                           hp_after=post.get('curHp') if isinstance(post, dict) else None))
    return dict(kill=int(bool(foot['heartKilled'])), finalAct=foot['finalAct'], floor=foot['finalFloor'],
                roots=roots, fights=fights)


def unit(args):
    root, s = args
    out = {}
    arms = sorted(f.split('-')[0] for f in os.listdir(os.path.join(root, s)) if f.endswith('.ctm.jsonl.gz'))
    for a in arms:
        d = os.path.join(root, s)
        out[(s, a)] = game(f'{d}/{a}-{s}.jsonl.gz', f'{d}/{a}-{s}.ctm.jsonl.gz')
    return out


if __name__ == '__main__':
    root = sys.argv[1]
    seeds = sorted(x for x in os.listdir(root) if x.isdigit())
    res = {}
    with Pool(4) as p:
        for o in p.imap_unordered(unit, [(root, s) for s in seeds], chunksize=8):
            res.update(o)
    pickle.dump(res, open(sys.argv[2], 'wb'))
    print(len(res))
