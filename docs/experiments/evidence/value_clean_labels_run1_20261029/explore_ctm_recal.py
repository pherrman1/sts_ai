import sys,pickle,numpy as np,os
# Exploratory (after TEST was read): the CTM recalibrated on run-1 entries only. Run from this directory.
sys.argv=['x']; sys.path.insert(0,'.')
import fit_a4_run1 as R
from sklearn.linear_model import LogisticRegression
F=R.F; s0=R.s0
es,bad=R.entries(pickle.load(open('/mnt/project-files/value-clean-labels/stage2/a4.pkl','rb')),pickle.load(open('/tmp/claude-0/run1/run1_a4.pkl','rb')))
model=F.load_trees(os.path.join(F.REPO,'models/candidates/ctm_act4_survival_trees.txt'))
X,c=R.design(es,model)
n=np.array([len(e['kills']) for e in es],float); y5=np.array([np.mean(e['kills']) for e in es])
seed=np.array([e['seed'] for e in es]); run1=np.array([e['src']=='run1' for e in es])
split=np.array([s0.split_of(int(s)) for s in seed]); te=(split=='test')&run1
lc=np.log(np.clip(c,1e-4,1-1e-4)/(1-np.clip(c,1e-4,1-1e-4)))
for name,m in (('run1 train+val',run1&(split!='test')),('all train',split=='train')):
    Xg=np.r_[lc[m],lc[m]][:,None]; yg=np.r_[np.ones(m.sum()),np.zeros(m.sum())]; wg=np.r_[y5[m]*n[m],(1-y5[m])*n[m]]
    p=LogisticRegression(C=1e6).fit(Xg,yg,sample_weight=wg).predict_proba(lc[:,None])[:,1]
    b=(R.wbce(p[te],y5[te])*n[te]).sum()/n[te].sum(); print(name,'CTM recal bce',round(b,4),'mean p',p[te].mean().round(3))
print('test kill rate',(y5[te]*n[te]).sum()/n[te].sum(), 'stage2 kill', y5[~run1].mean(), 'run1 kill', (y5[run1]*n[run1]).sum()/n[run1].sum())
# README's single-label TEST BCE (comparable with stage 2): the same models, TEST scored against the base game only.
import xgboost as xgb
y1=np.array([float(e['kills'][0]) for e in es]); w1=np.where(run1,1.0,n)
tr,va=split=='train',split=='validation'
info={}
cf=c; XC=np.hstack([X,lc[:,None]])
g5=R.fit(XC,y5,n,tr,va,'GC_5',info)   # picked_5 = GC in fit_result.json
m=split=='train'
Xg=np.r_[lc[m],lc[m]][:,None]; yg=np.r_[np.ones(m.sum()),np.zeros(m.sum())]; wg=np.r_[y5[m]*n[m],(1-y5[m])*n[m]]
cc=LogisticRegression(C=1e6).fit(Xg,yg,sample_weight=wg).predict_proba(lc[:,None])[:,1]
d=R.wbce(g5[te],y1[te])-R.wbce(cc[te],y1[te])
print('single-label TEST: GC_5',R.wbce(g5[te],y1[te]).mean().round(4),'CTM_recal',R.wbce(cc[te],y1[te]).mean().round(4),
      'diff',d.mean().round(4),F.boot(seed[te],d))
