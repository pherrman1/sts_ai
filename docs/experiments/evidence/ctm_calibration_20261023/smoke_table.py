"""SMOKE.md games table and banner check: python3 -I smoke_table.py OUT_DIR [OUT_DIR ...] (run_unit.sh output dirs)"""
import glob, gzip, json, os, re, sys
rows, banner_fail = [], []
NEED = [r'ooc-learned-stop: .*ooc_learned_stop_trees.txt', r'ctm-act4-survival\] model=', r'\[heart1\] loaded ',
        r'fast_root_cap=1024', r'leaf_calibration=-2.5384.*leaf_calibration_min_ascension=20']
CAL = r'\[ctm-calibration\] table=models/candidates/ctm_calibration_pathb_a20_v1.json sha256=359619f713677de60b86144e275ad37874718951c6964b63811f55c77181cb42 groups=34 scope=pathb-a20'
tot = {'A': [0, 0, 0, 0, 0], 'C': [0, 0, 0, 0, 0]}  # games, heart, act4, act2 deaths, wall
for out in sys.argv[1:]:
    for d in sorted(glob.glob(os.path.join(out, '1*/'))):
        seed = os.path.basename(d.rstrip('/'))
        g = {}
        for arm in 'AC':
            b = os.path.join(d, f'{arm}-{seed}')
            done = open(b + '.done').read()
            rc = re.search(r'rc=(-?\d+)', done).group(1)
            wall = int(re.search(r'wall=(\d+)', done).group(1))
            lines = gzip.open(b + '.jsonl.gz', 'rt').read().splitlines()
            foot = json.loads(lines[-1])
            keys = [json.loads(x).get('selectedKey') for x in lines[1:-1] if '"type":"decision"' in x]
            text = open(b + '.err').read() + open(b + '.log').read()
            ok = all(re.search(n, text) for n in NEED) and (bool(re.search(CAL, text)) == (arm == 'C')) and \
                (arm == 'C' or 'ctm-calibration]' not in text)
            if not ok:
                banner_fail.append(f'{arm}-{seed}')
            g[arm] = dict(rc=rc, wall=wall, foot=foot, keys=keys)
            t = tot[arm]
            t[0] += 1; t[1] += bool(foot['heartKilled']); t[2] += foot['finalAct'] >= 4
            t[3] += (not foot['heartKilled']) and foot['finalAct'] == 2; t[4] += wall
        first = next((i for i, (x, y) in enumerate(zip(g['A']['keys'], g['C']['keys'])) if x != y), None)
        order = 'A, C' if int(seed) % 2 == 0 else 'C, A'
        def cell(x):
            f = x['foot']
            res = 'Heart kill' if f['heartKilled'] else f"died act {f['finalAct']}, floor {f['finalFloor']}"
            return f"{res} | {x['rc']} | {x['wall']}"
        rows.append(f"| {seed} | {order} | {cell(g['A'])} | {cell(g['C'])} | {first} |")
print('| seed | order | A | rc | wall s | C | rc | wall s | first different decision |')
print('|---|---|---|---|---|---|---|---|---|')
print('\n'.join(rows))
print('banner failures:', banner_fail or 'none')
for arm, t in tot.items():
    print(arm, f'games {t[0]} heart {t[1]} act4 {t[2]} act2deaths {t[3]} meanwall {t[4] / max(t[0], 1):.0f}')
