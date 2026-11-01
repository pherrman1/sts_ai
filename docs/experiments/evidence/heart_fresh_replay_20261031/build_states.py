"""Heart-entry states (CTM pre rows) of control + 3 random children per pilot entry -> act4replay JSONL, one file each."""
import gzip, json, glob, os, re, random, sys
REPO = '/home/user/sts_ai'
def names(header, var):
    t = open(os.path.join(REPO, header)).read()
    body = t.split(var + '[] = {' if var + '[] = {' in t else var + '[] {', 1)[1].split('}', 1)[0]
    return re.findall(r'"([^"]*)"', body)
CARDS = names('include/constants/Cards.h', 'cardNames'); RELICS = names('include/constants/Relics.h', 'relicEnumNames')
POTS = names('include/constants/Potions.h', 'potionEnumNames')
data_dir, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
rng = random.Random(20261031); meta = []
for p in sorted(glob.glob(os.path.join(data_dir, '**', 'a4p-*.json'), recursive=True)):
    r = json.load(open(p)); d = os.path.dirname(p)
    def heart(c):
        rs = [json.loads(l) for l in gzip.open(os.path.join(d, c['file'].replace('.jsonl', '.ctm.jsonl') + '.gz'), 'rt')]
        h = [x for x in rs if x.get('roomClass') == 'BOSS' and x['act'] == 4]
        return h[-1] if h else None
    ch = r['children']; hs = {c['child']: heart(c) for c in ch}
    kids = [c for c in ch[1:] if hs[c['child']] is not None]
    pick = [ch[0]] + rng.sample(kids, min(3, len(kids))) if hs[0] is not None else []
    for c in pick:
        h = hs[c['child']]; pre = h['transition']['pre']
        line = {'id': f"{r['seed']}-p{c['child']:02d}", 'enc': 'THE_HEART', 'hp': pre['curHp'], 'maxHp': pre['maxHp'],
                'deck': [CARDS[x['id']] + ('+' if x['upgraded'] else '') for x in pre['deck']],
                'relics': [RELICS[x['id']] for x in pre['relics']], 'relicData': [x['data'] for x in pre['relics']],
                'potions': [POTS[x] for x in pre['potions'] if x > 1], 'potionCapacity': pre['potionCapacity'], 'bottleIdxs': pre['bottleIdxs']}
        fn = f"{r['seed']}-p{c['child']:02d}.jsonl"; open(os.path.join(out, fn), 'w').write(json.dumps(line) + '\n')
        meta.append(dict(file=fn, seed=r['seed'], child=c['child'], op=c['op'], insituHeartWon=h['transition']['combatOutcome'] == 1))
json.dump(meta, open(os.path.join(out, 'meta.json'), 'w'))
print(len(meta), sum(m['child'] == 0 for m in meta))
