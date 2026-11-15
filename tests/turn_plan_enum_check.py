"""ctest turn_plan_enum: `one_combat turnplanenum` (#1058, research only) on four recorded G16 roots.

Checks: no row errors; every root action maps to a recorded edge; an uncapped set covers every root action with at
least one plan and every plan starts from at least one root action; the first fixture row stays uncapped and the
last one (more than 512 plans) is capped; two runs give identical plans (enumeration is deterministic).
"""
import json, os, subprocess, sys, tempfile

binary = sys.argv[1]
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
fixture = os.path.join(root, 'tests', 'fixtures', 'turn_plan_rows.jsonl')
env = dict(os.environ, STS_SILVER_ROOT_PRIOR='models/combat_policy_mlp_g7f_E.txt', STS_SILVER_ROOT_PRIOR_WEIGHT='400')


def run(path):
    with open(fixture) as f:
        subprocess.run([binary, 'turnplanenum', path], stdin=f, cwd=root, env=env, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return [json.loads(l) for l in open(path)]


with tempfile.TemporaryDirectory() as d:
    a = run(os.path.join(d, 'a.jsonl'))
    b = run(os.path.join(d, 'b.jsonl'))
rows = [json.loads(l) for l in open(fixture)]
assert len(a) == len(rows) == 4, len(a)
for r, p, q in zip(rows, a, b):
    assert 'error' not in p, p.get('error')
    assert p['n'] == len(r['edges']) and all(t >= 0 for t in p['toRow']), (p['n'], p['toRow'])
    assert p['plans'] == q['plans'] and p['capped'] == q['capped'], 'non-deterministic enumeration'
    if p['capped']:
        assert p['plans'] == []
        continue
    covered = set()
    for plan in p['plans']:
        assert plan[0], 'plan without a first action'
        covered.update(plan[0])
        assert plan[1] in (0, 1, 2, 3)
    assert covered == set(range(p['n'])), (covered, p['n'])
assert not a[0]['capped'] and a[3]['capped'], [x['capped'] for x in a]
print('turn_plan_enum OK:', [len(x['plans']) for x in a])
