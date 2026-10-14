import numpy as np, sys
z=np.load('/root/fs/pack-g4.npz'); enc=np.load('/root/fs/enc.npy')
A={k:z[k] for k in z.files}
eptr=np.concatenate([[0],np.cumsum(A['r_nedge'],dtype=np.int64)])
for e in map(int,sys.argv[1:]):
    r=np.flatnonzero(enc==e)
    sl=np.concatenate([np.arange(A['st_ptr'][i],A['st_ptr'][i+1]) for i in r])
    es=np.concatenate([np.arange(eptr[i],eptr[i+1]) for i in r])
    lens=np.diff(A['st_ptr'])[r]
    out=dict(st_idx=A['st_idx'][sl],st_val=A['st_val'][sl],st_ptr=np.concatenate([[0],np.cumsum(lens)]).astype(np.int64),
      e_act=A['e_act'][es],e_tgt=A['e_tgt'][es],e_vis=A['e_vis'][es],tags=A['tags'])
    for k in ('r_src','r_seed','r_fight','r_var','r_val','r_nedge'): out[k]=A[k][r]
    np.savez(f'/root/fs/sub/enc{e}.npz',**out); print(e,len(r),len(es),flush=True)
