import csv,glob,os,json,random
B=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIRS={'A_playout':['leaf-screen-3arm-32-20261006','leaf-screen-3arm-512-20261006'],'B_direct':['leaf-screen-3arm-32-20261006','leaf-screen-3arm-512-20261006'],
      'C_screen':['leaf-screen-3arm-32-20261006','leaf-screen-3arm-512-20261006'],'D_screengbm':['leaf-screengbm-32-20261006']}
def load(arm):
    out={}
    for d in DIRS[arm]:
        for f in glob.glob(f'{B}/{d}/{arm}/*.exit'):
            seed=int(os.path.basename(f).split('.')[0])
            if not 47001024<=seed<=47001151 or open(f).read().strip()!='0': continue
            r=list(csv.DictReader(open(f.replace('.exit','.csv'))))
            if len(r)==1: out[seed]=r[0]
    return out
arms={a:load(a) for a in DIRS}
seeds=sorted(set.intersection(*map(set,arms.values()))); n=len(seeds)
col=lambda a,k:[float(arms[a][s][k]) for s in seeds]
def boot(x,y):
    rng=random.Random(379); d=[b-a for a,b in zip(x,y)]; m=sorted(sum(d[rng.randrange(n)] for _ in range(n))/n for _ in range(10000)); return [sum(d)/n,m[250],m[9750]]
out={'pairs':n,'arms':{a:{'win':sum(col(a,'won'))/n,'floor':sum(col(a,'floor'))/n,'sec':sum(col(a,'sec'))/n} for a in arms}}
for x,y in (('A_playout','B_direct'),('A_playout','C_screen'),('A_playout','D_screengbm'),('B_direct','D_screengbm'),('C_screen','D_screengbm')):
    wx,wy=col(x,'won'),col(y,'won')
    out[f'{y}-{x}']={'win':boot(wx,wy),'floor':boot(col(x,'floor'),col(y,'floor')),'discordant':[sum(a>b for a,b in zip(wx,wy)),sum(b>a for a,b in zip(wx,wy))]}
print(json.dumps(out,indent=1))
