#!/usr/bin/env python3
"""Post-fight states (first REWARDS-screen decision per floor) from LONG_B trajectory parts, perturbed as §747's
prices.py does. Writes records.jsonl (heart1score input) and meta.json (gates.py format: seed, set, room, act, ...).
Room: the map node at (obs.mapX, obs.mapY): ELITE (3) -> ELITE, MONSTER (4) -> NORMAL, mapY 15 -> BOSS; every
other room (events, treasure, shops) is dropped. Acts 1-3 -> set 'postfight'; Act-4 elites -> set 'act4elite'.
usage: build_states_traj.py <dir with traj-*.jsonl.gz> <out dir>"""
import glob, gzip, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'heart1_value_leaf_teacher_20261102'))
from prices import perturbations, apply  # noqa: E402


def room_of(rec):
    x, y = rec['obs.mapX'], rec['obs.mapY']
    if y == 15:
        return 'BOSS'
    for j, (xx, yy) in enumerate(zip(rec['obs.map.xs'], rec['obs.map.ys'])):
        if xx == x and yy == y:
            return {3: 'ELITE', 4: 'NORMAL'}.get(rec['obs.map.roomTypes'][j])
    return None


def main(src, out):
    os.makedirs(out, exist_ok=True)
    states, heart = [], {}
    for path in sorted(glob.glob(f'{src}/traj-*.jsonl.gz')):
        part = os.path.basename(path)[:-len('.jsonl.gz')]
        seen = set()
        for line in gzip.open(path, 'rt'):
            r = json.loads(line)
            if r.get('type') == 'game':
                heart[(part, str(r['seed']))] = int(bool(r['outcome']['heart_kill']))
                continue
            rec = r.get('record')
            if r.get('type') != 'decision' or not rec or rec['screen_state'] != 2:
                continue
            key = (r['seed'], r['floor'])
            if key in seen:
                continue
            seen.add(key)
            room = room_of(rec)
            if room is None or r['act'] not in (1, 2, 3, 4) or (r['act'] == 4 and room != 'ELITE'):
                continue
            states.append(dict(part=part, game=str(r['seed']), act=r['act'], floor=r['floor'], room=room,
                               set='postfight' if r['act'] <= 3 else 'act4elite', rec=rec, logged=r['value']))
    meta = []
    with open(os.path.join(out, 'records.jsonl'), 'w') as f:
        for i, s in enumerate(states):
            rec = s['rec']; fo = rec['obs.fixed_observation']
            for name, op in perturbations(rec):
                f.write(json.dumps(apply(rec, op)) + '\n')
                meta.append({'seed': i, 'game': s['part'] + ':' + s['game'], 'set': s['set'], 'room': s['room'],
                             'act': s['act'], 'floor': s['floor'], 'heart': heart[(s['part'], s['game'])],
                             'pert': name, 'hp': fo[0], 'mhp': fo[1], 'gold': fo[2],
                             'logged': s['logged'] if name == 'base' else None,
                             'potion': rec['obs.potions'][int(name[4:])] if name.startswith('pot-') else None})
    json.dump(meta, open(os.path.join(out, 'meta.json'), 'w'))
    print(len(states), 'states', len(meta), 'records')


if __name__ == '__main__':
    main(*sys.argv[1:3])
