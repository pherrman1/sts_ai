#!/usr/bin/env python3
"""Post-fight (REWARDS screen, acts 1-3) states from extracted key-rules-ab units, plus §721 Heart entries,
perturbed as prices.py does. Writes records.jsonl (heart1score input) and meta.json (prices.py analyze format,
plus 'set' and 'room').
usage: build_states.py <extracted units root> <heart.pkl> <out dir>"""
import glob, json, os, pickle, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prices import perturbations, apply  # noqa: E402

HALLWAY_SAMPLE, SEED = 6000, 20261102


def games(root):
    for path in sorted(glob.glob(f'{root}/*/out/units/*/[RF]-*.jsonl')):
        if path.endswith('.ctm.jsonl'):
            continue
        rows = [json.loads(l) for l in open(path)]
        out = [r for r in rows if r.get('type') == 'outcome']
        if not out or not out[-1].get('complete') or not out[-1].get('integrityPassed'):
            continue
        ctm = path[:-len('.jsonl')] + '.ctm.jsonl'
        fights = {}
        for l in open(ctm):
            x = json.loads(l)
            if x.get('act') in (1, 2, 3):
                fights.setdefault(x['floor'], x['roomClass'])
        yield os.path.basename(path)[:-len('.jsonl')], rows, fights, int(bool(out[-1].get('heartKilled')))


def main(root, pkl, out):
    os.makedirs(out, exist_ok=True)
    states = []
    for game, rows, fights, heart in games(root):
        seen = set()
        for r in rows:
            if r.get('type') != 'state' or r.get('act') not in (1, 2, 3) or r['floor'] not in fights:
                continue
            rec = r.get('record')
            if not rec or rec['screen_state'] != 2 or r['floor'] in seen or not r.get('supported', True):
                continue
            seen.add(r['floor'])
            states.append(dict(set='postfight', game=game, act=r['act'], floor=r['floor'], room=fights[r['floor']],
                               heart=heart, rec={**rec, 'obs.act': r['act']}))
    rng = random.Random(SEED)
    hall = [s for s in states if s['room'] == 'NORMAL']
    keep = [s for s in states if s['room'] != 'NORMAL'] + rng.sample(hall, min(HALLWAY_SAMPLE, len(hall)))
    for e in pickle.load(open(pkl, 'rb')):
        rec = e['entry']['record']
        keep.append(dict(set='heart', game=e['game'] + '@' + e['campaign'], act=4, floor=e['entry']['floor'],
                         room='HEART_ENTRY', heart=int(e['heartKilled']), rec={**rec, 'obs.act': 4}))
    meta = []
    with open(os.path.join(out, 'records.jsonl'), 'w') as f:
        for i, s in enumerate(keep):
            rec = s['rec']; fo = rec['obs.fixed_observation']
            for name, op in perturbations(rec):
                f.write(json.dumps(apply(rec, op)) + '\n')
                meta.append({'seed': i, 'game': s['game'], 'set': s['set'], 'room': s['room'], 'act': s['act'],
                             'floor': s['floor'], 'heart': s['heart'], 'pert': name, 'hp': fo[0], 'mhp': fo[1],
                             'gold': fo[2], 'potion': rec['obs.potions'][int(name[4:])] if name.startswith('pot-') else None})
    json.dump(meta, open(os.path.join(out, 'meta.json'), 'w'))
    import collections
    print(len(states), 'post-fight states;', collections.Counter((s['set'], s['room']) for s in keep), len(meta), 'records')


if __name__ == '__main__':
    main(*sys.argv[1:4])
