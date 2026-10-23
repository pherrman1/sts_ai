"""First decision where the two arms differ, per seed: python3 -I smoke_divergence.py SEED_DIR [SEED_DIR ...]"""
import gzip, json, os, sys

def load(path):
    decs, states = [], {}
    for x in gzip.open(path, 'rt').read().splitlines()[1:-1]:
        r = json.loads(x)
        if r.get('type') == 'state':
            states[r['index']] = r
        elif r.get('type') == 'decision':
            decs.append(r)
    return decs, states

def show(arm, d, states):
    root = d.get('root') or {}
    st = states.get(d.get('stateIndex'), {})
    hp = st.get('record', {}).get('obs.fixed_observation', [None])[0]
    c = sorted(root.get('candidates', []), key=lambda y: -y.get('visits', 0))[:4]
    cs = '; '.join(f"{y['key'].replace('ooc:v1:', '')} p={y['prior']:.2f} n={y.get('visits')} q={y.get('q', 0):.3f}" for y in c)
    print(f"  {arm}: act {d['act']} floor {d['floor']} hp {hp} screen {d.get('screen')} sims {root.get('completedSimulations')} "
          f"full {root.get('fullBudget')} -> {str(d.get('selectedKey')).replace('ooc:v1:', '')}\n     {cs}")

for sd in sys.argv[1:]:
    seed = os.path.basename(sd.rstrip('/'))
    A, sa = load(os.path.join(sd, f'A-{seed}.jsonl.gz'))
    C, sc = load(os.path.join(sd, f'C-{seed}.jsonl.gz'))
    i = next((k for k, (x, y) in enumerate(zip(A, C)) if x.get('selectedKey') != y.get('selectedKey')), None)
    print(seed, 'first different decision', i)
    if i is not None:
        show('A', A[i], sa)
        show('C', C[i], sc)
