"""Philipp-authorized rerun of the four lost §497 workers' sources (W=7, 8, 27, 34), each split in two halves.

Runs the frozen bundle's own heart_outcome_collect.worker() unchanged (all approval, activation, deadline,
CPU, unit, timeout, receipt and sealed-archive logic), restricted to half H of worker W's 40 fixed seeds:
the seeds at even (H=0) or odd (H=1) positions of that worker's assignment.
Usage: python3 rerun_half.py BUNDLE PLAN ACTIVATION OUT W H ACTIVATION_SHA256
"""
import importlib.util
from pathlib import Path
import sys

LOST = (7, 8, 27, 34)
bundle, plan, activation, out = (Path(a) for a in sys.argv[1:5])
w, h, act = int(sys.argv[5]), int(sys.argv[6]), sys.argv[7]
if w not in LOST or h not in (0, 1):
    raise SystemExit('rerun only for lost workers 7, 8, 27, 34 and half 0 or 1')
bundle = bundle.resolve()
sys.path.insert(0, str(bundle))
spec = importlib.util.spec_from_file_location('heart_outcome_collect', bundle / 'heart_outcome_collect.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
own = [s['seed'] for s in mod.assignments() if s['worker'] == w]
half = set(own[h::2])
verify_plan = mod.verify_plan


def restricted(plan_path, bundle_path):
    checked = verify_plan(plan_path, bundle_path)  # full original binding checks first
    return {**checked, 'sources': [s for s in checked['sources'] if s['worker'] != w or s['seed'] in half]}


mod.verify_plan = restricted
mod.worker(plan, bundle, activation, out.resolve(), w, act)
