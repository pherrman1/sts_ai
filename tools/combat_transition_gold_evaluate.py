#!/usr/bin/env python3
"""Frozen source-grouped development of the new gold component only.

Prepare audits the native event closure before fitting. Fit is a bounded small
decoder fit; it never trains encoders or upstream heads. Qualification and any
large refit require an independently reviewed implementation receipt.
"""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import subprocess
import time
import numpy as np
import torch
from tools import combat_transition_composed as c
from tools import combat_transition_composed_evaluate as e
from tools import combat_transition_gold as g
from tools.combat_transition_gold_audit import audit_without_gold_gate

RECIPE = dict(schema='shared_native_gold_v1', seed=20260912, epochs=12,
              batch=512, lr=.001, weightDecay=.0001, gradientClip=1.,
              selection='earliest strict minimum original VALIDATION NLL',
              training='new shared categorical scorer only; original TRAIN victories',
              encoder='frozen qualified HP encoder, historical AMP arithmetic',
              upstream='all historical encoders/heads frozen',
              fields=g.MECHANICAL_FIELDS, candidates=g.CANDIDATE_FIELDS,
              draws=32, samplingSeed=20260918, exposureThreshold=.1,
              transmutationPlus='shared upgradedHoGSource condition; two TEST rows diagnostic only',
              goldExposure='32 upstream draws with exact conditional marginal over legal potion masks',
              hardValidity='32 complete ancestral draws per gold-only TEST row; death short-circuits')


def dump(path, value):
    c.base.json_dump(path, value)


def prepare(folder):
    if folder.exists():
        raise ValueError('refusing to overwrite frozen gold preparation')
    hashes = e.verify_data()
    arrays, _ = c.base._load_prepared(e.PREPARED)
    m = c.FrozenModels('cpu')
    selected = []; records = []; counts = Counter(); native_rows = []
    test_rows = []
    relevant_ids = {c.base._POTION_IDS[n] for n in ('COLORLESS_POTION', 'SKILL_POTION', 'BLESSING_OF_THE_FORGE')}
    for index, row in enumerate(c.base.iter_rows(e.CORPUS)):
        counts['corpusRows'] += 1
        if (row['sourceSeed'], row['fightIdx']) != (int(arrays['sourceSeed'][index]), int(arrays['fightIdx'][index])):
            raise ValueError('original corpus identity mismatch')
        pre, post, pi = row['transition']['pre'], row['transition']['post'], row['predictorInput']
        reasons = c.full_support_reasons(pre, pi, m)
        if not reasons or not all(g.gold_reason(r) for r in reasons):
            continue
        with audit_without_gold_gate():
            if c.full_support_reasons(pre, pi, m):
                raise ValueError('later support rejection')
        masks = c.potion.legal_masks(np.asarray([pre['potions']]), np.asarray([pre['potionCapacity']]))[0]
        relevant = sum(1 << slot for slot, p in enumerate(pre['potions']) if p in relevant_ids)
        effects = {int(mask) & relevant for mask in np.flatnonzero(masks)}
        effect_mechanics = {effect: g.mechanics(pi, pre, effect) for effect in effects}
        by_mask = np.empty((32, len(g.MECHANICAL_FIELDS)), np.float32)
        modes = np.zeros(32, np.int8)
        for mask in range(32):
            mode, mechanical = effect_mechanics.get(mask & relevant, effect_mechanics[0])
            by_mask[mask] = mechanical; modes[mask] = mode
        name, asc = g.encounter_name(pi['globals']['encounter']), pi['globals']['ascension']
        mode_posts = {mode: g.native_posts(pre['gold'], name, asc, int(mode)) for mode in set(modes[masks].tolist())}
        posts = sorted(set().union(*map(set, mode_posts.values())))
        legal = np.zeros((4, len(posts)), bool)
        for mode, values in mode_posts.items():
            legal[mode] = [p in values for p in posts]
        win = row['transition']['combatOutcome'] == c.base.WIN
        mask = 0; target = 0; max_delta = 0; signed = 0
        if win:
            mask = int(c.potion.encode_masks(np.asarray([pre['potions']]), np.asarray([post['potions']]), np.asarray([pre['potionCapacity']]))[0])
            pair = (post['gold'], post['stolenGold'])
            if pair not in mode_posts[int(modes[mask])]:
                raise ValueError(f'native gold target outside event closure: index={index}, source={row["sourceSeed"]}, fight={row["fightIdx"]}, name={name}, preGold={pre["gold"]}, mask={mask}, mode={modes[mask]}, target={pair}')
            target = posts.index(pair)
            differences = c.base._copy_through_violations(pre, post)
            if any(v not in ('gold', 'stolenGold') for v in differences):
                raise ValueError('unsupported non-gold copy-through mutation')
            if pre['smokeBombUsed'] != post['smokeBombUsed']:
                raise ValueError('unmodeled escape')
            if c.native_rng.replay_misc(pre['combatRng'][2], name) != post['combatRng'][2] or pre['combatRng'][4] != post['combatRng'][4]:
                raise ValueError('inherited RNG mismatch')
            c.relic.trajectory_constraints(pre['relics'], post['relics'], pi['globals']['encounter'], any(r['id'] == c.base._RELIC_IDS['MARK_OF_THE_BLOOM'] for r in pre['relics']))
            max_delta = np.flatnonzero(m.delta_values == post['maxHp'] - pre['maxHp'])
            if len(max_delta) != 1:
                raise ValueError('maxHP target outside frozen class domain')
            max_delta = int(max_delta[0]); signed = post['curHp'] - pre['curHp']
            if signed not in m.classes:
                raise ValueError('HP target outside frozen class domain')
        local = len(selected); selected.append(index)
        records.append(dict(win=win, split=int(arrays['split_id'][index]), source=row['sourceSeed'], fight=row['fightIdx'],
                            preHp=pre['curHp'], preMaxHp=pre['maxHp'], preGold=pre['gold'],
                            trueHp=post['curHp'], trueMaxHp=post['maxHp'], trueMask=mask,
                            trueDeltaClass=max_delta, trueSigned=signed, target=target,
                            prePotions=pre['potions'], capacity=pre['potionCapacity']))
        native_rows.append((np.asarray(posts, np.int64), legal, by_mask, modes, masks))
        if arrays['split_id'][index] == 2:
            test_rows.append(dict(index=index, local=local, source=row['sourceSeed'], fight=row['fightIdx'],
                                  pre=pre, post=post, predictorInput=pi, win=win, reasons=reasons,
                                  transmutationPlus=any(x['cardId'] == g.b._CARD_IDS['TRANSMUTATION'] and x['upgraded'] for x in pi['cards'])))
        if len(selected) % 10000 == 0:
            print(f'gold native audit {len(selected)}/71367', flush=True)
    if counts['corpusRows'] != 510030 or len(selected) != 71367 or len(test_rows) != 7301:
        raise ValueError('frozen gold cohort counts differ')
    n = len(selected); width = max(len(v[0]) for v in native_rows)
    cache = {key: np.asarray([r[key] for r in records]) for key in records[0]}
    cache.update(ids=np.asarray(selected), posts=np.zeros((n, width, 2), np.int64),
                 candidateFeatures=np.zeros((n, width, len(g.CANDIDATE_FIELDS)), np.float32),
                 legal=np.zeros((n, 4, width), bool), mechanical=np.stack([v[2] for v in native_rows]),
                 modes=np.stack([v[3] for v in native_rows]), masksAllowed=np.stack([v[4] for v in native_rows]))
    for i, (posts, legal, _, _, _) in enumerate(native_rows):
        cache['posts'][i, :len(posts)] = posts
        cache['candidateFeatures'][i, :len(posts)] = g.candidate_features(posts, int(cache['preGold'][i]))
        cache['legal'][i, :, :len(posts)] = legal
    del native_rows, records
    torch.set_num_threads(4); m.to('cuda')
    cache['z'] = np.zeros((n, 64), np.float32)
    winners = np.arange(n)  # visible encodings must also exist for true deaths
    with torch.inference_mode():
        for start in range(0, len(winners), 512):
            ids = winners[start:start + 512]
            inputs = c.base._torch_inputs(arrays, cache['ids'][ids], 'cuda', torch, trim_padding=True)
            cache['z'][ids] = m.hp_encoding(inputs).cpu().numpy()
            if start % 10240 == 0:
                print(f'gold frozen encoding {start}/{len(winners)}', flush=True)
    folder.mkdir(parents=True)
    np.savez_compressed(folder / 'cache.npz', **cache)
    with (folder / 'test_rows.jsonl').open('w') as stream:
        for row in test_rows:
            stream.write(json.dumps(row) + '\n')
    metadata = dict(baseline=e.snapshot(), hashes=hashes, candidateWidth=width,
                    counts={k: dict(rows=int((cache['split'] == i).sum()), victories=int(((cache['split'] == i) & cache['win']).sum())) for i, k in enumerate(('train', 'validation', 'test'))},
                    nativeTargetViolations=0, otherPersistentViolations=0, inheritedRngViolations=0,
                    cacheSha256=c.base.sha256(folder / 'cache.npz'), testRowsSha256=c.base.sha256(folder / 'test_rows.jsonl'))
    dump(folder / 'preflight.json', metadata); dump(folder / 'recipe.json', RECIPE)
    print(json.dumps(metadata), flush=True)


def load_cache(folder):
    metadata = json.loads((folder / 'preflight.json').read_text())
    if e.verify_data() != metadata['hashes'] or c.base.sha256(folder / 'cache.npz') != metadata['cacheSha256'] or c.base.sha256(folder / 'test_rows.jsonl') != metadata['testRowsSha256'] or json.loads((folder / 'recipe.json').read_text()) != json.loads(json.dumps(RECIPE)):
        raise ValueError('frozen gold inputs changed')
    with np.load(folder / 'cache.npz') as raw:
        cache = {k: raw[k] for k in raw.files}
    return cache, metadata


def hp_conditions(cache, ids, ending=None, maximum=None):
    ending = cache['trueHp'][ids] if ending is None else ending
    maximum = cache['trueMaxHp'][ids] if maximum is None else maximum
    return np.stack(((ending - cache['preHp'][ids]) / 160, ending / maximum,
                     (maximum - cache['preMaxHp'][ids]) / 10), -1).astype(np.float32)


def forward(net, cache, ids, masks=None, ending=None, maximum=None):
    masks = cache['trueMask'][ids] if masks is None else np.asarray(masks, np.int64)
    modes = cache['modes'][ids, masks]
    values = (cache['z'][ids], cache['mechanical'][ids, masks], hp_conditions(cache, ids, ending, maximum),
              c.potion.BITS[masks].astype(np.float32), cache['candidateFeatures'][ids], cache['legal'][ids, modes])
    device = next(net.parameters()).device
    return net(*(torch.as_tensor(v, device=device) for v in values))


def score(net, cache, ids):
    values = []
    with torch.inference_mode():
        for start in range(0, len(ids), 512):
            sub = ids[start:start + 512]
            logp = forward(net, cache, sub)
            values.append(-logp[torch.arange(len(sub), device=logp.device), torch.as_tensor(cache['target'][sub], device=logp.device)].cpu().numpy())
    return float(np.concatenate(values).mean())


def fit(folder, source_sha):
    if e.snapshot() != source_sha or subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip():
        raise ValueError('bounded decoder fit requires the frozen clean implementation SHA')
    if (folder / 'gold.pt').exists():
        raise ValueError('refusing to overwrite gold fit')
    cache, metadata = load_cache(folder)
    if metadata['baseline'] != source_sha:
        raise ValueError('preparation implementation SHA differs')
    train = np.flatnonzero((cache['split'] == 0) & cache['win'])
    validation = np.flatnonzero((cache['split'] == 1) & cache['win'])
    torch.set_num_threads(4)
    net = g.new_decoder(torch).cuda()
    optimizer = torch.optim.AdamW(net.parameters(), lr=RECIPE['lr'], weight_decay=RECIPE['weightDecay'])
    rng = np.random.default_rng(RECIPE['seed']); history = []; best = float('inf'); started = time.monotonic()
    for epoch in range(RECIPE['epochs']):
        shuffled = rng.permutation(train); total = 0
        net.train()
        for start in range(0, len(shuffled), RECIPE['batch']):
            ids = shuffled[start:start + RECIPE['batch']]
            optimizer.zero_grad(set_to_none=True)
            logp = forward(net, cache, ids)
            loss = -logp[torch.arange(len(ids), device='cuda'), torch.as_tensor(cache['target'][ids], device='cuda')].mean()
            loss.backward(); torch.nn.utils.clip_grad_norm_(net.parameters(), RECIPE['gradientClip']); optimizer.step()
            total += float(loss.detach()) * len(ids)
        net.eval(); value = score(net, cache, validation)
        entry = dict(epoch=epoch + 1, trainNll=total / len(train), validationNll=value)
        history.append(entry); print(json.dumps(entry), flush=True)
        if value < best:
            best = value; selection = epoch + 1; weights = copy.deepcopy(net.cpu().state_dict()); net.cuda()
    torch.save(dict(schema=RECIPE['schema'], stateDict=weights, recipe=RECIPE, metadata=metadata,
                    sourceSha=source_sha, selectionEpoch=selection, history=history), folder / 'gold.pt')
    dump(folder / 'fit.json', dict(sourceSha=source_sha, independentReview=False,
                                 classification='BOUNDED_GOLD_DECODER_FIT_NOT_QUALIFICATION',
                                 trainRows=len(train), validationRows=len(validation),
                                 selectionEpoch=selection, history=history, elapsedSeconds=time.monotonic() - started,
                                 artifactSha256=c.base.sha256(folder / 'gold.pt'), upstreamHashesUnchanged=e.verify_data() == metadata['hashes']))


def summarize_component(p, cache, ids):
    target = cache['target'][ids]
    posts = cache['posts'][ids]
    true = posts[np.arange(len(ids)), target]
    expected = (p[:, :, None] * posts).sum(1)
    mae = np.abs(expected - true).mean(0)
    return dict(rows=len(ids), jointNll=float((-np.log(p[np.arange(len(ids)), target])).mean()),
                jointBrier=float((np.square(p).sum(-1) - 2 * p[np.arange(len(ids)), target] + 1).mean()),
                modeExact=float((p.argmax(-1) == target).mean()),
                expectedGoldMae=float(mae[0]), expectedStolenGoldMae=float(mae[1]))


def target_probability(net, cache, ids, masks, ending, maximum):
    logp = forward(net, cache, ids, masks, ending, maximum)
    target = torch.as_tensor(cache['target'][ids], device=logp.device)
    return logp[torch.arange(len(ids), device=logp.device), target].exp().cpu().numpy().astype(float)


def diagnose(folder, source_sha):
    """Bounded development diagnostics, not independent final qualification."""
    if e.snapshot() != source_sha or subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip():
        raise ValueError('diagnostics require frozen clean implementation SHA')
    if (folder / 'diagnostics.json').exists():
        raise ValueError('refusing to overwrite development diagnostics')
    cache, metadata = load_cache(folder)
    fitted = json.loads((folder / 'fit.json').read_text())
    if c.base.sha256(folder / 'gold.pt') != fitted['artifactSha256'] or fitted['sourceSha'] != source_sha:
        raise ValueError('fitted gold provenance changed')
    payload = torch.load(folder / 'gold.pt', weights_only=False, map_location='cpu')
    if payload['metadata'] != metadata or payload['recipe'] != RECIPE or payload['sourceSha'] != source_sha:
        raise ValueError('checkpoint binding differs')
    torch.set_num_threads(4)
    net = g.new_decoder(torch).cuda().eval().requires_grad_(False)
    net.load_state_dict(payload['stateDict'], strict=True)
    m = c.FrozenModels('cuda'); arrays, _ = c.base._load_prepared(e.PREPARED)
    rows = [json.loads(line) for line in (folder / 'test_rows.jsonl').read_text().splitlines()]
    test = np.asarray([r['local'] for r in rows], np.int64)
    if len(test) != 7301 or not np.all(cache['split'][test] == 2):
        raise ValueError('TEST row accounting differs')
    victories = test[cache['win'][test]]
    count = len(victories); width = cache['posts'].shape[1]
    gold_p = np.empty((count, width), float)
    z_potion = np.empty((count, 64), np.float32)
    p_delta = np.empty((count, len(m.delta_values)), float)
    hp_teacher = np.empty(count); potion_teacher = np.empty(count); max_teacher = np.empty(count)
    with torch.inference_mode():
        for start in range(0, count, 512):
            sub = victories[start:start + 512]; sl = slice(start, start + len(sub))
            gold_p[sl] = forward(net, cache, sub).exp().cpu().numpy()
            inputs = c.base._torch_inputs(arrays, cache['ids'][sub], 'cuda', torch, trim_padding=True)
            z_potion[sl] = m.fp32_encoding(m.potion_encoder.encoder, inputs).cpu().numpy()
            p_delta[sl] = e.probabilities(m.max_net.max_hp_delta(m.fp32_encoding(m.max_net.encoder, inputs)))
            hp_p = e.hp_prob(m, cache['z'][sub], cache['trueDeltaClass'][sub], cache['preHp'][sub], cache['trueMaxHp'][sub])
            hp_class = cache['trueSigned'][sub] - c.CLASSES[0]
            hp_teacher[sl] = e.nll(hp_p[np.arange(len(sub)), hp_class])
            pp = e.potion_prob(m, z_potion[sl], cache['prePotions'][sub], cache['capacity'][sub], cache['trueDeltaClass'][sub], cache['trueHp'][sub] / cache['trueMaxHp'][sub])
            potion_teacher[sl] = e.nll(pp[np.arange(len(sub)), cache['trueMask'][sub]])
            max_teacher[sl] = e.nll(p_delta[sl][np.arange(len(sub)), cache['trueDeltaClass'][sub]])
    gold_teacher = e.nll(gold_p[np.arange(count), cache['target'][victories]])
    # HP target exposure retains the exact marginal used by #179, not finite
    # empirical target hits. Gold also marginalizes potion masks exactly.
    hp_mass, _ = e.exact_hp_target_probabilities(m, cache['z'][victories], p_delta,
                                                cache['preHp'][victories], cache['preMaxHp'][victories],
                                                cache['trueSigned'][victories] - c.CLASSES[0])
    rng = np.random.default_rng(RECIPE['samplingSeed'])
    gold_mass = np.empty((RECIPE['draws'], count), float)
    potion_mass = np.empty_like(gold_mass)
    with torch.inference_mode():
        for draw in range(RECIPE['draws']):
            for start in range(0, count, 512):
                sub = victories[start:start + 512]; sl = slice(start, start + len(sub))
                delta = e.draw_categories(p_delta[sl], rng)
                maximum = cache['preMaxHp'][sub] + m.delta_values[delta]
                hp_p = e.hp_prob(m, cache['z'][sub], delta, cache['preHp'][sub], maximum)
                ending = cache['preHp'][sub] + c.CLASSES[e.draw_categories(hp_p, rng)]
                pp = e.potion_prob(m, z_potion[sl], cache['prePotions'][sub], cache['capacity'][sub], delta, ending / maximum)
                potion_mass[draw, sl] = pp[np.arange(len(sub)), cache['trueMask'][sub]]
                mass = np.zeros(len(sub))
                for mask in range(32):
                    active = pp[:, mask] > 0
                    if active.any():
                        mass[active] += pp[active, mask] * target_probability(net, cache, sub[active], np.full(active.sum(), mask), ending[active], maximum[active])
                gold_mass[draw, sl] = mass
            print(f'gold exposure {draw + 1}/32', flush=True)
    gold_mixture = e.nll(gold_mass.mean(0)); gold_gap = gold_mixture - gold_teacher
    hp_gap = e.nll(hp_mass) - hp_teacher
    potion_gap = e.nll(potion_mass.mean(0)) - potion_teacher
    hard = Counter(dict(illegalGold=0, illegalStolenGold=0, nativeGoldClosureViolation=0,
                        upstreamPersistentViolation=0, downstreamAfterDeath=0))
    rng = np.random.default_rng(RECIPE['samplingSeed'] + 1)
    gold_calls = 0; deaths = 0; raw_counts = Counter()
    with torch.inference_mode():
        for draw in range(RECIPE['draws']):
            for start in range(0, len(test), 512):
                local = test[start:start + 512]
                sample = e.complete_batch(m, arrays, cache['ids'][local], cache['preHp'][local], cache['preMaxHp'][local], cache['prePotions'][local], cache['capacity'][local], rng)
                raw_counts.update(sample['counts']); chosen = sample['chosen']; survivors = local[chosen]
                deaths += len(local) - len(chosen)
                if not len(chosen):
                    continue
                lp = forward(net, cache, survivors, sample['mask'], sample['ending'], sample['maximum'])
                choices = e.draw_categories(lp.exp().cpu().numpy().astype(float), rng)
                gold_calls += len(survivors)
                pairs = cache['posts'][survivors, choices]
                for j, index in enumerate(survivors):
                    row = rows[start + int(chosen[j])]
                    pre, pi = row['pre'], row['predictorInput']
                    residues = {group: int(value[j]) for group, value in sample['residues'].items()}
                    try:
                        c.assemble_victory(pre, pi, int(sample['maximum'][j]), int(sample['ending'][j]), int(sample['mask'][j]), residues, m.encounter_names)
                    except ValueError:
                        hard['upstreamPersistentViolation'] += 1
                    pair = tuple(int(v) for v in pairs[j])
                    hard['illegalGold'] += not 0 <= pair[0] <= 32767
                    name = g.encounter_name(pi['globals']['encounter'])
                    thieves = 2 if name == 'TWO_THIEVES' else int(name in ('LOOTER', 'EXORDIUM_THUGS'))
                    maximum_stolen = 3 * thieves * (20 if pi['globals']['ascension'] >= 17 else 15)
                    hard['illegalStolenGold'] += not 0 <= pair[1] <= maximum_stolen
                    hard['nativeGoldClosureViolation'] += pair not in g.posts_for_input(pi, pre, int(sample['mask'][j]))
            print(f'gold complete validity {draw + 1}/32', flush=True)
    hard['downstreamAfterDeath'] = int(gold_calls + deaths != len(test) * RECIPE['draws'])
    row_by_local = {r['local']: r for r in rows}
    trans_plus = np.asarray([row_by_local[i]['transmutationPlus'] for i in victories])
    groups = {'GOLD_UNION': ~trans_plus}
    for reason in sorted({v for r in rows for v in r['reasons']}):
        groups[reason] = np.asarray([reason in row_by_local[i]['reasons'] for i in victories]) & ~trans_plus
    groups['TRANSMUTATION_PLUS_DIAGNOSTIC'] = trans_plus
    result_groups = {}
    for label, mask in groups.items():
        if not mask.any():
            continue
        ids = victories[mask]
        modes = cache['modes'][ids, cache['trueMask'][ids]]
        informative = cache['legal'][ids, modes].sum(-1) > 1
        result_groups[label] = dict(component=summarize_component(gold_p[mask], cache, ids),
                                    teacherInformative=summarize_component(gold_p[mask][informative], cache, ids[informative]) if informative.any() else None,
                                    goldExposureGap=float(gold_gap[mask].mean()),
                                    hpExposureGap=float(hp_gap[mask].mean()), potionExposureGap=float(potion_gap[mask].mean()),
                                    maxHpNll=float(max_teacher[mask].mean()), signedHpNll=float(hp_teacher[mask].mean()), potionNll=float(potion_teacher[mask].mean()))
    main = {k: v for k, v in result_groups.items() if k != 'TRANSMUTATION_PLUS_DIAGNOSTIC'}
    gold_gate = all(np.isfinite(v['goldExposureGap']) and v['goldExposureGap'] <= .1 for v in main.values()) and not any(hard.values())
    upstream_gate = all(np.isfinite(v[key]) and v[key] <= .1 for v in main.values() for key in ('hpExposureGap', 'potionExposureGap'))
    result = dict(sourceSha=source_sha, independentReview=False,
                  classification='GOLD_DEVELOPMENT_GATES_PASS_PENDING_REVIEW' if gold_gate and upstream_gate else 'GOLD_DEVELOPMENT_GATES_FAIL',
                  goldGate=gold_gate, upstreamHpPotionGates=upstream_gate, groups=result_groups,
                  hardValidity=dict(hard), completeDraws=len(test) * RECIPE['draws'], goldCalls=gold_calls,
                  sampledDeaths=deaths, upstreamCalls=dict(raw_counts), modelSha256=fitted['artifactSha256'],
                  frozenHashes=metadata['hashes'], gameplay=False, supportChanged=False,
                  unevaluated='independent review, relic exposure on recovered rows, final union composition/native export/continuation/runtime parity')
    np.savez_compressed(folder / 'diagnostic_rows.npz', ids=cache['ids'][victories], source=cache['source'][victories],
                        goldTeacherNll=gold_teacher, goldMixtureNll=gold_mixture, goldMass=gold_mass,
                        hpExposureGap=hp_gap, potionExposureGap=potion_gap, transmutationPlus=trans_plus)
    dump(folder / 'diagnostics.json', result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('prepare', 'fit', 'diagnose'))
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--source-sha')
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.output_dir)
    elif args.command == 'fit':
        fit(args.output_dir, args.source_sha)
    else:
        diagnose(args.output_dir, args.source_sha)
