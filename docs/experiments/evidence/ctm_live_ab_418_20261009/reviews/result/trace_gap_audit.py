import json,glob,csv,sys,collections
root=sys.argv[1]
issues=collections.Counter(); det=[]
for tr in sorted(glob.glob(f'{root}/*.trace.jsonl')):
    unit=tr.split('/')[-1][:-len('.trace.jsonl')]; arm=unit.split('-')[0]
    rows={int(r['seed']):r for r in csv.DictReader(open(f'{root}/{unit}.csv'))}
    bat=collections.defaultdict(list); ooc=collections.defaultdict(list); order=[]
    for l in open(tr,'rb'):
        if not l.strip(): continue
        try: r=json.loads(l)
        except Exception: continue
        s=int(r['seed']); order.append(s)
        if r.get('kind')=='battle': bat[s].append(r['fight'])
        elif r.get('kind')=='ooc': ooc[s].append(r['idx'])
        else: issues['otherkind']+=1
    for s,row in rows.items():
        f=bat[s]; o=ooc[s]
        fs=sorted(f); os_=sorted(o)
        if fs!=list(range(fs[0],fs[0]+len(fs))) if fs else True:
            det.append((unit,s,'battle gap',[x for x in range(fs[0],fs[-1]+1) if x not in fs] if fs else 'none'))
        if os_!=list(range(os_[0],os_[0]+len(os_))) if os_ else True:
            det.append((unit,s,'ooc gap',[x for x in range(os_[0],os_[-1]+1) if x not in os_] if os_ else 'none'))
        if f!=fs: det.append((unit,s,'battle order',None))
        if o!=os_: det.append((unit,s,'ooc order',None))
        # lost fights vs csv
    # interleaving of seeds
    runs=[k for k,_ in __import__('itertools').groupby(order)]
    if len(runs)!=len(set(runs)): det.append((unit,None,'seed interleave',runs))
    issues['units']+=1
for d in det: print(d)
print(issues, len(det))
