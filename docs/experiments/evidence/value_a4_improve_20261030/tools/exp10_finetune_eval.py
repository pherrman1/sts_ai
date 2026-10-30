"""Score the heart1 fine-tune OOF predictions (heart1_finetune.py, PC) in the same CV frame.
usage: VA4_DATA=DIR exp10_finetune_eval.py ft_frozen.npz ft_top2.npz ft_full.npz"""
import sys, json, pickle, numpy as np, core
d = core.build(2); dc = ((d['seed'] % 4) != 3) & (d['src'] != 'extra')
P8 = pickle.load(open(core.D + 'P_exp8.pkl', 'rb')); P9 = pickle.load(open(core.D + 'P_exp9.pkl', 'rb'))
ref = {'ENS_rc': P8['ENS_rc'], 'LRemb': P9['LR_emb_C0.01'], 'ENS_rc+LRemb': (P8['ENS_rc'] + P9['LR_emb_C0.01']) / 2}
for f in sys.argv[1:]:
    Z = np.load(f); idt = json.loads(str(Z['identity'])); P = Z['P']; reps = list(Z['reps'])
    assert P.shape[1] == len(d['y']) and not np.isnan(P[:, dc]).any()
    R = {k: v[reps] for k, v in ref.items()}  # same fold assignments (rep r = core.folds rep r)
    print(idt['mode'], idt.get('seconds'), json.dumps(core.score(P, d, dc)))
    for k, v in R.items():
        print('  ', idt['mode'], '-', k, core.paired(core.per_seed_loss(P, d, dc), core.per_seed_loss(v, d, dc), d, dc))
    E = (R['ENS_rc'] + P) / 2
    print('  ', 'ENS_rc+' + idt['mode'], json.dumps(core.score(E, d, dc)), core.paired(core.per_seed_loss(E, d, dc), core.per_seed_loss(R['ENS_rc'], d, dc), d, dc))
