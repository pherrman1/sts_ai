"""Heart-entry states (CTM pre rows) of run 1's base game and its redrawn-future forks for the 60 entries of
heart_states.tar -> act4replay JSONL, one file each (SEED-bNN.jsonl: b00 = base, b01..b04 = forks 1-4).

  build_fork_states.py RUN1_UNITS_DIR META.json OUT_DIR
  RUN1_UNITS_DIR: out/units of the extracted run-1 tars (/mnt/project-files/value-clean-labels-run1/units/SEED_*.tar,
  *.ctm.jsonl.gz only). META.json: heart_states.tar's. fork_states.tar = the b01..b04 files + meta.json
  (cd OUT_DIR && tar cf fork_states.tar $(ls *-b0[1-4].jsonl) meta.json); b00 equals #923's p00 and is not rerun.
"""
import gzip, json, glob, os, re, sys
REPO = os.path.dirname(os.path.abspath(__file__)).split('/docs/')[0]
def names(header, var):
    t = open(os.path.join(REPO, header)).read()
    body = t.split(var + '[] = {' if var + '[] = {' in t else var + '[] {', 1)[1].split('}', 1)[0]
    return re.findall(r'"([^"]*)"', body)
CARDS = names('include/constants/Cards.h', 'cardNames'); RELICS = names('include/constants/Relics.h', 'relicEnumNames')
POTS = names('include/constants/Potions.h', 'potionEnumNames')
units, meta_path, out = sys.argv[1:4]; os.makedirs(out, exist_ok=True)
seeds = sorted({m['seed'] for m in json.load(open(meta_path))}); meta = []
def heart(path):
    rs = [json.loads(l) for l in gzip.open(path, 'rt')]
    h = [x for x in rs if x.get('roomClass') == 'BOSS' and x['act'] == 4]
    return h[-1] if h else None
for s in seeds:
    d = [x for x in glob.glob(os.path.join(units, f'{s}_*')) if os.path.isdir(x)][0]
    for k, f in [(0, f'base-{s}.ctm.jsonl.gz')] + [(i, f'fork-{s}-{i}.ctm.jsonl.gz') for i in range(1, 5)]:
        h = heart(os.path.join(d, f))
        if h is None:
            continue
        pre = h['transition']['pre']
        line = {'id': f"{s}-b{k:02d}", 'enc': 'THE_HEART', 'hp': pre['curHp'], 'maxHp': pre['maxHp'],
                'deck': [CARDS[x['id']] + ('+' if x['upgraded'] else '') for x in pre['deck']],
                'relics': [RELICS[x['id']] for x in pre['relics']], 'relicData': [x['data'] for x in pre['relics']],
                'potions': [POTS[x] for x in pre['potions'] if x > 1], 'potionCapacity': pre['potionCapacity'],
                'bottleIdxs': pre['bottleIdxs']}
        fn = f"{s}-b{k:02d}.jsonl"; open(os.path.join(out, fn), 'w').write(json.dumps(line) + '\n')
        meta.append(dict(file=fn, seed=s, fork=k, insituHeartWon=h['transition']['combatOutcome'] == 1))
json.dump(meta, open(os.path.join(out, 'meta.json'), 'w'))
print(len(meta), 'states;', sum(m['fork'] == 0 for m in meta), 'base;',
      'in-game Heart win base %.3f forks %.3f' % tuple(
          sum(m['insituHeartWon'] for m in meta if (m['fork'] == 0) == b) / max(1, sum((m['fork'] == 0) == b for m in meta))
          for b in (True, False)))
