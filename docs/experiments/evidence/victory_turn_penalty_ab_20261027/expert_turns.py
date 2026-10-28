"""Context only (#880): combat lengths in Baalorlord's Ironclad A20 runs, from the .run `damage_taken` list.
usage: python3 -I expert_turns.py <raw_dir> [OUT.json]
Raw files: /mnt/project-files/expert-replay/baalorlord_ironclad_raw (ids and hashes in
docs/experiments/evidence/expert_play_audit_20261026). The .run `turns` is the game's turn counter at combat end
(player turn 1 = 1); the bot's trace `turns` is BattleContext::turn (0-based), so analyze.py compares turns + 1.
Room class from path_per_floor (M NORMAL, E ELITE, B BOSS, other letters OTHER); act counts the None separators."""
import glob
import json
import os
import sys

import numpy as np

ROOM = {'M': 'NORMAL', 'E': 'ELITE', 'B': 'BOSS'}


def stats(t):
    if not t:
        return {'n': 0}
    t = np.asarray(t, float)
    return {'n': len(t), 'mean': round(float(t.mean()), 3), 'median': float(np.median(t)),
            'p90': float(np.percentile(t, 90)), 'p95': float(np.percentile(t, 95)), 'max': int(t.max())}


raw = sys.argv[1]
fights = []
runs = 0
for p in sorted(glob.glob(os.path.join(raw, '*.json'))):
    try:
        d = json.load(open(p))
    except ValueError:
        continue
    if d.get('character_chosen') != 'IRONCLAD' or d.get('ascension_level') != 20 or d.get('is_endless'):
        continue
    runs += 1
    ppf = d.get('path_per_floor') or []
    for x in d.get('damage_taken') or []:
        f = int(x['floor'])
        letter = ppf[f - 1] if 0 < f <= len(ppf) else None
        act = 1 + sum(1 for y in ppf[:f - 1] if y is None)
        fights.append({'act': act, 'room': ROOM.get(letter, 'OTHER'), 'turns': int(x['turns'])})
res = {'runs': runs, 'fights': len(fights), 'all': stats([x['turns'] for x in fights]),
       'byRoom': {r: stats([x['turns'] for x in fights if x['room'] == r]) for r in ('NORMAL', 'ELITE', 'BOSS', 'OTHER')},
       'byActRoom': {f'{a}-{r}': stats([x['turns'] for x in fights if x['act'] == a and x['room'] == r])
                     for a in (1, 2, 3, 4) for r in ('NORMAL', 'ELITE', 'BOSS')}}
text = json.dumps(res, indent=1)
print(text)
if len(sys.argv) > 2:
    open(sys.argv[2], 'w').write(text + '\n')
