# Per-run: outcome, searched-decision values, and per-fight pre/post compact states.
import json, sys, tarfile, gzip, os
def st(s, act, floor):
    return dict(act=act, floor=floor, hp=s['curHp'], mhp=s['maxHp'], gold=s.get('gold', 0),
                pc=s.get('potionCount', 0), ctc=s.get('cardTypeCounts', [0]*4),
                deck=[c['id'] * 2 + int(c['upgraded']) for c in s['deck']],
                rel=[r['id'] for r in s['relics']], pot=[p for p in s.get('potions', []) if p != 1])
def runs_from_tar(path):
    out = []
    with tarfile.open(path) as tf:
        mem = {os.path.basename(m.name): m for m in tf.getmembers()}
        for n, m in mem.items():
            if n.endswith('.ctm.jsonl.gz') or not n.endswith('.jsonl.gz'): continue
            tag = n[:-len('.jsonl.gz')]; arm, seed = tag.rsplit('-', 1)
            dec = []; outcome = None
            for l in gzip.decompress(tf.extractfile(m).read()).decode().splitlines():
                d = json.loads(l)
                if d.get('type') == 'outcome': outcome = d
                elif 'root' in d and d.get('searched'):
                    r = d['root']; c = r.get('candidates', [])
                    if len(c) < 2: continue
                    sel = [x for x in c if x['id'] == r['selectedId']][0]
                    dec.append((d['act'], d['floor'], d['screen'], r['rootMeanQ'], sel['q']))
            fights = []
            for l in gzip.decompress(tf.extractfile(mem[tag + '.ctm.jsonl.gz']).read()).decode().splitlines():
                d = json.loads(l); t = d['transition']; g = d['predictorInput']['globals']
                fights.append(dict(rc=d['roomClass'], enc=d['encounter'], out=t['combatOutcome'],
                                   pre=st(t['pre'], d['act'], d['floor']), post=st(t['post'], d['act'], d['floor'])))
            out.append(dict(arm=arm, seed=int(seed), y=int(outcome['heartKilled']), dec=dec, fights=fights))
    return out
if __name__ == '__main__':
    with open(sys.argv[1], 'w') as f:
        for p in sys.argv[2:]:
            for r in runs_from_tar(p): f.write(json.dumps(r) + '\n')
