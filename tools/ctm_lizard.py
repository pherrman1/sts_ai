"""Active Lizard Tail with Entropic Brew or Fairy Potion for #418 research candidates (PR9).

The active-Lizard correction composes three classes from a child CTM's survival: an
ordinary win (Tail unused, p = survival without the Tail), a win after the Tail fired
(q * r) and a loss (q * (1 - r)), with mechanical q = 1 - p and a learned
r = sigmoid(b0 + b1 * (pReserveWin - mean) / scale). Brew states route to the standard
(Attention) child, so they need their own r; a Fairy Potion fires before the Tail, so the
Tail-consumed branch has none.

    one_combat ctmlizardfeatures ROWS.jsonl FAST.native STANDARD.native OUT.csv
    python tools/ctm_lizard.py fit --features OUT.csv [OUT2.csv ...] --out DIR
    python tools/ctm_lizard.py extend --artifact FAST.native --fit DIR/fit.json --out NEW.native \\
        [--fast-r] [--brew] [--fairy]

`fit` refits r per child on the direct labels (rows where the Tail fired: a win after it
is r = 1, a loss r = 0) with the L2 strength chosen on VALIDATION, and reports r NLL against
the TRAIN base rate, q calibration (mean q against the observed Tail rate) and the
three-class NLL, by split and cohort (plain, fairy, brew). `extend` writes the
`lizardBrew` / `lizardFairy` capabilities and, with --fast-r, the refitted fast r into the
artifact's activeLizardCorrection, and prints the manifest entries it needs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct

import numpy as np

try:
    from tools import ctm_escape as e
except ModuleNotFoundError:  # direct invocation from the tools directory
    import ctm_escape as e

MAGIC = b'COMBAT_TRANSITION_RUNTIME_V2\0'
CHILDREN = ('fast', 'standard')
COHORTS = ('plain', 'fairy', 'brew')
L2_GRID = (0.0, 0.01, 0.1, 1.0, 10.0)
SPLITS = ('TRAIN', 'VALIDATION', 'TEST')


def load_features(paths):
    rows = []
    for path in paths:
        with open(path, newline='') as stream:
            for r in csv.DictReader(stream):
                if r['supported'] != '1':
                    continue
                rows.append(dict(seed=int(r['source_seed']), label=int(r['label']), child=r['child'],
                                 fairy=r['fairy'] == '1', brew=r['brew'] == '1',
                                 p=float(r['p_ordinary']), reserve=float(r['p_reserve'])))
    if not rows:
        raise ValueError('no supported active-Lizard rows')
    col = {k: np.asarray([r[k] for r in rows]) for k in rows[0]}
    col['split'] = np.asarray([e.split_for_seed(s) for s in col['seed']])
    col['cohort'] = np.where(col['brew'], 'brew', np.where(col['fairy'], 'fairy', 'plain'))
    return col


def _sigmoid(z):
    return 1 / (1 + np.exp(-np.clip(z, -40, 40)))


def fit_logistic(x, y, l2):
    """One standardized feature; L2 on the slope only. Returns the rModel payload."""
    mean = float(x.mean())
    scale = float(x.std()) or 1.0
    design = np.stack((np.ones_like(x), (x - mean) / scale), 1)
    beta = np.zeros(2)
    penalty = np.diag([0.0, l2])
    for _ in range(100):
        p = _sigmoid(design @ beta)
        gradient = design.T @ (p - y) + penalty @ beta
        hessian = design.T @ (design * (p * (1 - p))[:, None]) + penalty + 1e-9 * np.eye(2)
        step = np.linalg.solve(hessian, gradient)
        beta -= step
        if np.abs(step).max() < 1e-10:
            break
    if not np.isfinite(beta).all():
        raise ValueError('r fit did not converge')
    return dict(featureMean=[mean], featureScale=[scale], standardizedCoefficients=[float(b) for b in beta])


def r_of(model, reserve):
    beta = model['standardizedCoefficients']
    return _sigmoid(beta[0] + beta[1] * (np.asarray(reserve) - model['featureMean'][0]) / model['featureScale'][0])


def _nll(p, y):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean()) if len(y) else None


def model_sha256(model):
    return hashlib.sha256(json.dumps(model, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def fit(features, out):
    out = Path(out)
    if out.exists():
        raise ValueError(f'refusing to overwrite {out}')
    col = load_features(features)
    fired = col['label'] > 0
    models, report = {}, {}
    for child in CHILDREN:
        mine = col['child'] == child
        train = mine & fired & (col['split'] == 0)
        valid = mine & fired & (col['split'] == 1)
        y = (col['label'] == 1).astype(float)
        if len(set(y[train])) < 2:
            raise ValueError(f'{child}: TRAIN needs Tail-fired wins and losses')
        scores = {}
        for l2 in L2_GRID:
            model = fit_logistic(col['reserve'][train], y[train], l2)
            scores[l2] = _nll(r_of(model, col['reserve'][valid]), y[valid]) if valid.any() else 0.0
        chosen = min(L2_GRID, key=lambda l2: (scores[l2], -l2))
        models[child] = fit_logistic(col['reserve'][train], y[train], chosen)
        report[child] = dict(l2=chosen, validationNll={str(k): v for k, v in scores.items()},
                             rModelSha256=model_sha256(models[child]))
    evaluation = {}
    for s, split in enumerate(SPLITS):
        for cohort in COHORTS:
            m = (col['split'] == s) & (col['cohort'] == cohort)
            if not m.any():
                continue
            label, p, reserve = col['label'][m], col['p'][m], col['reserve'][m]
            child = 'standard' if cohort == 'brew' else 'fast'
            r = r_of(models[child], reserve)
            base = (col['label'][(col['split'] == 0) & (col['child'] == child) & fired] == 1).mean()
            f = label > 0
            q = 1 - p
            classes = np.stack((p, q * r, q * (1 - r)), 1)
            evaluation[f'{split}/{cohort}'] = dict(
                rows=int(m.sum()), tailFired=int(f.sum()), observedTailRate=float(f.mean()), meanQ=float(q.mean()),
                rNll=dict(model=_nll(r[f], (label[f] == 1).astype(float)),
                          constant=_nll(np.full(f.sum(), base), (label[f] == 1).astype(float))),
                classNll=float(-np.log(np.clip(classes[np.arange(len(label)), label], 1e-12, None)).mean()))
    out.mkdir(parents=True)
    receipt = dict(schema='ctm_lizard_fit_v1', features=[dict(path=str(p), sha256=e.sha256(p)) for p in features],
                   rModels=models, children=report, evaluation=evaluation,
                   rule='r per child on Tail-fired rows; L2 on the standardized slope chosen on VALIDATION; q = 1 - pOrdinaryWin')
    (out / 'fit.json').write_text(json.dumps(receipt, indent=2, sort_keys=True))
    return receipt


def read_header(path):
    data = Path(path).read_bytes()
    if not data.startswith(MAGIC):
        raise ValueError('not a combat transition runtime artifact')
    version, length = struct.unpack_from('<II', data, len(MAGIC))
    offset = len(MAGIC) + 8
    return version, json.loads(data[offset:offset + length]), data[offset + length:]


def extend(artifact, fit_json, out, fast_r=False, brew=False, fairy=False):
    """Writes the Lizard capabilities (and with fast_r the refitted fast r) into a candidate
    fast artifact. Tensors are untouched; only the JSON header changes."""
    if not (fast_r or brew or fairy):
        raise ValueError('nothing to extend')
    version, header, body = read_header(artifact)
    if 'researchCandidate' not in header:
        raise ValueError('only a research candidate may carry a capability')
    lizard = header.get('activeLizardCorrection')
    if lizard is None:
        raise ValueError('Lizard capabilities need an active-Lizard (fast) artifact')
    capabilities = dict(header.get('capabilities', {}))
    if (brew and 'lizardBrew' in capabilities) or (fairy and 'lizardFairy' in capabilities):
        raise ValueError('artifact already has that Lizard capability')
    receipt = json.loads(Path(fit_json).read_text())
    if receipt.get('schema') != 'ctm_lizard_fit_v1':
        raise ValueError('not a ctm_lizard fit receipt')
    if brew:
        capabilities['lizardBrew'] = {'rModel': receipt['rModels']['standard']}
    if fairy:
        capabilities['lizardFairy'] = {}
    header = dict(header, capabilities=capabilities)
    if fast_r:
        model = receipt['rModels']['fast']
        header['activeLizardCorrection'] = dict(lizard, rModel=model, rModelSha256=model_sha256(model),
                                                frozenQrArtifactSha256=e.sha256(fit_json))
    encoded = json.dumps(header).encode()
    with open(out, 'xb') as stream:
        stream.write(MAGIC + struct.pack('<II', version, len(encoded)) + encoded + body)
    corrected = header['activeLizardCorrection']
    return dict(artifact=str(out), artifactSha256=e.sha256(out), baseArtifactSha256=e.sha256(artifact),
                manifest=dict(capabilities=dict(fast=capabilities),
                              activeLizard={k: corrected[k] for k in (
                                  'candidateId', 'candidateManifestSha256', 'frozenQrArtifactSha256',
                                  'rModelSha256', 'rModel')}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('fit')
    p.add_argument('--features', type=Path, nargs='+', required=True)
    p.add_argument('--out', type=Path, required=True)
    p = sub.add_parser('extend')
    p.add_argument('--artifact', type=Path, required=True)
    p.add_argument('--fit', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--fast-r', action='store_true', help='replace the fast r with the refit')
    p.add_argument('--brew', action='store_true', help='lizardBrew: route Brew states to the standard child')
    p.add_argument('--fairy', action='store_true', help='lizardFairy: compose a Fairy Potion before the Tail')
    args = parser.parse_args(argv)
    if args.command == 'fit':
        result = fit(args.features, args.out)
        result = dict(children=result['children'], evaluation=result['evaluation'])
    else:
        result = extend(args.artifact, args.fit, args.out, args.fast_r, args.brew, args.fairy)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
