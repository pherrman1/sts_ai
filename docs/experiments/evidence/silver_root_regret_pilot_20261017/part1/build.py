import csv,glob,collections,pandas as pd
ARMS=["base2500","endwide2500","othernarrow2500","spire2500"]
def sc(r): return 0.0 if r["outcome"]=="DEATH" else 53+float(r["curHp"])+11*float(r["potionCount"])+0.25*float(r["gold"])+2*float(r["maxHp"])
states={};valid=collections.defaultdict(lambda:True);ctrl={};S={}
for d in glob.glob('/tmp/claude-0/x518/w*/out'):
  for p in glob.glob(d+'/shard*.states.csv'):
    pre=p[:-len('.states.csv')]
    for r in csv.DictReader(open(p)): states[r['stateId']]=r
    for r in csv.DictReader(open(pre+'.arms.csv')):
      valid[r['stateId']]&= r['valid']=='1'
      if r['arm']=='control': ctrl[r['stateId']]=r
    for r in csv.DictReader(open(pre+'.samples.csv')):
      if r['forecaster'] in ARMS: S[(r['stateId'],r['forecaster'],int(r['k']))]=sc(r)
out=[]
for sid,st in states.items():
  if not valid[sid] or not all((sid,a,k) in S for a in ARMS for k in (0,1)): continue
  row=dict(stateId=sid,seed=int(st['sourceSeed']),act=int(st['act']),floor=int(st['floor']),room=st['roomClass'],enc=st['encounter'],
     preHp=float(st['preHp']),preMaxHp=float(st['preMaxHp']),pots=int(st['prePotions']),ctmPDeath=float(st['ctmPDeath'] or 'nan'),ctmExpHp=float(st['ctmExpectedHp'] or 'nan'),
     ctrlDec=int(ctrl[sid]['decisions']),ctrlCpu=float(ctrl[sid]['cpuSeconds']),ctrlHp=float(ctrl[sid]['terminalHp']),ctrlWon=int(ctrl[sid]['won']))
  for a in ARMS:
    for k in (0,1): row[f'{a}_k{k}']=S[(sid,a,k)]
  out.append(row)
df=pd.DataFrame(out);df.to_csv('/tmp/claude-0/x518/an/rep.csv',index=False);print(len(df))
