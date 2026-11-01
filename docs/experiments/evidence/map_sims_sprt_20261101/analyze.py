#!/usr/bin/env python3
"""Map-simulations SPRT analysis (README.md, pre-registered before any campaign tar was read).

usage: analyze.py CAMPAIGN_SHARE A_UNITS_DIR OUT_JSON
  CAMPAIGN_SHARE  /mnt/project-files/map-sims-sprt   (wNN.tar from tools/cloud/worker.sh)
  A_UNITS_DIR     /mnt/project-files/value-chooser-ab/units  (§727 unit tars; arm A records are reused)
"""
import gzip, hashlib, io, json, os, random, sys, tarfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sprt_gate  # vendored from claude/project-thread-bdusqi 7b62e61a (README.md)

SHARE, AUNITS, OUT = sys.argv[1:4]
DIV = {int(k): v for k, v in json.load(open(os.path.join(HERE, 'divergence_727A.json'))).items()}
UNITS = {}
for line in open(os.path.join(HERE, 'units.txt')):
    if line.strip() and not line.startswith('#'):
        s, k = line.split(); UNITS[int(s)] = k


def rows_of(raw):
    return [json.loads(l) for l in gzip.decompress(raw).decode().splitlines() if l.strip()]


def play_key(r):
    """What a row says about play (not about search statistics or paths)."""
    if r.get('type') == 'state':
        return ('state', r.get('index'), r.get('act'), r.get('floor'), r.get('screen'),
                json.dumps(r.get('record'), sort_keys=True))
    if r.get('type') == 'decision':
        return ('decision', r.get('decisionIndex'), r.get('stateIndex'), r.get('by'), r.get('selectedKey'),
                r.get('executed'))
    if r.get('type') == 'outcome':
        return ('outcome', r.get('complete'), r.get('heartKilled'), r.get('finalAct'), r.get('finalFloor'),
                r.get('finalHp'), r.get('decisions'), r.get('states'))
    return None


def outcome(rows):
    o = [r for r in rows if r.get('type') == 'outcome'][0]
    f = o.get('finalFloor', 0)
    return dict(complete=bool(o.get('complete')), kill=int(bool(o.get('heartKilled'))), act4=int(o.get('finalAct', 0) >= 4),
                heart=int(f >= 56), floor=f, death_act=None if o.get('heartKilled') else o.get('finalAct'))


def map_sims(rows):
    return sum(r['root'].get('completedSimulations', 0) for r in rows
               if r.get('type') == 'decision' and r.get('searched') and r.get('screen') == 5 and r.get('root'))


# arm A (§727), checked against the frozen hashes in divergence_727A.json
A = {}
for n in sorted(os.listdir(AUNITS)):
    if not n.endswith('.tar'): continue
    s = int(n.split('.')[0])
    with tarfile.open(os.path.join(AUNITS, n)) as tf:
        raw = tf.extractfile(f'out/units/{s}/A-{s}.jsonl.gz').read()
        try: wall = [l for l in tf.extractfile(f'out/units/{s}/games.txt').read().decode().splitlines() if l.startswith(f'A-{s} ')]
        except KeyError: wall = []
    assert hashlib.sha256(raw).hexdigest() == DIV[s]['jsonlSha256'], f'arm A record of {s} changed'
    A[s] = dict(rows=rows_of(raw), wall=int(wall[0].split('wall=')[1]) if wall else None)
assert sorted(A) == sorted(DIV) and len(A) == 1536

# arm B (this campaign)
B, problems = {}, []
for n in sorted(os.listdir(SHARE)):
    if not (n.startswith('w') and n.endswith('.tar')): continue
    with tarfile.open(os.path.join(SHARE, n)) as tf:
        for m in tf.getmembers():
            p = m.name.split('/')
            if len(p) == 4 and p[3].startswith('B-') and p[3].endswith('.jsonl.gz') and '.ctm.' not in p[3]:
                s = int(p[2].split('_')[0])
                g = tf.extractfile(f'out/units/{p[2]}/games.txt').read().decode()
                wall = [l for l in g.splitlines() if l.startswith(f'B-{s} ')]
                B[s] = dict(rows=rows_of(tf.extractfile(m).read()),
                            wall=int(wall[-1].split('wall=')[1]) if wall else None,
                            rc0=bool(wall) and ' rc=0 ' in wall[-1] + ' ')
missing = sorted(set(UNITS) - set(B))

# reuse validity (README "Control reuse"): sentinels identical, diverging units identical up to the predicted root
checks = dict(sentinel_identical=0, sentinel_total=0, div_prefix_ok=0, div_pick_ok=0, div_total=0, failures=[])
for s, kind in sorted(UNITS.items()):
    if s not in B: continue
    a = [k for k in map(play_key, A[s]['rows']) if k]
    b = [k for k in map(play_key, B[s]['rows']) if k]
    if not outcome(B[s]['rows'])['complete'] or not B[s]['rc0']:
        checks['failures'].append((s, kind, 'incomplete')); continue
    if kind == 'sent':
        checks['sentinel_total'] += 1
        if a == b: checks['sentinel_identical'] += 1
        else: checks['failures'].append((s, kind, 'sentinel_differs'))
    else:
        checks['div_total'] += 1
        idx = DIV[s]['decisionIndex']
        def prefix(rows):
            out = []
            for r in rows:
                if r.get('type') == 'decision' and r.get('decisionIndex') == idx: return out, r
                k = play_key(r)
                if k and k[0] != 'outcome': out.append(k)
            return out, None
        pa, ra = prefix(A[s]['rows']); pb, rb = prefix(B[s]['rows'])
        if pa == pb and rb is not None:
            checks['div_prefix_ok'] += 1
            if rb.get('selectedKey') == DIV[s]['predictedKey']: checks['div_pick_ok'] += 1
            else: checks['failures'].append((s, kind, 'pick_differs'))
        else: checks['failures'].append((s, kind, 'prefix_differs'))
reuse_valid = (not missing and checks['sentinel_identical'] == checks['sentinel_total'] == 64
               and checks['div_prefix_ok'] == checks['div_pick_ok'] == checks['div_total'] == 652)

# pairs over all 1,536 seeds in ascending order; seeds not played in B are A's own game (d = 0)
pairs = []
for s in sorted(A):
    oa = outcome(A[s]['rows'])
    ob = outcome(B[s]['rows']) if s in B else oa
    pairs.append((s, oa, ob))
d = [ob['kill'] - oa['kill'] for _, oa, ob in pairs]
gate = sprt_gate.run(d, 'nonregression', look=64, cap=1536, alpha=0.05, beta=0.05)


def boot(vals, n=10000, seed=737):
    rng = random.Random(seed); m = len(vals)
    ms = sorted(sum(vals[rng.randrange(m)] for _ in range(m)) / m for _ in range(n))
    return [ms[int(0.025 * n)], ms[int(0.975 * n) - 1]]


mean = sum(d) / len(d); ci = boot(d)
if gate['verdict'] == 'CAP':
    fixed = 'NOT_WORSE' if ci[0] > -0.015 else ('WORSE' if ci[1] < 0 else 'INCONCLUSIVE')
else:
    fixed = None
sec = {}
for key in ('act4', 'heart', 'floor'):
    dd = [ob[key] - oa[key] for _, oa, ob in pairs]
    sec[key] = dict(A=sum(oa[key] for _, oa, _ in pairs) / 1536, B=sum(ob[key] for _, _, ob in pairs) / 1536,
                    diff=sum(dd) / 1536, ci=boot(dd))
for act in (1, 2, 3, 4):
    dd = [int(ob['death_act'] == act) - int(oa['death_act'] == act) for _, oa, ob in pairs]
    sec[f'death_act{act}'] = dict(diff=sum(dd) / 1536, ci=boot(dd))
played = [s for s in sorted(B) if UNITS[s] == 'div']
cpu = dict(div_units=len(played),
           mean_wall_A=sum(A[s]['wall'] for s in played if A[s]['wall']) / max(1, len(played)),
           mean_wall_B=sum(B[s]['wall'] for s in played if B[s]['wall']) / max(1, len(played)),
           map_sims_per_game_A=sum(map_sims(A[s]['rows']) for s in played) / max(1, len(played)),
           map_sims_per_game_B=sum(map_sims(B[s]['rows']) for s in played) / max(1, len(played)))
res = dict(reuse_valid=reuse_valid, missing=missing, checks=checks, pairs=len(d), diverging_pairs=len(played),
           kill_A=sum(oa['kill'] for _, oa, _ in pairs) / 1536, kill_B=sum(ob['kill'] for _, _, ob in pairs) / 1536,
           mean_d=mean, ci95=ci, sprt=gate, fixed_sample_reading=fixed,
           verdict=('INVALID' if not reuse_valid else (gate['verdict'] if gate['verdict'] != 'CAP' else f'CAP:{fixed}')),
           secondaries=sec, cpu=cpu)
json.dump(res, open(OUT, 'w'), indent=1, default=str)
print(json.dumps({k: v for k, v in res.items() if k not in ('sprt',)}, indent=1, default=str)[:4000])
print('sprt', gate['verdict'], gate['n_stop'], round(gate['llr'], 3))
