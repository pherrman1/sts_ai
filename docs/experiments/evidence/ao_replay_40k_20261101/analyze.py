"""Awakened One replay (README.md): production (P) vs flat 40k (F) on the recorded §727 arm-A entries.
usage: analyze.py UNITS_DIR [--json OUT]   UNITS_DIR holds <seed>/{P,F}-<seed>.jsonl.gz and <seed>.done
Primary: per-fight death difference F - P over the three copies r = 0..2 (same battle seed in both arms per copy:
r = 0 the recorded seed, r = 1..2 the SEED_BASE redraws), mean over entries, entry bootstrap 4,000. Secondary: HP lost (entry HP - exit HP, death = entry HP), CPU per copy, identity
(P r = 0 reproduces the recorded fight), and the run-level translation dDeath x AO entries per run (5,543 / 15,363,
§740) x P(Heart kill | survived AO) (0.59, §740). Units with rc != 0 or any invalid / errored / missing replay are
excluded whole and listed."""
import sys, os, json, gzip, glob, argparse
import numpy as np
ap = argparse.ArgumentParser(); ap.add_argument('units'); ap.add_argument('--json'); a = ap.parse_args()
rows, excluded, ident = [], [], [0, 0]
for d in sorted(glob.glob(os.path.join(a.units, '*', ''))):
    seed = os.path.basename(d.rstrip('/'))
    done = os.path.join(d, seed + '.done')
    if not os.path.exists(done) or ' rc=0 ' not in open(done).read() + ' ':
        excluded.append((seed, open(done).read().strip() if os.path.exists(done) else 'no .done')); continue
    def rd(p):
        p2 = p if os.path.exists(p) else p + '.gz'
        op = gzip.open if p2.endswith('.gz') else open
        return [json.loads(l) for l in op(p2, 'rt') if l.strip()]
    src = {(r['sourceSeed'], r['fightIdx']): r for r in rd(os.path.join(d, f'rows-{seed}.jsonl'))}
    P = rd(os.path.join(d, f'P-{seed}.jsonl')); F = rd(os.path.join(d, f'F-{seed}.jsonl'))
    bad = [x for x in P + F if 'error' in x or not x.get('valid')]
    if bad: excluded.append((seed, 'invalid/error replay')); continue
    for k, s in src.items():
        hp0 = s['transition']['pre']['curHp']
        get = lambda L, r: next((x for x in L if (x['sourceSeed'], x['fightIdx']) == k and x['replicate'] == r), None)
        p0 = get(P, 0)
        ident[1] += 1; ident[0] += bool(p0 and p0.get('identity'))
        pr = [get(P, r) for r in (0, 1, 2)]; fr = [get(F, r) for r in (0, 1, 2)]
        if None in pr or None in fr: excluded.append((seed, 'missing replicate')); continue
        die = lambda x: x['combatOutcome'] == 2
        lost = lambda x: hp0 if die(x) else hp0 - x['post']['curHp']
        rows.append(dict(seed=seed, hp0=hp0, maxhp=s['transition']['pre']['maxHp'], rec_dead=s['transition']['combatOutcome'] == 2,
                         pd=np.mean([die(x) for x in pr]), fd=np.mean([die(x) for x in fr]),
                         pl=np.mean([lost(x) for x in pr]), fl=np.mean([lost(x) for x in fr]),
                         pcpu=np.mean([x['cpuSeconds'] for x in pr]), fcpu=np.mean([x['cpuSeconds'] for x in fr])))
n = len(rows)
rng = np.random.default_rng(740)
def boot(v, B=4000):
    v = np.asarray(v, float); idx = rng.integers(0, len(v), (B, len(v)))
    return [float(x) for x in np.percentile(v[idx].mean(1), [2.5, 97.5])]
dd = [r['fd'] - r['pd'] for r in rows]; dl = [r['fl'] - r['pl'] for r in rows]
res = dict(entries=n, excluded=excluded, identity=f'{ident[0]}/{ident[1]}',
           death_P=float(np.mean([r['pd'] for r in rows])), death_F=float(np.mean([r['fd'] for r in rows])),
           dDeath=float(np.mean(dd)), dDeath_ci=boot(dd), sd_pair=float(np.std(dd, ddof=1)),
           hpLost_P=float(np.mean([r['pl'] for r in rows])), hpLost_F=float(np.mean([r['fl'] for r in rows])),
           dHpLost=float(np.mean(dl)), dHpLost_ci=boot(dl),
           cpu_P=float(np.mean([r['pcpu'] for r in rows])), cpu_F=float(np.mean([r['fcpu'] for r in rows])),
           recorded_death=float(np.mean([r['rec_dead'] for r in rows])))
res['run_level_pp'] = res['dDeath'] * -1 * 5543 / 15363 * 0.59 * 100
lo, hi = res['dDeath_ci']
res['verdict'] = ('PLANNING_LIMITED' if res['dDeath'] <= -0.04 and hi < 0 else
                  'NOT_PLANNING_LIMITED' if lo > -0.04 else 'INCONCLUSIVE')
print(json.dumps(res, indent=1))
if a.json: json.dump(res, open(a.json, 'w'), indent=1)
