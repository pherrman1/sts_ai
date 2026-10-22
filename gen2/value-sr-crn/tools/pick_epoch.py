"""SR-CRN seeds round (../PLAN_SEEDS.md): which epochs of a finished run to export and score.

usage: pick_epoch.py runs/<name>/summary.json [BCE_BAR]
Prints one JSON line with:
- ranking: the pre-registered choice. It is the epoch with the highest in-training holdout ranking (history
  "sr_holdout" concordance) among the epochs whose selection-fold value BCE is at most BCE_BAR (default 0.570).
  Ties go to the earliest epoch.
- valueStop: the same choice, restricted to the epochs that a patience-3 stop on the selection objective would have
  run. That is the procedure that picked §645's exploratory epoch 11.
- valueStopEpochsRun: the last epoch such a stop would have run.
- fold: the run's own selected epoch (selection objective; with --patience 0 it is chosen over all epochs).
- curve: [epoch, holdout ranking, selection objective, selection-fold value BCE] per epoch.
"""
import json
import sys


def main(path, bar='0.570'):
    s = json.load(open(path))
    bar = float(bar)
    curve = [[int(h['epoch']), h['sr_holdout']['concordance'], h['select']['objective'],
              h['select']['value']['all']['bce']] for h in s['history'] if int(h['epoch']) > 0 and 'select' in h]

    def best(rows):
        ok = [r for r in rows if r[3] <= bar]
        return max(ok, key=lambda r: (r[1], -r[0]))[0] if ok else None

    stop, low, since = len(curve), None, 0  # distill.py: stop once 3 epochs pass without a lower objective
    for i, r in enumerate(curve):
        if low is None or r[2] < low:
            low, since = r[2], 0
        else:
            since += 1
            if since >= 3:
                stop = i + 1
                break
    print(json.dumps({'ranking': best(curve), 'valueStop': best(curve[:stop]), 'valueStopEpochsRun': curve[stop - 1][0],
                      'fold': s['selected_epoch'], 'epochsRun': s['epochs_run'], 'bceBar': bar, 'curve': curve}))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(*sys.argv[1:])
