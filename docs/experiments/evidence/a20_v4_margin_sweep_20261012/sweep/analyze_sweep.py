import csv,glob,json,collections,random,sys
S=sys.argv[1]
arms="a20_m0 a20_m0.25 a20_m0.5 a20_m1 a20_m2 a20_m4 a0_m0 a0_m0.25 a0_m0.5 a0_m1 a0_m2 a0_m4 heur".split()
R={}
for a in arms:
    d={}
    for f in glob.glob(f'{S}/w*/out/{a}-*.csv'):
        if f.endswith('.v4.csv'): continue
        for r in csv.DictReader(open(f)): d[int(r['seed'])]=r
    R[a]=d
seeds=sorted(R['heur'])
def boot(x,y):
    rng=random.Random(20261012); n=len(x); diffs=[x[i]-y[i] for i in range(n)]; m=sum(diffs)/n
    bs=sorted(sum(diffs[rng.randrange(n)] for _ in range(n))/n for _ in range(10000))
    return m,bs[250],bs[9749]
print(f"{'arm':10} n wins  win% floor  skull  cpu  vs heur dWin[95%CI]          vs a0_m1 dWin[95%CI]")
for a in arms:
    d=R[a]; assert sorted(d)==seeds,(a,len(d))
    w=[int(d[s]['won']) for s in seeds]; fl=sum(int(d[s]['floor']) for s in seeds)/len(seeds)
    sk=sum(1 for s in seeds if d[s]['won']=='0' and d[s]['fightsLost']=='0')
    cpu=sum(float(d[s]['sec']) for s in seeds)/len(seeds)
    h=[int(R['heur'][s]['won']) for s in seeds]; c=[int(R['a0_m1'][s]['won']) for s in seeds]
    m1=boot(w,h); m2=boot(w,c)
    print(f"{a:10} {len(seeds)} {sum(w):4} {100*sum(w)/len(w):5.1f} {fl:5.1f} {sk:4} {cpu:4.0f}  {100*m1[0]:+5.1f} [{100*m1[1]:+5.1f},{100*m1[2]:+5.1f}]   {100*m2[0]:+5.1f} [{100*m2[1]:+5.1f},{100*m2[2]:+5.1f}]")
# repro check vs first run
first={}
for f in glob.glob('/root/a20v4a0/main/u-*.csv'):
    if f.endswith('.v4.csv'): continue
    for r in csv.DictReader(open(f)): first[int(r['seed'])]=r
same=sum(1 for s in seeds if all(first[s][k]==R['a20_m0'][s][k] for k in ('won','floor','hpEnd','maxHp','fightsLost')))
print('a20_m0 rerun identical to first run (won,floor,hp,maxHp,fightsLost):',same,'/',len(seeds))
# V4 ownership + threshold check
for a in arms:
    own=tot=0; th=set()
    for f in glob.glob(f'{S}/w*/out/{a}-*.v4.csv'):
        for r in csv.DictReader(open(f)): tot+=1; own+=int(r['owned']); th.add(r['threshold'])
    print(f'{a:10} V4 gate rows {tot:6} V4-taken {100*own/max(tot,1):5.1f}%  thresholds {sorted(th)}')
print('A20 - A0 at same margin:')
for m in ['0','0.25','0.5','1','2','4']:
    x=[int(R['a20_m'+m][s]['won']) for s in seeds]; y=[int(R['a0_m'+m][s]['won']) for s in seeds]
    b=boot(x,y); print(f'  m{m}: {100*b[0]:+5.1f} [{100*b[1]:+5.1f},{100*b[2]:+5.1f}]')
