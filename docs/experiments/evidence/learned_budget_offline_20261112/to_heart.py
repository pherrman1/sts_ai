#!/usr/bin/env python3
"""Step B0 applied to step A: rewrite rows.json's per-copy HP losses into Heart-pp losses with the pooled currency
(cur.json 'pooled' exchange): death -> 100 * V_mean(act, room); won -> 100 * dV/dHP(act, room) * HP lost, where
Act 1-2 boss HP counts 25% (A20 heals 75% of missing HP at the next act; battles.csv hp_post already includes it).
usage: python3 -I to_heart.py rows.json cur.json out_rows.json"""
import json, sys
D = json.load(open(sys.argv[1])); C = json.load(open(sys.argv[2]))['pooled']['exchange']
RM = {'M': 'NORMAL', 'E': 'ELITE', 'B': 'BOSS'}
for r in D['rows']:
    x = C[f"A{r['act']} {RM[r['room']]}"]
    w = 0.25 if (r['room'] == 'B' and r['act'] < 3) else 1.0
    for k in list(r):
        if k.endswith('_copies'):
            r[k] = [100 * x['V_mean'] if l >= r['hp'] else w * x['dV_per_HP_pp'] * l for l in r[k]]
json.dump(D, open(sys.argv[3], 'w'))
