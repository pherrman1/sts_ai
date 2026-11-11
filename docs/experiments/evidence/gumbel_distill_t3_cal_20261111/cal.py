import numpy as np, json, sys
z=np.load(sys.argv[1])  # usage: python3 cal.py t3cal_val.npz coefs_out.json
p=z['p'].astype(np.float64); n=len(p)
mid=(np.arange(20)+0.5)/20
pwin=p[:,1:].sum(1); efr=(p[:,1:]*mid).sum(1)
maxhp=z['maxHp'].astype(float); hp=z['hp'].astype(float); npot=z['npot'].astype(float)
ehp=efr*maxhp
Q=z['rootQ'].astype(float); S=z['score'].astype(float); ok=np.isfinite(Q)
seed=z['seed']; h=(seed*2654435761)%97
tr=ok&(h<60); te=ok&(h>=60)
print('rows',n,'train',tr.sum(),'test',te.sum())
def fit(X,y,name):
    b=np.linalg.lstsq(X[tr],y[tr],rcond=None)[0]; r=y[te]-X[te]@b
    print(f"{name:40s} R2 {1-r.var()/y[te].var():.3f} resid sd {r.std():.2f} bias {r.mean():+.2f}  coef {np.round(b,3)}")
    return b
one=np.ones(n)
fit(np.stack([one,hp,npot],1),Q,'Q ~ hp+npot')
fit(np.stack([one,pwin,ehp,npot,hp],1),Q,'Q ~ pwin,ehp,npot,hp')
fit(np.stack([one,pwin,ehp,npot,hp],1),S,'score ~ pwin,ehp,npot,hp')
print('Q vs score corr',np.corrcoef(Q[ok],S[ok])[0,1],'mean Q-S',(Q[ok]-S[ok]).mean())
enc=z['encounter']; X=np.stack([one,pwin,ehp,npot,hp],1)
pred=np.full(n,np.nan); coefs={}
gb=np.linalg.lstsq(X[tr],Q[tr],rcond=None)[0]
for e in np.unique(enc):
    m=tr&(enc==e)
    if m.sum()>=2000:
        b=np.linalg.lstsq(X[m],Q[m],rcond=None)[0]
    else: b=gb
    coefs[int(e)]=b.tolist(); mm=enc==e; pred[mm]=X[mm]@b
r=Q[te]-pred[te]; print('per-encounter R2',1-r.var()/Q[te].var(),'resid sd',r.std())
# within-encounter variance explained
w=0;tot=0
for e in np.unique(enc[te]):
    m=te&(enc==e); w+=((Q[m]-pred[m])**2).sum(); tot+=((Q[m]-Q[m].mean())**2).sum()
print('within-encounter R2', 1-w/tot)
# baseline per-encounter hp+npot
pb=np.full(n,np.nan)
for e in np.unique(enc):
    m=tr&(enc==e); Xb=X[:,[0,3,4]]
    b=np.linalg.lstsq(Xb[m],Q[m],rcond=None)[0] if m.sum()>=2000 else np.linalg.lstsq(Xb[tr],Q[tr],rcond=None)[0]
    pb[enc==e]=Xb[enc==e]@b
w=0
for e in np.unique(enc[te]):
    m=te&(enc==e); w+=((Q[m]-pb[m])**2).sum()
print('within-encounter R2 baseline hp+npot', 1-w/tot)
json.dump(coefs,open(sys.argv[2],'w'))
X2=np.concatenate([np.stack([one,npot,hp,maxhp],1),p[:,1:]*maxhp[:,None]/20,p[:,:1]],1)
pr=np.full(n,np.nan)
gb2=np.linalg.lstsq(X2[tr],Q[tr],rcond=None)[0]
for e in np.unique(enc):
    m=tr&(enc==e)
    b=np.linalg.lstsq(X2[m],Q[m],rcond=None)[0] if m.sum()>=3000 else gb2
    pr[enc==e]=X2[enc==e]@b
w=0
for e in np.unique(enc[te]):
    m=te&(enc==e); w+=((Q[m]-pr[m])**2).sum()
print('within-encounter R2 rich', 1-w/tot, 'resid sd', np.sqrt(w/te.sum()))
# by act x room summary for the 5-feature per-encounter model
for a in (1,2,3,4):
  for rm in (0,1,2):
    m=te&(z['act']==a)&(z['elite_boss']==rm)
    if m.sum()>500: r=Q[m]-pred[m]; print(a,rm,m.sum(),'resid sd %.1f  Q sd %.1f'%(r.std(),Q[m].std()))
