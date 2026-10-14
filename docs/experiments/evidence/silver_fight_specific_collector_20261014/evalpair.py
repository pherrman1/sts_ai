import sys,numpy as np,torch
sys.path.insert(0,'/home/user/sts_ai/tools'); import silver_az_mlp as M
sub,a,b=sys.argv[1:4]
d=M.Data(sub); te=d.roots((M.TEST,))
def ld(p):
    c=torch.load(p); n=M.make_net(torch,c['h1'],c['h2']); n.load_state_dict(c['state']); return n,tuple(np.array(x,np.float32) for x in c['scales'])
for p in (a,b):
    n,s=ld(p); r=M.evaluate(torch,n,d,te,s); print(p.split('/')[-1], round(r['ce'],4), round(r['top1'],3))
