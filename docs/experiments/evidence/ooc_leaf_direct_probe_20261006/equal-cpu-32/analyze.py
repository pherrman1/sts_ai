import csv,glob,os,sys,json,random
R=os.path.dirname(os.path.abspath(__file__))
def load(arm):
    d={}
    for f in glob.glob(f'{R}/{arm}/*.csv'):
        ex=f.replace('.csv','.exit')
        if not os.path.exists(ex) or open(ex).read().strip()!='0': continue
        rows=list(csv.DictReader(open(f)))
        if len(rows)!=1: continue
        r=rows[0]; d[int(r['seed'])]=r
    return d
A,B=load('A_playout'),load('B_direct4096')
seeds=sorted(set(A)&set(B))
def arr(D,k,t=float): return [t(D[s][k]) for s in seeds]
wa,wb=arr(A,'won',int),arr(B,'won',int); fa,fb=arr(A,'floor'),arr(B,'floor'); sa,sb=arr(A,'sec'),arr(B,'sec')
n=len(seeds)
def boot(x,y,reps=10000):
    rng=random.Random(379); d=[b-a for a,b in zip(x,y)]; m=[]
    for _ in range(reps):
        s=[d[rng.randrange(n)] for _ in range(n)]; m.append(sum(s)/n)
    m.sort(); return sum(d)/n, m[int(.025*reps)], m[int(.975*reps)]
mean=lambda v:sum(v)/len(v)
out={'pairs':n,'win_A':mean(wa),'win_B':mean(wb),'floor_A':mean(fa),'floor_B':mean(fb),'sec_A':mean(sa),'sec_B':mean(sb),
 'win_delta_B_minus_A':boot(wa,wb),'floor_delta_B_minus_A':boot(fa,fb),'sec_ratio_B_over_A':mean(sb)/mean(sa),
 'discordant_wins':{'A_only':sum(a and not b for a,b in zip(wa,wb)),'B_only':sum(b and not a for a,b in zip(wa,wb))}}
print(json.dumps(out,indent=1))
