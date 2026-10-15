"""Concatenate packs (same format); later packs' r_src are offset by the earlier tag count."""
import sys, numpy as np
out, packs = sys.argv[1], sys.argv[2:]
Z = [dict(np.load(p)) for p in packs]
o = {}; ntag = 0; tags = []
for z in Z:
    z['r_src'] = (z['r_src'].astype(np.int16) + ntag).astype(np.int8); ntag += len(z['tags']); tags += list(z['tags'])
for k in ('st_idx', 'st_val', 'e_act', 'e_tgt', 'e_vis', 'r_src', 'r_seed', 'r_fight', 'r_var', 'r_val', 'r_nedge'):
    o[k] = np.concatenate([z[k] for z in Z])
ptr = [Z[0]['st_ptr']]
for z in Z[1:]:
    ptr.append(z['st_ptr'][1:] + ptr[-1][-1])
o['st_ptr'] = np.concatenate(ptr); o['tags'] = np.array(tags)
np.savez(out, **o); print(len(o['r_seed']), tags)
