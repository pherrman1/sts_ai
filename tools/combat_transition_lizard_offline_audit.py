#!/usr/bin/env python3
"""Offline-only active Lizard audit of the frozen composed CTM.

The sole support exception is Lizard Tail:data=1. The exception is made by
temporarily constraining that relic to remain active while the unchanged
composed support checker audits every other condition. No runtime support
predicate or artifact metadata is changed. For ancestral validity diagnostics,
the unqualified Lizard tensor is ignored and replaced with a TRAIN-only binary
class prior; this diagnostic prior is not a candidate runtime model.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import numpy as np
import torch

from tools import combat_transition_composed as c
from tools import combat_transition_composed_evaluate as ev
from tools import combat_transition_model_experiment as base_model

FIELDS = ('globals_continuous','global_categories','cards','relics','potions','card_mask','relic_mask')
BOOTSTRAP_REPS = c.RECIPE['bootstrapReps']
BOOTSTRAP_SEED = c.RECIPE['bootstrapSeed']
DRAW_COUNT = c.RECIPE['draws']


def offline_reasons(pre, pi, models):
    """Bypass only the active-Lizard rejection, retaining all other checks."""
    original = c.relic.legal_posts
    lizard = c.base._RELIC_IDS['LIZARD_TAIL']
    bloom = any(int(r['id']) == c.base._RELIC_IDS['MARK_OF_THE_BLOOM'] for r in pre['relics'])
    def allow_active_copy(rid, data, encounter=None, mark_of_bloom=False):
        allowed = original(rid, data, encounter, mark_of_bloom)
        if int(rid) == lizard and int(data) == 1 and not bloom and not mark_of_bloom:
            return frozenset({1})
        return allowed
    c.relic.legal_posts = allow_active_copy
    try:
        reasons = c.full_support_reasons(pre, pi, models)
    finally:
        c.relic.legal_posts = original
    # A state can pass the production pre-state checks while still containing
    # a nondeterministic mutable relic with no trained trajectory factor. Keep
    # this visible pre-state out of component and ancestral evaluation.
    for relic in pre['relics']:
        name = c.relic.NAMES.get(int(relic['id']))
        if name is None or name in c.relic.TRAJECTORY or name == 'LIZARD_TAIL':
            continue
        allowed = original(int(relic['id']), int(relic['data']),
                           pi['globals']['encounter'],
                           any(int(x['id']) == c.base._RELIC_IDS['MARK_OF_THE_BLOOM']
                               for x in pre['relics']))
        if len(allowed) > 1:
            reasons.append(f'unmodeled_mutable_relic:{name}')
    return reasons


def grouped_bootstrap(sources, values, seed=BOOTSTRAP_SEED):
    sources = np.asarray(sources, dtype=np.int64)
    values = np.asarray(values, dtype=np.float64)
    if len(sources) != len(values) or not len(values):
        return {'rows': len(values), 'sources': len(np.unique(sources)), 'mean': None, 'ci95': None}
    unique, inverse = np.unique(sources, return_inverse=True)
    counts = np.bincount(inverse).astype(float)
    sums = np.bincount(inverse, weights=values, minlength=len(unique))
    rng = np.random.default_rng(seed)
    draws = np.empty(BOOTSTRAP_REPS, dtype=np.float64)
    for i in range(BOOTSTRAP_REPS):
        sample = rng.integers(0, len(unique), len(unique))
        draws[i] = sums[sample].sum() / counts[sample].sum()
    return {'rows': len(values), 'sources': len(unique), 'mean': float(values.mean()),
            'ci95': np.quantile(draws, [.025,.975], method='inverted_cdf').tolist(),
            'repetitions': BOOTSTRAP_REPS, 'unit': 'sourceSeed'}


def stack_inputs(rows):
    encoded = [base_model._encode_row(r) for r in rows]
    return {name: np.stack([row[i] for row in encoded]) for i,name in enumerate(FIELDS)}


def lizard_head_probabilities(models, z, signed_class, fraction, mask):
    values = (torch.as_tensor(z,device=models.device,dtype=torch.float32), torch.as_tensor(signed_class,device=models.device,dtype=torch.long),
              torch.as_tensor(fraction,device=models.device,dtype=torch.float32),
              torch.as_tensor(mask,device=models.device,dtype=torch.long))
    logits = models.relic_net(*values)['lizard']
    return torch.softmax(logits.float(),-1).cpu().numpy().astype(float)


def audit(corpus_path: Path, manifest_path: Path, output_path: Path):
    manifest = json.loads(manifest_path.read_text())
    validated = c.base.validate_corpus(manifest)
    corpus_sha = c.base.sha256(corpus_path)
    if manifest.get('csv',{}).get('path') != str(corpus_path.resolve()):
        raise ValueError('manifest corpus path differs')
    if manifest.get('csv',{}).get('sha256') != corpus_sha:
        raise ValueError('manifest corpus hash differs')
    rows = list(c.base.iter_rows(corpus_path))
    if len(rows) != validated['rows']:
        raise ValueError('validated corpus row count differs')
    invalid_rows = [i for i,r in enumerate(rows)
                    if r.get('runValid') is not True or r.get('captureCount') != 1
                    or r.get('captureStatus') != 'exactly_one' or r.get('quarantineReason')]
    if invalid_rows:
        raise ValueError(f'fail-closed: {len(invalid_rows)} invalid, quarantined, or nonunique-capture rows')
    seeds = sorted({int(r['sourceSeed']) for r in rows})
    split = {s: base_model.split_for_seed(s) for s in seeds}
    split_rows = {name: [s for s in seeds if split[s] == name] for name in ('train','validation','test')}
    arrays = stack_inputs(rows)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    torch.set_num_threads(4)
    models = c.FrozenModels(device)
    n = len(rows)
    source = np.asarray([int(r['sourceSeed']) for r in rows],dtype=np.int64)
    fight = np.asarray([int(r['fightIdx']) for r in rows],dtype=np.int64)
    win = np.asarray([int(r['transition']['combatOutcome']) == c.base.WIN for r in rows])
    outcome = np.asarray([int(r['transition']['combatOutcome']) for r in rows])
    prehp = np.asarray([r['transition']['pre']['curHp'] for r in rows],dtype=np.int64)
    premax = np.asarray([r['transition']['pre']['maxHp'] for r in rows],dtype=np.int64)
    actualhp = np.asarray([r['transition']['post']['curHp'] for r in rows],dtype=np.int64)
    actualmax = np.asarray([r['transition']['post']['maxHp'] for r in rows],dtype=np.int64)
    true_delta = actualmax - premax
    delta_index = {int(x):i for i,x in enumerate(models.delta_values)}
    if any(int(d) not in delta_index for d in true_delta[win]):
        raise ValueError('observed maxHP transition outside frozen class domain')
    true_delta_idx = np.asarray([delta_index.get(int(d),0) for d in true_delta],dtype=np.int64)
    true_class_value = actualhp - prehp
    true_class = true_class_value - int(models.classes[0])
    if np.any((true_class[win] < 0) | (true_class[win] >= len(models.classes))):
        raise ValueError('observed HP transition outside frozen class domain')

    support_reasons = Counter()
    full = np.zeros(n,dtype=bool)
    for i,row in enumerate(rows):
        pre=row['transition']['pre']; post=row['transition']['post']
        encounter=row['predictorInput']['globals']['encounter']
        bloom=any(x['id']==c.base._RELIC_IDS['MARK_OF_THE_BLOOM'] for x in pre['relics'])
        post_by_id={int(x['id']):int(x['data']) for x in post['relics']}
        for entry in pre['relics']:
            rid=int(entry['id'])
            if rid not in c.relic.NAMES:
                if post_by_id[rid] != int(entry['data']):
                    raise ValueError(f"fail-closed: RAW immutable relic target changed seed={row['sourceSeed']} fight={row['fightIdx']} relic={rid}")
                continue
            allowed=c.relic.legal_posts(rid,int(entry['data']),encounter,bloom)
            if post_by_id[rid] not in allowed:
                raise ValueError(f"fail-closed: RAW relic target outside native domain seed={row['sourceSeed']} fight={row['fightIdx']} relic={c.relic.NAMES.get(rid,rid)}")
    for i,row in enumerate(rows):
        reasons = offline_reasons(row['transition']['pre'],row['predictorInput'],models)
        support_reasons.update(reasons)
        full[i] = not reasons
    if any(name == 'active_unqualified_lizard' for name in support_reasons):
        raise ValueError('offline Lizard exception failed to isolate the production guard')

    cache = {'pwin':np.zeros(n), 'pdelta':np.zeros((n,len(models.delta_values))),
             'z':np.zeros((n,64),np.float32), 'potion_z':np.zeros((n,64),np.float32)}
    with torch.inference_mode():
        for ids in ev.batches(n,256):
            inputs = c.base._torch_inputs(arrays,ids,device,torch,trim_padding=True)
            cache['pwin'][ids] = torch.sigmoid(models.survival_net.survival(models.fp32_encoding(models.survival_net.encoder,inputs))).squeeze(-1).cpu().numpy()
            cache['pdelta'][ids] = ev.probabilities(models.max_net.max_hp_delta(models.fp32_encoding(models.max_net.encoder,inputs)))
            cache['z'][ids] = models.hp_encoding(inputs).cpu().numpy()
            cache['potion_z'][ids] = models.fp32_encoding(models.potion_encoder.encoder,inputs).cpu().numpy()

    seed_split = np.asarray([split[int(s)] for s in source])
    test = (seed_split == 'test') & full
    test_wins = test & win
    eval_ids = np.flatnonzero(test)
    win_ids = np.flatnonzero(test_wins)
    stats = Counter()
    copy_through_mismatches = Counter()
    interaction_sources = {}
    def record_interaction(key, source_seed):
        stats[key] += 1
        interaction_sources.setdefault(key, set()).add(int(source_seed))
    observed_legality = Counter()
    unmodeled_mutable_targets = Counter()
    lizard_id = c.base._RELIC_IDS['LIZARD_TAIL']
    fairy_id = c.base._POTION_IDS['FAIRY_POTION']
    for i,row in enumerate(rows):
        pre = row['transition']['pre']; post = row['transition']['post']
        bloom = any(x['id']==c.base._RELIC_IDS['MARK_OF_THE_BLOOM'] for x in pre['relics'])
        try:
            c.relic.trajectory_constraints(pre['relics'],post['relics'],row['predictorInput']['globals']['encounter'],bloom)
        except (ValueError,KeyError,TypeError) as error:
            if str(error) == 'unsupported mutable relic transition':
                unmodeled_mutable_targets[f'{split[int(source[i])]}.{type(error).__name__}:{error}'] += 1
            else:
                observed_legality[f'{split[int(source[i])]}.{type(error).__name__}:{error}'] += 1
        before = next((x['data'] for x in pre['relics'] if x['id'] == lizard_id),None)
        after = next((x['data'] for x in post['relics'] if x['id'] == lizard_id),None)
        split_name = split[int(source[i])]
        if before == 1 and after == 1 and win[i]: record_interaction(f'{split_name}.active_survived_retained',source[i])
        if before == 1 and after == 0 and win[i]: record_interaction(f'{split_name}.active_survived_consumed',source[i])
        if before == 1 and after == 0 and not win[i]: record_interaction(f'{split_name}.final_death_after_consumption',source[i])
        has_fairy = any(int(p['potionId']) == fairy_id for p in row['predictorInput']['potions'])
        fairy_after = any(int(p) == fairy_id for p in post['potions'])
        if has_fairy and not fairy_after and after == 1: record_interaction(f'{split_name}.fairy_first_lizard_retained',source[i])
        if pre['gold'] != post['gold']: record_interaction(f'{split_name}.gold_changed',source[i])
        if pre['deck'] != post['deck']: record_interaction(f'{split_name}.deck_changed',source[i])
        if pre['stolenGold'] != post['stolenGold']: record_interaction(f'{split_name}.stolen_gold_changed',source[i])
        if pre['smokeBombUsed'] != post['smokeBombUsed']: record_interaction(f'{split_name}.smoke_bomb_state_changed',source[i])
        if pre['cardTypeCounts'] != post['cardTypeCounts']: record_interaction(f'{split_name}.card_type_counts_changed',source[i])
        if before == 1: record_interaction(f'{split_name}.active_lizard_rows',source[i])
        if full[i] and win[i]:
            for key in (*c.base.COPY_THROUGH_KEYS, 'smokeBombUsed'):
                if pre[key] != post[key]:
                    copy_through_mismatches[f'{split_name}.{key}'] += 1

    if observed_legality:
        raise ValueError(f'fail-closed: {sum(observed_legality.values())} RAW relic transitions violate the audited native contract: {dict(observed_legality)}')

    if not len(win_ids) or not len(eval_ids):
        raise ValueError('source-grouped TEST has no fully supported active-Lizard rows/wins')
    prehp_w = prehp[win_ids]; premax_w = premax[win_ids]; max_w = actualmax[win_ids]
    hp_w = actualhp[win_ids]; delta_w = true_delta_idx[win_ids]
    class_w = true_class[win_ids]
    max_teacher = ev.nll(cache['pdelta'][win_ids,delta_w])
    hp_prob = ev.hp_prob(models,cache['z'][win_ids],delta_w,prehp_w,max_w)
    hp_teacher = ev.nll(hp_prob[np.arange(len(win_ids)),class_w])
    hp_rows = c.hp.row_scores(hp_prob,c.CLASSES,prehp_w,max_w,hp_w,hp_teacher)
    slots = arrays['potions'][win_ids,:,1].astype(np.int64)
    caps = np.asarray([rows[i]['transition']['pre']['potionCapacity'] for i in win_ids],dtype=np.int64)
    true_masks = c.potion.encode_masks(np.asarray([rows[i]['transition']['pre']['potions'] for i in win_ids]),
                                       np.asarray([rows[i]['transition']['post']['potions'] for i in win_ids]),caps)
    fractions = hp_w / max_w
    potion_prob = ev.potion_prob(models,cache['potion_z'][win_ids],slots,caps,delta_w,fractions)
    potion_teacher = ev.nll(potion_prob[np.arange(len(win_ids)),true_masks])
    constraints = {g:np.ones((len(win_ids),k),dtype=bool) for g,k in c.relic.HEAD_CLASSES.items() if g in c.TRAINED_GROUPS}
    observed_groups = np.zeros((len(win_ids),len(c.TRAINED_GROUPS)),dtype=bool)
    for local,i in enumerate(win_ids):
        row=rows[i]; pre=row['transition']['pre']; post=row['transition']['post']
        bloom=any(x['id']==c.base._RELIC_IDS['MARK_OF_THE_BLOOM'] for x in pre['relics'])
        observed=c.relic.trajectory_constraints(pre['relics'],post['relics'],row['predictorInput']['globals']['encounter'],bloom)
        for gi,g in enumerate(c.TRAINED_GROUPS):
            if g in observed:
                constraints[g][local]=np.isin(np.arange(c.relic.HEAD_CLASSES[g]),list(observed[g]))
                observed_groups[local,gi]=True
    relic_p = ev.relic_prob(models,cache['z'][win_ids],class_w,fractions,true_masks)
    relic_group_nll = {g:ev.nll(np.sum(relic_p[g]*constraints[g],axis=-1)) for g in c.TRAINED_GROUPS}
    relic_count = observed_groups.sum(-1)
    relic_teacher = sum(relic_group_nll[g]*observed_groups[:,j] for j,g in enumerate(c.TRAINED_GROUPS)) / np.maximum(relic_count,1)
    informative = relic_count > 0

    train = (seed_split == 'train') & full & win
    lizard_train = []
    lizard_test = []
    lizard_probs = lizard_head_probabilities(models,cache['z'][win_ids],class_w,fractions,true_masks)
    for local,i in enumerate(win_ids):
        pre=rows[i]['transition']['pre']; post=rows[i]['transition']['post']
        before=next(x['data'] for x in pre['relics'] if x['id']==lizard_id)
        after=next(x['data'] for x in post['relics'] if x['id']==lizard_id)
        lizard_test.append(int(before == 1 and after == 0))
    for i in np.flatnonzero(train):
        pre=rows[i]['transition']['pre']; post=rows[i]['transition']['post']
        before=next(x['data'] for x in pre['relics'] if x['id']==lizard_id)
        after=next(x['data'] for x in post['relics'] if x['id']==lizard_id)
        lizard_train.append(int(before == 1 and after == 0))
    prior_consumption=float(np.mean(lizard_train)) if lizard_train else float('nan')
    y_lizard=np.asarray(lizard_test,dtype=np.int64)
    safe_prior=np.clip(prior_consumption,1e-9,1-1e-9)
    prior_nll=-(y_lizard*np.log(safe_prior)+(1-y_lizard)*np.log1p(-safe_prior))
    head_nll=ev.nll(lizard_probs[np.arange(len(y_lizard)),y_lizard])
    head_brier=(lizard_probs[:,1]-y_lizard)**2

    # Existing composed-sampler exposure criterion, restricted to source-held-out rows.
    exposure_rng=np.random.default_rng(c.RECIPE['samplingSeed'])
    hp_mass=[]; potion_mass=[]; relic_mass=[]
    true_class_vec=class_w
    prepotions=np.asarray([rows[i]['transition']['pre']['potions'] for i in win_ids],dtype=np.int64)
    with torch.inference_mode():
        for _ in range(DRAW_COUNT):
            d=ev.draw_categories(cache['pdelta'][win_ids],exposure_rng)
            maximum=premax_w+models.delta_values[d]
            p_hp=ev.hp_prob(models,cache['z'][win_ids],d,prehp_w,maximum)
            hp_mass.append(p_hp[np.arange(len(win_ids)),true_class_vec])
            sampled_signed=ev.draw_categories(p_hp,exposure_rng)
            ending=prehp_w+c.CLASSES[sampled_signed]
            frac=ending/maximum
            pp=ev.potion_prob(models,cache['potion_z'][win_ids],slots,caps,d,frac)
            potion_mass.append(pp[np.arange(len(win_ids)),true_masks])
            sampled_mask=ev.draw_categories(pp,exposure_rng)
            rp=ev.relic_prob(models,cache['z'][win_ids],sampled_signed,frac,sampled_mask)
            relic_mass.append(ev.constraint_probability(rp,constraints))
    hp_mixture=ev.nll(np.mean(hp_mass,axis=0))
    potion_mixture=ev.nll(np.mean(potion_mass,axis=0))
    relic_mixture=ev.nll(np.mean(relic_mass,axis=0))
    hp_marginal,hp_conditional=ev.exact_hp_target_probabilities(models,cache['z'][win_ids],cache['pdelta'][win_ids],prehp_w,premax_w,true_class_vec)
    hp_exact=ev.nll(hp_marginal)
    src_win=source[win_ids]
    exposure={
        'hp':grouped_bootstrap(src_win,hp_exact-hp_teacher),
        'potion':grouped_bootstrap(src_win,potion_mixture-potion_teacher),
        'relic':grouped_bootstrap(src_win[informative],(relic_mixture-relic_teacher)[informative]/relic_count[informative]),
    }
    for g,metric in exposure.items():
        metric['qualificationThresholdMeanGap'] = 0.1
        metric['gate'] = ('INCONCLUSIVE_NO_INFORMATIVE_ROWS' if metric['mean'] is None else
                          'EXPOSURE_OK' if metric['mean'] <= 0.1 else 'MATERIAL_EXPOSURE_DEGRADATION')

    # Full ancestral validity under the explicit TRAIN-only prior, not the old Lizard tensor.
    prior_vec=np.asarray([1-safe_prior,safe_prior],dtype=float)
    original_relic_prob=ev.relic_prob
    def prior_augmented_relic_prob(m,z,signed,fraction,mask):
        result=original_relic_prob(m,z,signed,fraction,mask)
        result['lizard']=np.broadcast_to(prior_vec,(len(z),2)).copy()
        return result
    ev.relic_prob=prior_augmented_relic_prob
    arrays['sourceSeed']=source
    validity=Counter(); sampled={'death':0,'victory':0,'lizardRetained':0,'lizardConsumed':0}; sample_rng=np.random.default_rng(c.RECIPE['samplingSeed']+1)
    try:
        sample_ids=eval_ids
        prehp_all=np.asarray([rows[i]['transition']['pre']['curHp'] for i in sample_ids])
        premax_all=np.asarray([rows[i]['transition']['pre']['maxHp'] for i in sample_ids])
        slot_all=arrays['potions'][sample_ids,:,1].astype(np.int64)
        cap_all=np.asarray([rows[i]['transition']['pre']['potionCapacity'] for i in sample_ids])
        sample_rows=[rows[i] for i in sample_ids]
        for draw in range(DRAW_COUNT):
            for batch in ev.batches(len(sample_ids),128):
                local_ids=batch
                global_ids=sample_ids[local_ids]
                sample=ev.complete_batch(models,arrays,global_ids,prehp_all[local_ids],premax_all[local_ids],slot_all[local_ids],cap_all[local_ids],sample_rng)
                sampled['death'] += len(local_ids)-len(sample['chosen']); sampled['victory'] += len(sample['chosen'])
                for k,local in enumerate(sample['chosen']):
                    row=rows[int(global_ids[local])]
                    try:
                        residue={g:int(values[k]) for g,values in sample['residues'].items()}
                        post=c.assemble_victory(row['transition']['pre'],row['predictorInput'],int(sample['maximum'][k]),int(sample['ending'][k]),int(sample['mask'][k]),residue,models.encounter_names)
                        state=next(x['data'] for x in post['relics'] if x['id']==lizard_id)
                        sampled['lizardRetained' if state==1 else 'lizardConsumed'] += 1
                    except Exception as error:
                        validity[f'assembly:{type(error).__name__}:{error}'] += 1
    finally:
        ev.relic_prob=original_relic_prob
    output={
        'schema':'active_lizard_offline_ctm_audit_v1','productionGuardChanged':False,
        'offlineSupportException':'active Lizard only; all other full_support_reasons preserved',
        'ancestralLizardDistribution':'TRAIN-only consumption prior; historical unqualified lizard tensor excluded',
        'corpus':{'path':str(corpus_path.resolve()),'sha256':corpus_sha,'manifestSha256':c.base.sha256(manifest_path),'validatedRows':validated['rows'],'sourceSeeds':len(seeds),'sourcesBySplit':{k:len(v) for k,v in split_rows.items()},'sourceSeedsBySplit':{k:v for k,v in split_rows.items()}},
        'frozenArtifacts':c.verify_hashes(),'teacherId':manifest['combatTeacher']['teacher_id'],
        'teacherProvenance':manifest['combatTeacher'],'interventionProvenance':manifest.get('lizardIntervention'),
        'support':{'counts':{'testFullSupportRows':len(eval_ids),'testFullSupportWins':len(win_ids),'testRowsTotal':int(np.sum(seed_split=='test')),'unsupportedReasons':dict(support_reasons)},'otherReasonsRetained':True},
        'observedInteractionsBySourceSplit':dict(sorted(stats.items())),
        'observedInteractionSourceCountsBySourceSplit':{
            key:len(values) for key,values in sorted(interaction_sources.items())},
        'supportedWinningCopyThroughMismatches':dict(copy_through_mismatches),
        'observedRelicLegalityFailures':dict(observed_legality),
        'nativeLegalButUnmodeledMutableTargets':dict(unmodeled_mutable_targets),
        'components':{
            'survival':dict(rows=len(eval_ids),brier=c.base._binary_metrics(win[eval_ids].astype(int),cache['pwin'][eval_ids])['brier'],logloss=c.base._binary_metrics(win[eval_ids].astype(int),cache['pwin'][eval_ids])['logloss']),
            'maxHp':dict(winningRows=len(win_ids),nll=ev.mean(max_teacher),modeAccuracy=ev.mean(cache['pdelta'][win_ids].argmax(-1)==delta_w)),
            'hp':dict(winningRows=len(win_ids),nll=ev.mean(hp_teacher),scores=c.hp.summarize(hp_rows)),
            'potions':dict(winningRows=len(win_ids),jointMaskNll=ev.mean(potion_teacher),modeExact=ev.mean(potion_prob.argmax(-1)==true_masks)),
            'relicTrajectory':dict(winningRows=len(win_ids),observedGroupCounts={g:int(observed_groups[:,j].sum()) for j,g in enumerate(c.TRAINED_GROUPS)},normalizedConstraintNll=ev.mean(relic_teacher[informative]) if informative.any() else None,byGroupNll={g:ev.mean(relic_group_nll[g][observed_groups[:,j]]) for j,g in enumerate(c.TRAINED_GROUPS)}),
            'lizardHeadDiagnosticOnly':dict(trainingWinningRows=len(lizard_train),trainConsumed=sum(lizard_train),priorConsumptionRate=prior_consumption,testWinningRows=len(y_lizard),testConsumed=int(y_lizard.sum()),oldHeadNll=ev.mean(head_nll),trainPriorNll=ev.mean(prior_nll),oldHeadBrier=ev.mean(head_brier),qualification='UNQUALIFIED'),
        },
        'exposure':{**{k:v for k,v in exposure.items() if k != 'relic'},
                    'nonLizardRelic':exposure['relic'],
                    'lizardHeadVsTrainPrior':grouped_bootstrap(source[win_ids],head_nll-prior_nll)},
        'ancestral':{'drawsPerTestRow':DRAW_COUNT,'counts':dict(sampled),'hardValidityFailures':dict(validity),'hardValidityFailureCount':sum(validity.values()),'priorIsDiagnosticOnly':True},
        'decision':'INCONCLUSIVE_KEEP_ACTIVE_UNQUALIFIED_LIZARD',
        'decisionReason':'This diagnostic does not qualify an active-Lizard runtime artifact; production remains fail-closed pending held-out evidence and the normal scientific gate.',
    }
    output_path.parent.mkdir(parents=True,exist_ok=True)
    output_path.write_text(json.dumps(output,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'output':str(output_path),'support':output['support'],'exposure':exposure,'ancestral':output['ancestral'],'decision':output['decision']},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus',type=Path,required=True)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args(); audit(a.corpus,a.manifest,a.output)
