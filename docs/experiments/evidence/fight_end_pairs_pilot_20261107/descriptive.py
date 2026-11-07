#!/usr/bin/env python3
"""RESULT.md tables from analyze.py's JSON, plus descriptive extras from the tars (not pre-registered).
usage: descriptive.py results/analysis.json UNITS_DIR results/descriptive.json
Prints the RESULT tables as Markdown. Extras: per-potion-type HP prices with a source-seed bootstrap CI (2,000
resamples, seed 20261107, beta fixed at its point estimate), the source-run CPU total and the weights by act. Same unit
filter and weights (eligible / sampled, deviation 1) as analyze.py."""
import collections, gzip, io, json, os, re, sys, tarfile
import numpy as np

res = json.load(open(sys.argv[1])); UNITS = sys.argv[2]; OUT = sys.argv[3]
FAM = ['hp:-3', 'hp:-8', 'hp:-15', 'pot', 'maxhp:-5', 'gold:-50']
NAME = {'hp:-3': '−3 HP', 'hp:-8': '−8 HP', 'hp:-15': '−15 HP', 'pot': 'potion', 'maxhp:-5': '−5 max HP',
        'gold:-50': '−50 gold'}


def f(x, nd=2):
    return f'{x:+.{nd}f}'.replace('-', '−')


def ci(c, nd=2):
    return f'[{f(c[0], nd)}, {f(c[1], nd)}]'


u = res['unweighted']
print('### Decision\n')
print('| | weighted (primary, deviation 1) | unweighted (frozen) |\n| --- | --- | --- |')
for lab, key in (('S: −15 HP, acts 1-4, Δ pp [95%]', 'all|hp:-15'), ('S: potion, acts 1-4', 'all|pot'),
                 ('S: −5 max HP, acts 1-4', 'all|maxhp:-5')):
    w, x = res['cells'][key], u['cells'][key]
    print(f"| {lab} | {f(w['delta_pp'])} {ci(w['ci_pp'])} | {f(x['delta_pp'])} {ci(x['ci_pp'])} |")
print(f"| sign check S | {'pass' if res['sign_check_pass'] else 'fail'} | {'pass' if u['sign_check_pass'] else 'fail'} |")
print(f"| β, pp per HP [95%] | {f(res['beta_pp_per_hp'], 3)} {ci(res['beta_ci'], 3)} | {f(u['beta_pp_per_hp'], 3)} {ci(u['beta_ci'], 3)} |")
pc = res['projection_ci']
print(f"| cost*, core-h [95%] | {res['projection_core_h']:,.0f} [{pc[0]:,.0f}, {pc[1]:,.0f}] | ∞ (β ≤ 0) |"
      if not np.isfinite(u['projection_core_h']) else '| cost* | ? | ? |')
print(f"| price check P | {'pass' if res['price_check_pass'] else 'fail'} | {'pass' if u['price_check_pass'] else 'fail'} |")
print(f"| **decision** | **{res['decision']}** | **{u['decision']}** |")
zw, zu = res['hp8_z_by_act'], u['hp8_z_by_act']
print(f"| 8-HP z, acts 1 / 2 / 3 | {' / '.join(f'{zw[a]:.1f}' for a in ('1', '2', '3'))} | "
      f"{' / '.join(f'{zu[a]:.1f}' for a in ('1', '2', '3'))} |")
print(f"| base Heart kill | {100 * res['base_heart_rate']:.2f}% | {100 * u['base_heart_rate']:.2f}% |")

print('\n### Weighted cells (Heart kill, pp)\n')
print('| act | family | pairs | n_eff | Δ [95%] | f | ρ | unweighted Δ |\n| --- | --- | --- | --- | --- | --- | --- | --- |')
for a in ('1', '2', '3', '4', 'all'):
    for fam in FAM:
        c, x = res['cells'][f'{a}|{fam}'], u['cells'][f'{a}|{fam}']
        print(f"| {a.replace('all', '1-4')} | {NAME[fam]} | {c['pairs']:,} | {c['n_eff']:,.0f} | {f(c['delta_pp'])} {ci(c['ci_pp'])} | "
              f"{c['discordance']:.3f} | {c['rho']:.2f} | {f(x['delta_pp'])} |")

print('\n### Weighted final floor (floors)\n')
print('| family | act 1 | act 2 | act 3 | acts 1-4 |\n| --- | --- | --- | --- | --- |')
for fam in FAM:
    print(f"| {NAME[fam]} | " + ' | '.join(f"{f(res['cells'][f'{a}|{fam}']['floor_delta'])}" for a in ('1', '2', '3', 'all')) + ' |')

print('\n### Weighted Heart kill of the base copy by act\n')
print(' / '.join(f"act {a}: {100 * res['cells'][f'{a}|hp:-3']['heart_base']:.1f}%" for a in ('1', '2', '3', '4')))

p = res['prices']
print(f"\nprices: potion {p['potion_hp']:.1f} HP, max HP {p['maxhp_hp_per_point']:.2f} HP/point, gold {p['gold_hp_per_gold']:.3f} HP/gold")

print('\n### Room cells (weighted Δ pp, pairs)\n')
rooms = res['room_cells_pp']
print('| act | room | ' + ' | '.join(NAME[x] for x in FAM) + ' |\n| --- | --- |' + ' --- |' * len(FAM))
for a in ('1', '2', '3', '4'):
    for room in ('NORMAL', 'ELITE', 'BOSS'):
        cells = [rooms.get(f'{a}|{room}|{fam}') for fam in FAM]
        if not any(cells):
            continue
        print(f'| {a} | {room} | ' + ' | '.join(f"{f(c[1])} ({c[0]:,})" if c else '–' for c in cells) + ' |')

# ---- descriptive extras from the tars (same unit filter as analyze.py: first tar per id, rc 0, 8 source rows)
units = {}
for name in sorted(os.listdir(UNITS)):
    m = re.fullmatch(r'(\d+)\.w\d+\.tar', name)
    if not m or m.group(1) in units:
        continue
    with tarfile.open(os.path.join(UNITS, name)) as t:
        files = {x.name: x for x in t.getmembers() if x.isfile()}
        res_t = [n for n in files if n.endswith(f'/{m.group(1)}/result.txt')]
        jl = [n for n in files if n.endswith('.jsonl.gz') and f'/{m.group(1)}/' in n]
        if len(res_t) != 1 or len(jl) != 1:
            continue
        rc = re.search(r'rc=(\d+)', t.extractfile(files[res_t[0]]).read().decode())
        if not rc or rc.group(1) != '0':
            continue
        rows = [json.loads(l) for l in gzip.open(io.BytesIO(t.extractfile(files[jl[0]]).read()), 'rt')]
    if sum(r['kind'] == 'source' for r in rows) == 8:
        units[m.group(1)] = rows
src = [r for rows in units.values() for r in rows if r['kind'] == 'source']
w = {r['seed']: r['eligible'] / r['sampled'] for r in src if r.get('sampled')}
forks = collections.defaultdict(dict)
for rows in units.values():
    for r in rows:
        if r['kind'] == 'copy':
            forks[(r['seed'], r['fork'])][r['variant']] = r
seeds = sorted({r['seed'] for r in src}); six = {s: i for i, s in enumerate(seeds)}
pot = collections.defaultdict(lambda: [np.zeros(len(seeds)), np.zeros(len(seeds)), 0])
wact = collections.defaultdict(list)
for (seed, fk), vs in forks.items():
    b = vs.get('base')
    if not b or not b['outcome']['valid']:
        continue
    wact[b['act']].append(w[seed])
    for v, r in vs.items():
        if v.startswith('pot:') and r['outcome']['valid']:
            d = float(r['outcome']['heartKill']) - float(b['outcome']['heartKill'])
            e = pot[v[4:]]; e[0][six[seed]] += w[seed] * d; e[1][six[seed]] += w[seed]; e[2] += 1
rng = np.random.default_rng(20261107)
Wb = rng.multinomial(len(seeds), np.full(len(seeds), 1.0 / len(seeds)), size=2000).astype(float)
beta = res['beta_pp_per_hp'] / 100
ptab = {}
for name, (num, den, n) in sorted(pot.items(), key=lambda kv: -kv[1][2]):
    if n < 200:
        continue
    pt = num.sum() / den.sum(); bs = (Wb @ num) / np.where(Wb @ den > 0, Wb @ den, np.nan)
    lo, hi = np.nanpercentile(bs, [2.5, 97.5])
    ptab[name] = {'pairs': n, 'delta_pp': 100 * pt, 'ci_pp': [100 * lo, 100 * hi], 'hp': -pt / beta,
                  'hp_ci': [-hi / beta, -lo / beta]}
nf = [sum(e[0] for k, e in pot.items() if k != 'FAIRY_POTION'), sum(e[1] for k, e in pot.items() if k != 'FAIRY_POTION'),
      sum(e[2] for k, e in pot.items() if k != 'FAIRY_POTION')]
pt = nf[0].sum() / nf[1].sum(); bs = (Wb @ nf[0]) / np.where(Wb @ nf[1] > 0, Wb @ nf[1], np.nan)
lo, hi = np.nanpercentile(bs, [2.5, 97.5])
no_fairy = {'pairs': nf[2], 'delta_pp': 100 * pt, 'ci_pp': [100 * lo, 100 * hi], 'hp': -pt / beta,
            'hp_ci': [-hi / beta, -lo / beta]}
print(f"\npotion without Fairy: {nf[2]:,} pairs, Δ {f(100 * pt)} [{f(100 * lo)}, {f(100 * hi)}] pp, "
      f"{-pt / beta:.1f} HP [{-hi / beta:.1f}, {-lo / beta:.1f}]")
print('\n### Potion types (descriptive, n ≥ 200; HP = −Δ / β; seed bootstrap)\n')
print('| potion | pairs | Δ pp [95%] | HP [95%] |\n| --- | --- | --- | --- |')
for name, e in sorted(ptab.items(), key=lambda kv: -kv[1]['hp']):
    g = (lambda x: f'{x:.1f}'.replace('-', '−'))
    print(f"| {name} | {e['pairs']:,} | {f(e['delta_pp'])} {ci(e['ci_pp'])} | {g(e['hp'])} [{g(e['hp_ci'][0])}, {g(e['hp_ci'][1])}] |")
src_core_h = sum(r['cost']['cpuMs'] for r in src) / 3.6e6
print(f"\nsource runs: {len(src):,}, CPU {src_core_h:.1f} core-h ({src_core_h * 3600 / len(src):.1f} s/run); continuations "
      f"{res['core_h_played']:.1f} core-h; total {src_core_h + res['core_h_played']:.1f} core-h")
print('weights by act (mean, max):', {a: (round(float(np.mean(v)), 2), round(float(np.max(v)), 2), len(v)) for a, v in sorted(wact.items())})
json.dump({'potion_types': ptab, 'potion_without_fairy': no_fairy, 'source_core_h': src_core_h, 'source_s_per_run': src_core_h * 3600 / len(src),
           'weights_by_act': {a: {'mean': float(np.mean(v)), 'max': float(np.max(v)), 'forks': len(v)}
                              for a, v in sorted(wact.items())}}, open(OUT, 'w'), indent=1)
