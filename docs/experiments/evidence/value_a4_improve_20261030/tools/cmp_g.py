"""Paired CV comparison of the candidates against G (the record-only §720 model that stage 5 uses). Needs exp1/5/6 outputs."""
import pickle, numpy as np, core
d = core.build(2); d0 = core.build(False); N0 = len(d0['y'])
assert (d['seed'][:N0] == d0['seed']).all() and np.allclose(d['y'][:N0], d0['y'])
P1 = np.load(core.D + 'P_exp1.npy', allow_pickle=True).item(); P6 = pickle.load(open(core.D + 'P_exp6.pkl', 'rb')); P5 = pickle.load(open(core.D + 'P_exp5.pkl', 'rb'))[0]
dc = (d0['seed'] % 4) != 3
L = lambda P: core.per_seed_loss(P, d0, dc)
G = P1['G_d3']; print('G', core.score(G, d0, dc))
for k, P in (('GCe(entry CTM)', P1['GCe_d3']), ('GBM_core', P5['GBM_core'][:, :N0]), ('ENS_core', P5['ENS_core'][:, :N0]),
             ('GBM_all', P6['GBM_all'][:, :N0]), ('ENS_all', P6['ENS_all'][:, :N0])):
    print(k, '- G', core.paired(L(P), L(G), d0, dc), core.score(P, d0, dc))
