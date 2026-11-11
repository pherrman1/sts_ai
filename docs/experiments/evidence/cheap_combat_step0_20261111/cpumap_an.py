import pickle, collections, numpy as np
rows,games=pickle.load(open('/tmp/claude-0/s0/cpumap.pkl','rb'))
A=np.array([r[:8]+(r[9],r[10],r[11]) for r in rows],dtype=np.int64); cpu=np.array([r[8] for r in rows])
seed,comb,floor,act,room,legal,inh,budget,sims,phases,cand=A.T
gcpu=np.array([g[3] for g in games]); win=np.array([g[1] for g in games])
print('games',len(games),'mean cpu/run %.1f'%gcpu.mean(),'heart %.2f%%'%win.mean(),'root cpu/run %.1f'%(cpu.sum()/len(games)),'roots/run %.0f'%(len(cpu)/len(games)))
print('root sims/run %.2fM, us/sim %.1f'%(sims.sum()/len(games)/1e6, cpu.sum()/sims.sum()*1e6))
tot=cpu.sum()
names={0:'normal',1:'elite',2:'boss',3:'other'}
print('\nact room   roots/run cpu/run share  sims/root  us/sim budget(median)')
for a in [1,2,3,4]:
  for r in [0,1,2,3]:
    m=(act==a)&(room==r)
    if m.sum()==0: continue
    print(a,names[r].ljust(7),'%7.1f %7.1f %5.1f%% %8.0f %6.1f %7d'%(m.sum()/1024,cpu[m].sum()/1024,100*cpu[m].sum()/tot,sims[m].mean(),cpu[m].sum()/max(sims[m].sum(),1)*1e6,np.median(budget[m])))
print('\nlegal actions: share of roots / cpu')
for lo,hi in [(1,1),(2,2),(3,4),(5,8),(9,16),(17,999)]:
  m=(legal>=lo)&(legal<=hi); print('%d-%d'%(lo,hi),'%5.1f%% roots %5.1f%% cpu'%(100*m.mean(),100*cpu[m].sum()/tot))
print('\ninherited visits share of budget (mean)', (inh/np.maximum(budget,1)).mean())
# per-game cpu tail
print('\ngame cpu quantiles', np.percentile(gcpu,[50,90,95,99,100]).round(0))
# heart-reaching games cpu
