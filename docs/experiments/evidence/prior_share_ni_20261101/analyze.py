#!/usr/bin/env python3
"""Prior-share non-inferiority analysis (README.md, pre-registered before any campaign tar was read).
Adapted from map_sims_sprt_20261101/analyze.py: arm A there = the 1,024 control R here, arm B there = arm C here.

usage: analyze.py CAMPAIGN_SHARE A_UNITS_DIR B_SHARE OUT_JSON
  CAMPAIGN_SHARE  /mnt/project-files/prior-share-ni  (units/<id>.wNN.tar from tools/cloud/worker.sh)
  A_UNITS_DIR     /mnt/project-files/value-chooser-ab/units  (§727 arm A records)
  B_SHARE         /mnt/project-files/map-sims-sprt  (§741 arm B records)
Control record R(s) = §741 B record where B was played, else §727 A record (divergence_ps90.json `source`).
"""
import gzip, hashlib, io, json, os, random, sys, tarfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sprt_gate  # tools/sprt_gate.py of main 520d4e4b (ADR-0064 + #971 tie-prefix fix), vendored

SHARE, AUNITS, BSHARE, OUT = sys.argv[1:5]
DIV = {int(k): v for k, v in json.load(open(os.path.join(HERE, 'divergence_ps90.json'))).items()}
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


def map_sims(rows, cap=None):
    # cap=1024 for R: a §727 A record searched 4,096, the 1,024 control the first 1,024 of them
    return sum(min(r['root'].get('completedSimulations', 0), cap or 1 << 62) for r in rows
               if r.get('type') == 'decision' and r.get('searched') and r.get('screen') == 5 and r.get('root'))


# control R: §741 B record where played, else §727 A record; checked against the frozen hashes in divergence_ps90.json
BT = {int(n.split('_')[0]): os.path.join(BSHARE, 'units', n) for n in os.listdir(os.path.join(BSHARE, 'units')) if n.endswith('.tar')}
A = {}
for n in sorted(os.listdir(AUNITS)):
    if not n.endswith('.tar'): continue
    s = int(n.split('.')[0])
    if DIV[s]['source'] == 'B741':
        with tarfile.open(BT[s]) as tf:
            m = [x for x in tf.getmembers() if x.name.endswith(f'/B-{s}.jsonl.gz')][0]
            raw = tf.extractfile(m).read()
            g = tf.extractfile(m.name.rsplit('/', 1)[0] + '/games.txt').read().decode()
            wall = [l for l in g.splitlines() if l.startswith(f'B-{s} ')]
    else:
        with tarfile.open(os.path.join(AUNITS, n)) as tf:
            raw = tf.extractfile(f'out/units/{s}/A-{s}.jsonl.gz').read()
            try: wall = [l for l in tf.extractfile(f'out/units/{s}/games.txt').read().decode().splitlines() if l.startswith(f'A-{s} ')]
            except KeyError: wall = []
    assert hashlib.sha256(raw).hexdigest() == DIV[s]['jsonlSha256'], f'control record of {s} changed'
    A[s] = dict(rows=rows_of(raw), wall=int(wall[-1].split('wall=')[1]) if wall else None)
assert sorted(A) == sorted(DIV) and len(A) == 1536

# arm C (this campaign)
B, problems = {}, []
# queue schedule (manifest `schedule queue`): one tar per unit in SHARE/units/<id>.wNN.tar; static schedule: SHARE/wNN.tar
TARS = [os.path.join(SHARE, n) for n in sorted(os.listdir(SHARE)) if n.startswith('w') and n.endswith('.tar')]
if os.path.isdir(os.path.join(SHARE, 'units')):
    TARS += [os.path.join(SHARE, 'units', n) for n in sorted(os.listdir(os.path.join(SHARE, 'units'))) if n.endswith('.tar')]
duplicates = []
for t in TARS:
    with tarfile.open(t) as tf:
        for m in tf.getmembers():
            p = m.name.split('/')
            if len(p) == 4 and p[3].startswith('C-') and p[3].endswith('.jsonl.gz') and '.ctm.' not in p[3]:
                s = int(p[2].split('_')[0])
                g = tf.extractfile(f'out/units/{p[2]}/games.txt').read().decode()
                wall = [l for l in g.splitlines() if l.startswith(f'C-{s} ')]
                if s in B:  # the scheduler can run a unit twice: keep the first tar in sorted order (verify_campaign)
                    duplicates.append((s, os.path.basename(t))); continue
                B[s] = dict(rows=rows_of(tf.extractfile(m).read()),
                            wall=int(wall[-1].split('wall=')[1]) if wall else None,
                            rc0=bool(wall) and ' rc=0 ' in wall[-1] + ' ')
missing = sorted(set(UNITS) - set(B))
# README "Failed units": a diverging unit whose 4th attempt failed with a game error (claims/<id>.a4/failed, rc not a
# run_unit configuration check) counts as a C loss (d = -kill_R); a sentinel or a configuration-check failure stays
# missing and makes the reuse INVALID.
CONFIG_RC = {'88', '89', '92', '93', '95'}
failed_as_loss = []
for s_ in list(missing):
    f = os.path.join(SHARE, 'claims', f'{s_}_{UNITS[s_]}.a4', 'failed')
    if UNITS[s_] == 'div' and os.path.isfile(f):
        rc = open(f).read().strip().split('rc=')[-1]
        if rc not in CONFIG_RC:
            failed_as_loss.append((s_, rc)); missing.remove(s_)

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
reuse_valid = (not missing and checks['sentinel_identical'] == checks['sentinel_total'] == 32
               and checks['div_prefix_ok'] == checks['div_pick_ok'] == checks['div_total'] == 49 - len(failed_as_loss))

# pairs over all 1,536 seeds in ascending order; seeds not played in B are A's own game (d = 0)
pairs = []
for s in sorted(A):
    oa = outcome(A[s]['rows'])
    ob = outcome(B[s]['rows']) if s in B else oa
    if s in dict(failed_as_loss): ob = dict(oa, kill=0)  # C loss on the primary; secondaries keep R's values
    pairs.append((s, oa, ob))
d = [ob['kill'] - oa['kill'] for _, oa, ob in pairs]
gate = sprt_gate.run(d, 'nonregression', look=64, cap=1536, alpha=0.05, beta=0.05)


def boot(vals, n=10000, seed=942):
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
    sec[key] = dict(R=sum(oa[key] for _, oa, _ in pairs) / 1536, C=sum(ob[key] for _, _, ob in pairs) / 1536,
                    diff=sum(dd) / 1536, ci=boot(dd))
for act in (1, 2, 3, 4):
    dd = [int(ob['death_act'] == act) - int(oa['death_act'] == act) for _, oa, ob in pairs]
    sec[f'death_act{act}'] = dict(diff=sum(dd) / 1536, ci=boot(dd))
played = [s for s in sorted(B) if UNITS[s] == 'div']
cpu = dict(div_units=len(played),
           mean_wall_R=sum(A[s]['wall'] for s in played if A[s]['wall']) / max(1, len(played)),
           mean_wall_C=sum(B[s]['wall'] for s in played if B[s]['wall']) / max(1, len(played)),
           map_sims_per_game_R=sum(map_sims(A[s]['rows'], 1024) for s in played) / max(1, len(played)),
           map_sims_per_game_C=sum(map_sims(B[s]['rows']) for s in played) / max(1, len(played)))
divp = [(oa, ob) for s_, oa, ob in pairs if UNITS.get(s_) == 'div']
dk = [ob['kill'] - oa['kill'] for oa, ob in divp]
sec['diverging_seeds_kill'] = dict(n=len(divp), R=sum(oa['kill'] for oa, _ in divp), C=sum(ob['kill'] for _, ob in divp),
                                   diff=sum(dk) / max(1, len(dk)), ci=boot(dk) if dk else None)
res = dict(reuse_valid=reuse_valid, missing=missing, failed_as_loss=failed_as_loss, duplicates=duplicates, checks=checks, pairs=len(d), diverging_pairs=len(played),
           kill_R=sum(oa['kill'] for _, oa, _ in pairs) / 1536, kill_C=sum(ob['kill'] for _, _, ob in pairs) / 1536,
           mean_d=mean, ci95=ci, sprt=gate, fixed_sample_reading=fixed,
           verdict=('INVALID' if not reuse_valid else (gate['verdict'] if gate['verdict'] != 'CAP' else f'CAP:{fixed}')),
           secondaries=sec, cpu=cpu)
json.dump(res, open(OUT, 'w'), indent=1, default=str)
print(json.dumps({k: v for k, v in res.items() if k not in ('sprt',)}, indent=1, default=str)[:4000])
print('sprt', gate['verdict'], gate['n_stop'], round(gate['llr'], 3))
