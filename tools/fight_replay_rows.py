"""Build `one_combat fightreplay` input rows from heartoutcomegen campaign units.

Each heartoutcomegen unit writes ARM-SEED.jsonl (trajectory: one "state" row per real-driver boundary, BATTLE
screens included) and ARM-SEED.ctm.jsonl (one combat_transition_row_v2 row per real fight, in the same order).
The k-th BATTLE state row (screen 9) belongs to fight k. This adds to each fight row the "replayContext" the
transition rows do not carry: keys held (obs.fixed_observation[7:10] = ruby, emerald, sapphire), the map node
(obs.mapX, obs.mapY) and the second Act-3 boss (the encounter of the run's second Act-3 boss fight on that
fight itself, -1 otherwise). Event fights (room class OTHER) are left out.

Usage: python3 -I tools/fight_replay_rows.py OUT.jsonl UNIT.tar [UNIT.tar ...] [--arm A] [--rooms BOSS,ELITE,...]
"""
import argparse
import gzip
import json
import os
import tarfile

BATTLE = 9


def unit_rows(path, arm_filter):
    with tarfile.open(path) as tf:
        members = {os.path.basename(m.name): m for m in tf.getmembers() if m.isfile()}
        for name in sorted(members):
            if not name.endswith('.ctm.jsonl.gz'):
                continue
            tag = name[:-len('.ctm.jsonl.gz')]
            arm = tag.rsplit('-', 1)[0]
            if arm_filter and arm not in arm_filter:
                continue
            fights = [json.loads(l) for l in gzip.decompress(tf.extractfile(members[name]).read()).splitlines() if l]
            states = [json.loads(l) for l in
                      gzip.decompress(tf.extractfile(members[tag + '.jsonl.gz']).read()).splitlines() if l]
            battles = [s for s in states if s.get('type') == 'state' and s.get('screen') == BATTLE]
            if len(battles) != len(fights):
                raise SystemExit(f'{path}:{tag}: {len(battles)} BATTLE states for {len(fights)} fights')
            act3_bosses = 0
            for f, s in zip(fights, battles):
                if (s['act'], s['floor']) != (f['act'], f['floor']):
                    raise SystemExit(f'{path}:{tag}: fight {f["fightIdx"]} state/fight floor mismatch')
                second = -1
                if f['act'] == 3 and f['roomClass'] == 'BOSS':
                    act3_bosses += 1
                    if act3_bosses == 2:
                        second = f['encounter']
                rec = s['record']
                f['replayContext'] = {'arm': arm, 'keys': rec['obs.fixed_observation'][7:10],
                                      'mapX': rec['obs.mapX'], 'mapY': rec['obs.mapY'], 'secondBoss': second}
                yield f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('units', nargs='+')
    ap.add_argument('--arm', action='append', default=[])
    ap.add_argument('--rooms', default='')
    a = ap.parse_args()
    rooms = set(a.rooms.split(',')) if a.rooms else None
    if os.path.exists(a.out):
        raise SystemExit(f'refusing to overwrite {a.out}')
    n = 0
    with open(a.out, 'w') as out:
        for u in a.units:
            for f in unit_rows(u, set(a.arm)):
                if f['roomClass'] == 'OTHER' or (rooms and f['roomClass'] not in rooms):
                    continue
                out.write(json.dumps(f) + '\n')
                n += 1
    print(f'fight_replay_rows: {n} rows -> {a.out}')


if __name__ == '__main__':
    main()
