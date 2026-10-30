"""Ensembles of the exp8 members with the heart1-embedding linear probe (exp9). usage: VA4_DATA=DIR exp9b_combos.py"""
import json, pickle, numpy as np, core
d = core.build(2); dc = ((d['seed'] % 4) != 3) & (d['src'] != 'extra')
P8 = pickle.load(open(core.D + 'P_exp8.pkl', 'rb')); P9 = pickle.load(open(core.D + 'P_exp9.pkl', 'rb'))
C = {'ENS_rc + LRemb (1:1)': (P8['ENS_rc'] + P9['LR_emb_C0.01']) / 2,
     'GBM_rc + LR_rc + LRemb (1/3 each)': (P8['GBM_rc'] + P8['LR_rc'] + P9['LR_emb_C0.01']) / 3,
     'GBM_rc + LRemb': (P8['GBM_rc'] + P9['LR_emb_C0.01']) / 2,
     'ENS_rc_emb + LRemb': (P9['ENS_rc_emb'] + P9['LR_emb_C0.01']) / 2}
for k, p in C.items():
    print(k, json.dumps(core.score(p, d, dc)), core.paired(core.per_seed_loss(p, d, dc), core.per_seed_loss(P8['ENS_rc'], d, dc), d, dc))
