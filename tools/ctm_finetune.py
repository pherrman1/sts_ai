#!/usr/bin/env python3
"""Warm-start fine-tune of the A20 fast CTM (pathb-a20 DeepSets) on recorded real combats (research).

The deployed fast artifact (combat_transition_deepsets_pathb_a20_lizard.native) was trained on combats of the
2026-10-12 Stage-1 teacher (§443). Today's Silver loses less HP late in the run (ctm_calibration_20261023). This
tool continues training two parts of that artifact on combat_transition_row_v2 rows of current play:

* survival: the survival encoder (its own DeepSets weights) and its 1x64 head, all weights;
* HP: only the HP head (delta embedding, 73 -> 64 -> classes MLP). The HP encoder z is frozen because maxHP
  (a weight twin), relic, gold and ritual heads read the same z.

Everything else (maxHP, potion, relic, gold, ritual, writhing, escape, Lizard metadata) is copied byte for byte.
Both losses carry an L2 pull towards the base weights (L2-SP). Old rows (e.g. the Stage-1 corpus) can be mixed in
at a fixed share of each batch so rare fights keep their coverage.

  encode  OUT.npz ROWS.jsonl[:SCORES.csv] ...       rows -> arrays (SCORES: ctmscorerows of the same rows; only
                                                    rows it scored are kept, else all rows with a transition)
  train   --base ART --base-sha SHA --new NEW.npz [--old OLD.npz --old-share F] [--seeds even|odd|all] --out DIR
  export  --base ART --base-sha SHA --checkpoint DIR/finetune.pt --out NEW.native --manifest-out MANIFEST.json

`export` writes a research-candidate artifact under candidate id pathb-a20 and a ctm_research_candidate_v3
manifest (the built-in A20 manifest with the new fast artifact and checkpoint hashes; without the §470 boss shift,
since a survival fine-tune learns boss deaths directly, unless --keep-boss-shift). Load it with STS_CTM_RESEARCH_CANDIDATE_MANIFEST(+_SHA256); the
Act-4 survival model and STS_CTM_CALIBRATION still apply to it, as to the deployed stack.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import combat_transition_model_experiment as experiment  # noqa: E402
from tools import ctm_escape  # noqa: E402

LIZARD_TAIL = 'LIZARD_TAIL'
SEED = 20261023
INPUT_KEYS = ('globals_continuous', 'global_categories', 'cards', 'relics', 'potions', 'card_mask', 'relic_mask')
SURVIVAL_PREFIX = 'survival.'
HP_HEAD = ('hp.delta_embedding.weight', 'hp.hp.0.weight', 'hp.hp.0.bias', 'hp.hp.2.weight', 'hp.hp.2.bias')
MAX_HP_DELTAS = (0, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _enum_index(header, array, name):
    import re
    text = (ROOT / header).read_text()
    body = re.search(array + r'\[\]\s*(?:=\s*)?\{(.*?)\};', text, re.S).group(1)
    return [n.strip().strip('"') for n in body.split(',') if n.strip()].index(name)


def _read_scored(path):
    import csv
    with open(path, newline='') as stream:
        return [(int(r['source_seed']), int(r['fight_idx']), r['scored'] == '1') for r in csv.DictReader(stream)]


def encode(out, specs):
    """Arrays of every usable row: model inputs, labels and the fields the training masks need."""
    tail = _enum_index('include/constants/Relics.h', 'relicEnumNames', LIZARD_TAIL)
    brew = _enum_index('include/constants/Potions.h', 'potionEnumNames', 'ENTROPIC_BREW')
    lists = {key: [] for key in INPUT_KEYS}
    meta = {key: [] for key in ('seed', 'fight', 'act', 'room', 'encounter', 'win', 'pre_hp', 'post_hp',
                                'post_max_hp', 'delta', 'escaped', 'eligible', 'boss', 'brew', 'lizard', 'source')}
    sources = []
    for source, spec in enumerate(specs):
        rows_path, _, scores_path = spec.partition(':')
        scored = _read_scored(scores_path) if scores_path else None
        sources.append(dict(rows=rows_path, rowsSha256=sha256(rows_path),
                            scores=scores_path or None, scoresSha256=sha256(scores_path) if scores_path else None))
        with open(rows_path) as stream:
            for index, line in enumerate(stream):
                row = json.loads(line)
                if scored is not None:
                    seed, fight, ok = scored[index]
                    assert (seed, fight) == (int(row['sourceSeed']), int(row['fightIdx'])), 'rows and scores differ'
                    if not ok:
                        continue
                t = row['transition']
                if t is None or int(t['combatOutcome']) not in (experiment.WIN, experiment.DEATH):
                    continue
                g, gc, c, r, p, cm, rm, win, _, context = experiment._encode_row(row)
                for key, value in zip(INPUT_KEYS, (g, gc, c, r, p, cm, rm)):
                    lists[key].append(value)
                pre, post, pi = t['pre'], t['post'], row['predictorInput']
                boss = row['roomClass'] == 'BOSS'
                capacity = int(pi['globals']['potionCapacity'])
                potions = [int(q['potionId']) for q in sorted(pi['potions'], key=lambda q: int(q['slot']))]
                eligible = ctm_escape.eligible(potions, capacity, boss)
                delta = int(post['maxHp']) - int(pre['maxHp'])
                values = dict(seed=int(row['sourceSeed']), fight=int(row['fightIdx']), act=int(row['act']),
                              room=['NORMAL', 'ELITE', 'BOSS'].index(row['roomClass'])
                              if row['roomClass'] in ('NORMAL', 'ELITE', 'BOSS') else 3,
                              encounter=int(row['encounter']), win=int(win), pre_hp=int(pre['curHp']),
                              post_hp=int(post['curHp']), post_max_hp=int(post['maxHp']),
                              delta=MAX_HP_DELTAS.index(delta) if delta in MAX_HP_DELTAS else -1,
                              escaped=int(bool(post.get('smokeBombUsed')) and eligible), eligible=int(eligible),
                              boss=int(boss), brew=int(brew in potions[:capacity]),
                              lizard=int(any(int(x['id']) == tail and int(x['data']) == 1 for x in pre['relics'])),
                              source=source)
                for key, value in values.items():
                    meta[key].append(value)
    arrays = {key: np.stack(value) for key, value in lists.items()}
    arrays.update({key: np.asarray(value, np.int64) for key, value in meta.items()})
    np.savez_compressed(out, **arrays)
    report = dict(rows=int(len(arrays['seed'])), deaths=int((arrays['win'] == 0).sum()),
                  brew=int(arrays['brew'].sum()), lizard=int(arrays['lizard'].sum()), sources=sources)
    Path(str(out) + '.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


def _load(path, seeds):
    data = dict(np.load(path))
    keep = np.ones(len(data['seed']), bool)
    if seeds in ('even', 'odd'):
        keep = data['seed'] % 2 == (seeds == 'odd')
    # Brew rows are routed to the standard child and active-Lizard rows to the composition: neither is a plain
    # fast-child prediction, so the fine-tune leaves them out.
    keep &= (data['brew'] == 0) & (data['lizard'] == 0)
    return {key: value[keep] for key, value in data.items()}


def _inner_split(seeds):
    """About 10% of the training fold's source seeds pick the epoch (never the test fold)."""
    return np.asarray([hashlib.sha256(f'ctm-finetune:{int(s)}'.encode()).digest()[0] < 26 for s in seeds])


class Model:
    def __init__(self, torch, tensors, freeze_encoder=False):
        from tools import ctm_artifact_torch
        self.torch = torch
        with torch.random.fork_rng(devices=[]):
            self.encoder = ctm_artifact_torch._encoder(tensors, 'survival.encoder.')
            self.head = ctm_artifact_torch._load(torch.nn.Linear(64, 1), tensors, 'survival.survival.')
            self.hp_encoder = ctm_artifact_torch._encoder(tensors, 'hp.encoder.')
        self.freeze_encoder = freeze_encoder
        self.encoder.requires_grad_(not freeze_encoder).train()
        self.head.requires_grad_(True).train()
        self.hp = {name: torch.tensor(tensors[name], requires_grad=True) for name in HP_HEAD}
        self.base = {name: p.detach().clone() for name, p in self.named()}

    def named(self):
        if not self.freeze_encoder:
            for name, p in self.encoder.named_parameters():
                yield 'survival.encoder.' + name, p
        for name, p in self.head.named_parameters():
            yield 'survival.survival.' + name, p
        yield from self.hp.items()

    def survival_logit(self, inputs):
        return self.head(self.encoder(*inputs)).flatten()

    def hp_logits(self, z, delta, escaped):
        p = self.hp
        x = self.torch.cat((z, p['hp.delta_embedding.weight'][delta], escaped[:, None]), -1)
        hidden = self.torch.relu(x @ p['hp.hp.0.weight'].T + p['hp.hp.0.bias'])
        return hidden @ p['hp.hp.2.weight'].T + p['hp.hp.2.bias']

    def l2sp(self, survival_weight, hp_weight):
        total_s = sum(((p - self.base[n]) ** 2).sum() for n, p in self.named() if n.startswith(SURVIVAL_PREFIX))
        total_h = sum(((p - self.base[n]) ** 2).sum() for n, p in self.named() if n in HP_HEAD)
        return survival_weight * total_s + hp_weight * total_h

    def tensors(self):
        return {name: p.detach().cpu().numpy().astype(np.float32) for name, p in self.named()}


def _inputs(torch, data, index):
    from tools import combat_transition_surrogate as surrogate
    return surrogate._torch_inputs(data, index, 'cpu', torch, trim_padding=True)


def _hp_targets(data, classes):
    hp_class = data['post_hp'] - data['pre_hp'] - classes[0]
    ok = ((data['win'] == 1) & (data['delta'] >= 0) & (hp_class >= 0) & (hp_class < len(classes))
          & (data['post_hp'] >= 1) & (data['post_hp'] <= data['post_max_hp']))
    return hp_class, ok


def _z(model, torch, data, batch=4096):
    with torch.no_grad():
        return torch.cat([model.hp_encoder(*_inputs(torch, data, np.arange(s, min(s + batch, len(data['seed'])))))
                          for s in range(0, len(data['seed']), batch)]).float()


class Losses:
    """Survival BCE and HP NLL of one data set, with the frozen HP encodings computed once."""

    def __init__(self, torch, model, data, classes):
        self.torch, self.data = torch, data
        self.z = _z(model, torch, data)
        self.hp_class, self.hp_ok = _hp_targets(data, classes)
        post = torch.as_tensor(data['pre_hp'])[:, None] + torch.as_tensor(classes)[None]
        self.legal = (post >= 1) & (post <= torch.as_tensor(data['post_max_hp'])[:, None])
        self.win = torch.as_tensor(data['win'], dtype=torch.float32)

    def survival(self, model, index):
        logit = model.survival_logit(_inputs(self.torch, self.data, index))
        return self.torch.nn.functional.binary_cross_entropy_with_logits(logit, self.win[index], reduction='none')

    def hp(self, model, index):
        index = index[self.hp_ok[index]]
        if len(index) == 0:
            return self.torch.zeros(0)
        t = self.torch
        logits = model.hp_logits(self.z[index], t.as_tensor(self.data['delta'][index]),
                                 t.as_tensor(self.data['escaped'][index], dtype=t.float32))
        logits = logits.masked_fill(~self.legal[index], -t.inf)
        return -t.log_softmax(logits, -1).gather(1, t.as_tensor(self.hp_class[index])[:, None])[:, 0]

    def score(self, model, index, batch=4096):
        with self.torch.no_grad():
            s = self.torch.cat([self.survival(model, index[i:i + batch]) for i in range(0, len(index), batch)])
            h = self.torch.cat([self.hp(model, index[i:i + batch]) for i in range(0, len(index), batch)])
        return dict(survivalNll=float(s.mean()), hpNll=float(h.mean()) if len(h) else None,
                    rows=int(len(index)), hpRows=int(len(h)))


def train(args):
    import torch
    torch.manual_seed(SEED)
    torch.set_num_threads(args.threads)
    out = Path(args.out)
    if out.exists():
        raise ValueError(f'refusing to overwrite {out}')
    if sha256(args.base) != args.base_sha:
        raise ValueError('base artifact SHA256 differs')
    metadata, tensors = ctm_escape.read_artifact(args.base)
    classes = np.asarray(metadata['hpClasses'], np.int64)
    model = Model(torch, tensors, args.survival_head_only)
    new = _load(args.new, args.seeds)
    inner = _inner_split(new['seed'])
    sets = {'new': Losses(torch, model, new, classes)}
    train_ids = {'new': np.flatnonzero(~inner)}
    valid_ids = np.flatnonzero(inner)
    if args.old:
        old = _load(args.old, 'all')
        sets['old'] = Losses(torch, model, old, classes)
        old_inner = _inner_split(old['seed'])
        train_ids['old'] = np.flatnonzero(~old_inner)
        old_valid = np.flatnonzero(old_inner)
    named = list(model.named())
    opt = torch.optim.Adam([dict(params=[p for n, p in named if n.startswith(SURVIVAL_PREFIX)], lr=args.lr),
                            dict(params=[p for n, p in named if n in HP_HEAD], lr=args.hp_lr or args.lr)])
    rng = np.random.default_rng(SEED)

    def evaluate():
        model.encoder.eval()
        result = dict(new=sets['new'].score(model, valid_ids))
        if args.old:
            result['old'] = sets['old'].score(model, old_valid)
        model.encoder.train()
        return result

    # The survival and HP parameters are disjoint and their losses independent, so each part keeps its own best
    # epoch on the inner validation rows.
    history = [dict(epoch=0, **evaluate())]
    best = {part: (history[0]['new'][key], 0, model.tensors()) for part, key in (('survival', 'survivalNll'),
                                                                                  ('hp', 'hpNll'))}
    old_per_batch = int(round(args.batch * args.old_share)) if args.old else 0
    new_per_batch = args.batch - old_per_batch
    steps = int(np.ceil(len(train_ids['new']) / new_per_batch))
    l2_s, l2_h = args.l2sp / len(train_ids['new']), args.l2sp_hp / len(train_ids['new'])
    for epoch in range(1, args.epochs + 1):
        order = rng.permutation(train_ids['new'])
        for step in range(steps):
            index = order[step * new_per_batch:(step + 1) * new_per_batch]
            opt.zero_grad()
            loss = sets['new'].survival(model, index).sum()
            hp = sets['new'].hp(model, index).sum()
            count = len(index)
            if old_per_batch:
                old_index = rng.choice(train_ids['old'], old_per_batch, replace=False)
                loss = loss + sets['old'].survival(model, old_index).sum()
                hp = hp + sets['old'].hp(model, old_index).sum()
                count += old_per_batch
            total = (loss + hp) / count + model.l2sp(l2_s, l2_h)
            total.backward()
            opt.step()
        record = dict(epoch=epoch, **evaluate())
        history.append(record)
        print(json.dumps(record, sort_keys=True), file=sys.stderr, flush=True)
        for part, key in (('survival', 'survivalNll'), ('hp', 'hpNll')):
            if record['new'][key] < best[part][0]:
                best[part] = (record['new'][key], epoch, model.tensors())
    chosen = {name: value for name, value in best['survival'][2].items() if name.startswith(SURVIVAL_PREFIX)}
    chosen.update({name: best['hp'][2][name] for name in HP_HEAD})
    out.mkdir(parents=True)
    torch.save(dict(tensors=chosen, baseArtifactSha256=args.base_sha), out / 'finetune.pt')
    receipt = dict(schema='ctm_finetune_v1', baseArtifactSha256=args.base_sha,
                   newData=dict(path=str(args.new), sha256=sha256(args.new), seeds=args.seeds,
                                trainRows=int(len(train_ids['new'])), innerValidationRows=int(len(valid_ids))),
                   oldData=dict(path=str(args.old), sha256=sha256(args.old), share=args.old_share,
                                trainRows=int(len(train_ids['old']))) if args.old else None,
                   lr=args.lr, hpLr=args.hp_lr or args.lr, survivalHeadOnly=args.survival_head_only, epochs=args.epochs, batch=args.batch, l2sp=args.l2sp,
                   l2spHp=args.l2sp_hp, seed=SEED, threads=args.threads,
                   selectedEpoch=dict(survival=best['survival'][1], hp=best['hp'][1]),
                   checkpointSha256=sha256(out / 'finetune.pt'), history=history,
                   torch=torch.__version__, numpy=np.__version__)
    (out / 'fit.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    return dict(selectedEpoch=receipt['selectedEpoch'], checkpointSha256=receipt['checkpointSha256'],
                innerValidation=dict(survivalNll=best['survival'][0], hpNll=best['hp'][0], before=history[0]['new']))


def export(args):
    import torch
    sys.path.insert(0, str(ROOT))
    if sha256(args.base) != args.base_sha:
        raise ValueError('base artifact SHA256 differs')
    metadata, tensors = ctm_escape.read_artifact(args.base)
    if metadata.get('researchCandidate') != {'candidateId': 'pathb-a20'}:
        raise ValueError('base is not a pathb-a20 fast artifact')
    payload = torch.load(args.checkpoint, map_location='cpu', weights_only=False)
    if payload['baseArtifactSha256'] != args.base_sha:
        raise ValueError('fine-tune was made on a different artifact')
    checkpoint = sha256(args.checkpoint)
    fitted = payload['tensors']
    for name, value in fitted.items():
        if name not in tensors or tensors[name].shape != value.shape:
            raise ValueError(f'tensor {name} differs from the base')
        if not (name.startswith(SURVIVAL_PREFIX) or name in HP_HEAD):
            raise ValueError(f'tensor {name} is not fine-tuned')
    tensors.update({name: np.asarray(value, np.float32) for name, value in fitted.items()})
    metadata = copy.deepcopy(metadata)
    metadata['experimentalSurvival']['checkpointSha256'] = checkpoint
    metadata['experimentalDeepSets']['maxHpHpCheckpointSha256'] = checkpoint
    metadata['sources'].update(survival=checkpoint, HP=checkpoint, maxHP=checkpoint)
    metadata['ctmFinetune'] = dict(baseArtifactSha256=args.base_sha, checkpointSha256=checkpoint,
                                   tensors=sorted(fitted))
    out = Path(args.out)
    ctm_escape.write_artifact(out, metadata, tensors)
    manifest = json.loads(_embedded_a20_manifest())
    if not args.keep_boss_shift:
        manifest.pop('bossSurvivalLogitShift', None)
    manifest['fast']['artifactSha256'] = sha256(out)
    manifest['fast']['survival']['checkpointSha256'] = checkpoint
    manifest['fast']['maxHpHpCheckpointSha256'] = checkpoint
    Path(args.manifest_out).write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    return dict(artifact=str(out), artifactSha256=sha256(out), manifest=str(args.manifest_out),
                manifestSha256=sha256(args.manifest_out), checkpointSha256=checkpoint)


def _embedded_a20_manifest():
    """The built-in pathb-a20 manifest (kA20CandidateManifest) from the runtime source."""
    text = (ROOT / 'apps/one_combat/combat_transition_runtime.cpp').read_text()
    start = text.index('kA20CandidateManifest[]=R"json(') + len('kA20CandidateManifest[]=R"json(')
    body = text[start:text.index(')json"', start)]
    expected = text[text.index('kA20CandidateManifestSha256[]="') + 31:][:64]
    if hashlib.sha256(body.encode()).hexdigest() != expected:
        raise ValueError('embedded A20 manifest hash differs')
    return body


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('encode')
    p.add_argument('out', type=Path)
    p.add_argument('specs', nargs='+')
    p = sub.add_parser('train')
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--base-sha', required=True)
    p.add_argument('--new', type=Path, required=True)
    p.add_argument('--old', type=Path)
    p.add_argument('--old-share', type=float, default=0.25)
    p.add_argument('--seeds', choices=('even', 'odd', 'all'), default='all')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--lr', type=float, default=3e-4)
    p.add_argument('--hp-lr', type=float, help='learning rate of the HP head (default: --lr)')
    p.add_argument('--survival-head-only', action='store_true', help='freeze the survival encoder')
    p.add_argument('--epochs', type=int, default=8)
    p.add_argument('--batch', type=int, default=512)
    p.add_argument('--l2sp', type=float, default=1.0, help='L2-SP on survival weights, per training row')
    p.add_argument('--l2sp-hp', type=float, default=1.0, help='L2-SP on HP head weights, per training row')
    p.add_argument('--threads', type=int, default=4)
    p = sub.add_parser('export')
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--base-sha', required=True)
    p.add_argument('--checkpoint', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--manifest-out', type=Path, required=True)
    p.add_argument('--keep-boss-shift', action='store_true',
                   help="keep the §470 boss shift (for a fine-tune that leaves survival unchanged)")
    args = parser.parse_args(argv)
    if args.command == 'encode':
        result = encode(args.out, args.specs)
    elif args.command == 'train':
        result = train(args)
    else:
        result = export(args)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
