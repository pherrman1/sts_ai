import csv,json,sys
from pathlib import Path
import numpy as np

a,b,out=map(Path,sys.argv[1:])
def read(p):
 rows=list(csv.DictReader(p.open())); r={int(x['seed']):x for x in rows}
 assert len(rows)==32 and set(r)==set(range(970000,970032))
 return r
ra,rb=read(a),read(b);seeds=list(range(970000,970032))
ca,cb=[json.loads(p.with_suffix('.config.json').read_text())['env'] for p in (a,b)]
assert {k:v for k,v in ca.items() if not k.startswith('STS_OOC_MCTS')}=={k:v for k,v in cb.items() if not k.startswith('STS_OOC_MCTS')}
assert ca['STS_OOC_MCTS']==cb['STS_OOC_MCTS']=='1' and ca['STS_OOC_MCTS_SIMS']=='512' and cb['STS_OOC_MCTS_SIMS']=='2048'
ma,mb=[json.loads(Path(str(p)+'.meta.json').read_text()) for p in (a,b)]
assert ma['config']['executableGitSha']==mb['config']['executableGitSha']
idx=np.random.Generator(np.random.PCG64(20260914)).integers(0,32,size=(200000,32))
r={'interpretation':'Secondary descriptive paired budget comparison; fixed same source/models/seeds, historical runtime.'}
for key in ('won','floor','hpEnd','sec'):
 x,y=[np.array([float(rows[s][key]) for s in seeds]) for rows in (ra,rb)]
 d=y-x;r[key]={'mean512':float(x.mean()),'mean2048':float(y.mean()),'delta2048minus512':float(d.mean()),'pairedBootstrap95CI':np.quantile(d[idx].mean(axis=1),[.025,.975],method='linear').tolist()}
r['wins512']=sum(int(x['won']) for x in ra.values());r['wins2048']=sum(int(x['won']) for x in rb.values())
r['only2048']=sum(int(rb[s]['won'])==1 and int(ra[s]['won'])==0 for s in seeds)
r['only512']=sum(int(ra[s]['won'])==1 and int(rb[s]['won'])==0 for s in seeds)
out.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
