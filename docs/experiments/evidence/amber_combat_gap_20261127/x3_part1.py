#!/usr/bin/env python3
"""X3 part 1 (WORKPLAN-2, AGREED-2 item B): do the value heads steer the first decision of a fight?

usage: python3 -I x3_part1.py <probe.jsonl> [out.json]

Input: selfplay.py --probe-states on the dumped Baalorlord fight starts (copy 0), ckpt_1828683, the fixed-seed
bench's input options; every legal first action got one simulation, so a deterministic action's recorded leaf is
the net's evaluation of its child state s_a. Per root, actions kept: not END_TURN, not a chance edge, visited once.
F = E[final floor] / 57 (outcome head; a win counts 57), H = amberH(floor, hpf) (az_run_driver.h), U = (F + 0.5 H)
/ 1.5. Roots with >= 2 kept actions. Within-root slope of U on enemy HP removed (and on block gained): pooled
within-root (demeaned) OLS; 95% interval by bootstrap over fights (10,000, seed 20261128).
Rule (fixed): Part 2 slope clearly positive AND argmax_a(F + 0.5 H) != argmax_a(F) at < 5 % of roots AND the slope
of U on enemy HP removed not distinguishable from 0 -> utility property (volume is the remedy); Part 2 slope not
positive -> look at the HP head's learning; else undecided.
"""
import json, random, statistics as st, sys

FLOORS = 56


def amber_h(floor, hpf):
    fl = min(max(floor, 1), FLOORS)
    return ((fl - 1) + sum(min(max(x, 0.0), 1.0) for x in hpf[fl - 1:])) / FLOORS


def ef(dist):
    return sum(p * (57 if c == 0 else c) for c, p in enumerate(dist)) / 57.0


def is_end_turn(bits):
    # search::Action::getActionType: (bits >> 29) & 0xF, END_TURN = 4
    return ((bits >> 29) & 0xF) == 4


roots = []
excl = dict(not_searched=0, moved_before=0, lt2=0)
for line in open(sys.argv[1]):
    r = json.loads(line)
    if r['status'] != 'searched':
        excl['not_searched'] += 1
        continue
    if r['combat_moves'] != 0:
        excl['moved_before'] += 1
        continue
    acts = []
    for i, b in enumerate(r['bits']):
        if r['n'][i] != 1 or r['chance'][i] or is_end_turn(b) or r['hpf'] is None:
            continue
        F = ef(r['dist'][i])
        H = amber_h(r['floor_g'], r['hpf'][i])
        acts.append(dict(F=F, H=H, U=(F + 0.5 * H) / 1.5, ehr=r['enemy_hp_removed'][i], blk=r['block_gained'][i]))
    if len(acts) < 2:
        excl['lt2'] += 1
        continue
    roots.append(dict(key=(r['file'], r['floor']), act=r['act'], acts=acts))


def q(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(p * len(v)))]


rh = [max(a['H'] for a in x['acts']) * 0.5 - min(a['H'] for a in x['acts']) * 0.5 for x in roots]
rf = [max(a['F'] for a in x['acts']) - min(a['F'] for a in x['acts']) for x in roots]
ratio = [h / f for h, f in zip(rh, rf) if f > 0]
diff = sum(max(range(len(x['acts'])), key=lambda i: x['acts'][i]['F'] + 0.5 * x['acts'][i]['H'])
           != max(range(len(x['acts'])), key=lambda i: x['acts'][i]['F']) for x in roots)


def slope(rs, key):
    sxy = sxx = 0.0
    for x in rs:
        mu = st.mean(a['U'] for a in x['acts'])
        mx = st.mean(a[key] for a in x['acts'])
        for a in x['acts']:
            sxy += (a[key] - mx) * (a['U'] - mu)
            sxx += (a[key] - mx) ** 2
    return sxy / sxx if sxx > 0 else float('nan')


def boot(key, reps=10000):
    rng = random.Random(20261128)
    v = sorted(slope([rng.choice(roots) for _ in roots], key) for _ in range(reps))
    return [v[int(0.025 * reps)], v[int(0.975 * reps) - 1]]


res = dict(roots=len(roots), actions=sum(len(x['acts']) for x in roots), excluded=excl,
           range_half_H=dict(median=st.median(rh), p10=q(rh, .1), p90=q(rh, .9)),
           range_F=dict(median=st.median(rf), p10=q(rf, .1), p90=q(rf, .9)),
           ratio_half_H_over_F=dict(median=st.median(ratio), p10=q(ratio, .1), p90=q(ratio, .9), n=len(ratio)),
           argmax_differs_share=diff / len(roots),
           slope_U_per_enemy_hp=slope(roots, 'ehr'), slope_U_per_enemy_hp_ci=boot('ehr'),
           slope_U_per_block=slope(roots, 'blk'), slope_U_per_block_ci=boot('blk'))
s = json.dumps(res, indent=1)
print(s)
if len(sys.argv) > 2:
    open(sys.argv[2], 'w').write(s + '\n')
