#!/usr/bin/env python3
"""Issue #1056 paired probes: pick the probe states from §782's 1,024 G16 games and write units.txt.

    python3 -I make_units.py TRACE_DIR > units.txt      (TRACE_DIR holds out/units/*/G16-SEED.trace.jsonl.gz)

Rules fixed before any probe game (PREREG.md):
  smith       act-1 campfire on floor 15 (the one before the boss), HP <= 85 % of max, the net smithed
              (REST step leaves HP unchanged and the next step, a CARD_SELECT on floor 15, only upgrades) -> REST
  elite       a map decision with more than one path whose next room is an elite, HP <= 50 % of max
              -> the net's best path whose next room is not an elite
  corruption  a rewards decision that took Corruption -> the net's best other offered card
  runic       a boss-relic decision that took Runic Dome, Pyramid or Cube -> the net's best other offered relic
Per pattern the candidates are ordered by sha256("issue1056-probe-" + pattern + "-" + seed + "-" + idx) and the
first 128 are taken. One unit = one pair: production (STS_OOC_FORCE_DECISION=IDX:1:-) and the alternative
(IDX:1:KEY), both with the hidden future redrawn by salt 1 after the decision.
"""
import collections
import glob
import gzip
import hashlib
import json
import sys

N = 128
SALT = 1
FA_REST, ROOM_ELITE, CORRUPTION = 4, 3, 83          # heart1 FA_REST, Room::ELITE, CardId::CORRUPTION
RUNIC = {'RUNIC_CUBE': 56, 'RUNIC_DOME': 57, 'RUNIC_PYRAMID': 58}   # RelicId
KEYS = {'smith': 'ppo:fa=%d' % FA_REST, 'elite': 'ppo:path_not=%d' % ROOM_ELITE,
        'corruption': 'ppo:card_not=%d' % CORRUPTION,
        'runic': 'ppo:relic_not=' + ','.join(str(v) for v in sorted(RUNIC.values()))}


def candidates(trace_dir):
    out = collections.defaultdict(list)
    files = sorted(glob.glob(trace_dir + '/out/units/*/G16-*.trace.jsonl.gz'))
    if len(files) != 1024:
        raise SystemExit('expected 1024 G16 traces, found %d' % len(files))
    for f in files:
        seed = int(f.split('G16-')[1].split('.')[0])
        oo = [r for r in (json.loads(l) for l in gzip.open(f, 'rt')) if r['kind'] == 'ooc']
        nxt = {a['idx']: b for a, b in zip(oo, oo[1:])}
        for r in oo:
            pre, post = r['pre'], r['post']
            s, frac = pre['screen'], pre['hp'] / pre['maxHp']
            add = collections.Counter(post['deck']) - collections.Counter(pre['deck'])
            rel = [x for x in post['relics'] if x not in pre['relics']]
            n = nxt.get(r['idx'])
            if (s == 'REST' and pre['act'] == 1 and pre['floor'] == 15 and post['hp'] == pre['hp'] and frac <= 0.85
                    and n and n['pre']['screen'] == 'CARD_SELECT' and n['pre']['floor'] == 15):
                up = collections.Counter(n['post']['deck']) - collections.Counter(n['pre']['deck'])
                if up and all(k.endswith('+') for k in up):
                    out['smith'].append((seed, r['idx'], pre))
            if s == 'MAP' and post.get('room') == 'ELITE' and frac <= 0.5 and r['by'] != 'heart1_ppo_single':
                out['elite'].append((seed, r['idx'], pre))
            if s == 'REWARDS' and any(k.rstrip('+') == 'Corruption' for k in add):
                out['corruption'].append((seed, r['idx'], pre))
            if s == 'BOSS_RELIC' and set(rel) & set(RUNIC):
                out['runic'].append((seed, r['idx'], pre))
    return out


def main():
    cands = candidates(sys.argv[1])
    u = 0
    for pattern in ('smith', 'elite', 'corruption', 'runic'):
        ranked = sorted(cands[pattern], key=lambda c: hashlib.sha256(
            ('issue1056-probe-%s-%d-%d' % (pattern, c[0], c[1])).encode()).hexdigest())
        print('# %s: %d candidates, first %d taken' % (pattern, len(ranked), min(N, len(ranked))))
        for seed, idx, pre in ranked[:N]:
            u += 1
            print('u%03d %s %d %d %d %s' % (u, pattern, seed, idx, SALT, KEYS[pattern]))


if __name__ == '__main__':
    main()
