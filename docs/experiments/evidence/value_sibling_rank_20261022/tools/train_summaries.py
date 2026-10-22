"""Key training numbers of the sibling-ranking round from the runs' summary.json (data branch claude/az-gen2-data).

usage: train_summaries.py OUT.json NAME=SUMMARY_JSON ...
Per run: selected epoch, epochs run, wall, selection-fold metrics at the selected epoch (KL, value BCE/AUC), the
VALIDATION value metrics, the sibling-ranking holdout report and its per-epoch curve, and the monotone report.
"""
import json, sys

out = {}
for arg in sys.argv[2:]:
    name, path = arg.split('=', 1)
    d = json.load(open(path))
    h = next(x for x in d['history'] if x['epoch'] == d['selected_epoch'])
    args = {k: v for k, v in d['args'].items() if k != 'data'}  # the row-file list (2,352 paths) is only counted
    args['dataFiles'] = len(d['args'].get('data', []))
    out[name] = {'args': args,
                 'selectedEpoch': d['selected_epoch'], 'epochsRun': d['epochs_run'], 'wallSec': d['wall_sec'],
                 'select': {'kl': h['select']['kl'], 'objective': h['select'].get('objective'),
                            'value': h['select']['value']['all']},
                 'validationValue': d['value']['all'], 'siblingRank': d.get('sibling_rank'),
                 'srHoldoutPerEpoch': [x.get('sr_holdout', {}).get('concordance') for x in d['history']],
                 'monotoneSelect': d.get('monotone', {}).get('select')}
json.dump(out, open(sys.argv[1], 'w'), indent=1)
for n, r in out.items():
    print(n, r['selectedEpoch'], r['epochsRun'], r['select']['value']['bce'], (r['siblingRank'] or {}).get('holdout'))
