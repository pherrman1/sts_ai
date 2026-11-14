import numpy as np, json, sys
def est(K):
    n=K.shape[0]; T=K.sum(); D=np.trace(K); r=K.sum(1); d=np.diag(K)
    mu2=(T-D)/(n*(n-1)); trS=(D-T/n)/(n-1)
    Tk=T-2*r+d; Dk=D-d; m=n-1
    jk=(Tk-Dk)/(m*(m-1))
    se=np.sqrt((n-1)/n*((jk-jk.mean())**2).sum())
    return mu2,se,trS
out={}
for pair,tags,ns in (("it22+it23",("it22","it23"),(507,507)),("lb35+lc419",("lb35","lc419"),(520,520))):
    for lab in ("K","Kw"):
        K=np.load(f"{lab}-{pair}.npy")
        o=np.cumsum((0,)+ns)
        sets={tags[0]:slice(o[0],o[1]),tags[1]:slice(o[1],o[2]),pair:slice(0,o[2])}
        for nm,s in sets.items():
            mu2,se,trS=est(K[s,s]); up=mu2+1.645*se
            n=s.stop-s.start
            out[f"{nm}/{lab}"]=dict(n=n,mu2=mu2,se=se,z=mu2/se,trS=trS,mu2_up95=up,B_noise_lower95=trS/up if up>0 else None,
                 snr520_upper95=520*up/trS, cos520_upper95=float(np.sqrt(520*up/trS/(1+520*up/trS))))
for k,v in out.items(): print(k,{a:round(b,4) if isinstance(b,float) else b for a,b in v.items()})
json.dump(out,open("jackknife.json","w"),indent=1,default=float)
