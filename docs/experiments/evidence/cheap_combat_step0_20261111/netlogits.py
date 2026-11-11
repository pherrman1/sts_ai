import sys, struct, numpy as np, torch, time
sys.path.insert(0,'/home/user/sts_ai/tools/combat_net')
import model as M
def load_ctn(p):
    b=open(p,'rb').read(); assert b[:8]==b'CTOKNET1'
    h=struct.unpack_from('<10i',b,8); o=48
    n,=struct.unpack_from('<i',b,o); o+=4; sd={}
    for _ in range(n):
        L,=struct.unpack_from('<i',b,o); o+=4; name=b[o:o+L].decode(); o+=L
        nd,=struct.unpack_from('<i',b,o); o+=4; dims=struct.unpack_from(f'<{nd}i',b,o); o+=4*nd
        cnt=int(np.prod(dims)) if nd else 1
        sd[name]=torch.from_numpy(np.frombuffer(b,'<f4',cnt,o).copy().reshape(dims)); o+=4*cnt
    d,layers,heads,ffn,g_len,m_num,q_len,a_len,von,aon=h
    net=M.CombatNet(d=d,layers=layers,heads=heads,g_len=g_len,m_num=m_num,q_len=q_len,a_len=a_len,aux=bool(aon),value=bool(von))
    net.load_state_dict(sd); net.eval(); return net
net=load_ctn(sys.argv[1]); A=M.Arrays('/tmp/claude-0/s0/tval')
torch.set_num_threads(4)
ao=np.asarray(A.a['act_off']); out=np.zeros(len(A.a['actions']),np.float32)
nc=np.diff(np.asarray(A.a['card_off'])); idx=np.argsort(nc,kind='stable'); t=time.time()
with torch.no_grad():
    for s in range(0,len(idx),512):
        bi=np.sort(idx[s:s+512]); b=M.collate(A,bi)
        lg,_,_=net(b); lg=lg.float().numpy(); m=b['act_mask'].numpy()
        for i,r in enumerate(bi):
            k=ao[r+1]-ao[r]; out[ao[r]:ao[r+1]]=lg[i,:k]
        if s%51200==0: print(s,time.time()-t,flush=True)
np.save(sys.argv[2],out)
