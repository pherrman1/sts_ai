import re,json,collections,sys,csv
import numpy as np
sys.path.insert(0,'tools'); import ctm_act4_survival as m
from pathlib import Path
src=open('include/constants/Cards.h').read()
names=re.findall(r'"((?:[^"\\]|\\.)*)"', re.search(r'cardNames\[\] = \{(.*?)\};',src,re.S).group(1))
dup={n for n,c in collections.Counter(names).items() if c>1}
rel=re.findall(r'"([^"]*)"', re.search(r'relicEnumNames\[\] \{(.*?)\};',open('include/constants/Relics.h').read(),re.S).group(1))
pot=re.findall(r'"([^"]*)"', re.search(r'potionEnumNames\[\] = \{(.*?)\};',open('include/constants/Potions.h').read(),re.S).group(1))
# the Act-4 training rows give the Ironclad id for each duplicated name
F=sys.argv[1]; W=sys.argv[2]
rows=[json.loads(l) for l in open(F+'/heart64.jsonl')]
used=collections.Counter()
d=m.load(W+'/all.jsonl')
train_gold=np.median(d['X'][:,m.NAMES.index('gold')])
for r in rows:
    for c in r['deck']:
        b=c[:-1] if c.endswith('+') else c
        if b in dup: used[b]+=1
print('duplicated names in decks', used, 'gold median', train_gold)
def ids(name):
    return [i for i,n in enumerate(names) if n==name]
inputs=[]
for r in rows:
    cards=[]
    for c in r['deck']:
        up=c.endswith('+'); b=c[:-1] if up else c
        cand=ids(b); cards.append({'cardId':cand[-1] if len(cand)>1 else cand[0],'upgraded':up})
    p={'globals':{'encounter':57,'curHp':r['hp'],'maxHp':r['maxHp'],'gold':train_gold,'potionCapacity':r['potionCapacity'],'potionCount':len(r['potions'])},
       'cards':cards,'relics':[{'relicId':rel.index(x)} for x in r['relics']],
       'potions':[{'slot':i,'potionId':pot.index(x)} for i,x in enumerate(r['potions'])]}
    inputs.append(p)
X=np.stack([m.features(p) for p in inputs])
import xgboost as xgb
fit=json.load(open(W+'/fit/fit.json')); bst=xgb.Booster(); bst.load_model(W+'/fit/model.ubj')
pred=bst.predict(xgb.DMatrix(X,feature_names=m.NAMES),iteration_range=(0,fit['selected']['best_iteration']+1))
rep=collections.defaultdict(list)
for x in csv.DictReader(open(F+'/heart_budget.csv')):
    if x['sims']=='10000': rep[x['id']].append(int(x['won']))
obs=np.array([1-np.mean(rep[r['id']]) for r in rows]); src_obs=np.array([0 if r['observedWon'] else 1 for r in rows])
print('states',len(rows),'replays/state',set(len(v) for v in rep.values()))
print(f'candidate mean death {pred.mean():.3f}; replay death (10k, 3 copies) {obs.mean():.3f}; source-run death {src_obs.mean():.3f}')
print('corr(pred, replay death)', np.corrcoef(pred,obs)[0,1])
y=np.concatenate([[1-w for w in rep[r['id']]] for r in rows]); pp=np.repeat(pred,3)
print('replay-row BCE cand', m.bce(pp,y).mean(), 'AUC', m.auc(pp,y), 'const BCE', m.bce(np.full(len(y),y.mean()),y).mean())
