#!/usr/bin/env python3
"""compare.py DIR_A DIR_B SEED: play identity between two bestbench units, timing fields removed."""
import csv, json, re, sys
from pathlib import Path
A, B, seed = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
base = f'S-a20-{seed}'
TIME = re.compile(r'(sec|Sec|seconds|wall|Wall|cpu_|Cpu|elapsed)', re.I)
ok = True
def report(name, same):
    global ok
    ok &= same
    print(f'  {name}: {"identical" if same else "DIFFERENT"}')
def csv_rows(p):
    with open(p) as f:
        rows = list(csv.reader(f))
    keep = [i for i, h in enumerate(rows[0]) if not TIME.search(h)]
    return [[r[i] for i in keep] for r in rows]
def strip(o):
    if isinstance(o, dict): return {k: strip(v) for k, v in o.items() if not TIME.search(k)}
    if isinstance(o, list): return [strip(v) for v in o]
    return o
print(base)
for suf in ('.csv', '.mcts.csv'):
    report(suf, csv_rows(A / (base + suf)) == csv_rows(B / (base + suf)))
for suf in ('.mcts.csv.actions.jsonl', '.mcts.csv.support.jsonl', '.decisions.json'):
    pa, pb = A / (base + suf), B / (base + suf)
    if pa.exists() or pb.exists(): report(suf, pa.exists() and pb.exists() and pa.read_bytes() == pb.read_bytes())
ra = [strip(json.loads(l)) for l in open(A / (base + '.runprof.jsonl'))]
rb = [strip(json.loads(l)) for l in open(B / (base + '.runprof.jsonl'))]
report(f'.runprof.jsonl ({len(ra)} rows, timing keys dropped)', ra == rb)
norm = lambda l: re.sub(r'/scratchpad/[a-z0-9]+/', '/scratchpad/BIN/', l)
la = [norm(l) for l in open(A / (base + '.log')) if not TIME.search(l)]
lb = [norm(l) for l in open(B / (base + '.log')) if not TIME.search(l)]
report(f'.log ({len(la)} non-timing lines)', la == lb)
print('PLAY IDENTICAL' if ok else 'MISMATCH')
sys.exit(0 if ok else 1)
