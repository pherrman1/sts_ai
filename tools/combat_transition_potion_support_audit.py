#!/usr/bin/env python3
"""Seed-free, fail-closed old/new support accounting on the frozen corpus."""
from collections import Counter
import argparse
import json
from pathlib import Path
import re
import numpy as np
from tools import combat_transition_composed_evaluate as evaluation
from tools import combat_transition_composed as c
from tools.combat_transition_contract import validate_corpus


def audit(output):
    hashes = evaluation.verify_data()
    manifest_path = Path(json.loads((evaluation.PREPARED/'prepared_manifest.json').read_text())['corpusManifest'])
    manifest = json.loads(manifest_path.read_text())
    integrity = validate_corpus(manifest)
    provenance_path = evaluation.CORPUS.with_suffix('.jsonl.provenance.json')
    provenance = json.loads(provenance_path.read_text())
    bindings = dict(dataset_path=manifest['csv']['path'], git_sha=manifest['producerGitSha'],
                    rows_written=integrity['rows'], completed_seeds=integrity['completedSeeds'],
                    requested_seeds=integrity['requestedSeeds'], seed_offset=manifest['seedSpec']['start'],
                    invalid_or_quarantined_seeds=integrity['quarantinedSeeds'], generator='combattransitiongen')
    if any(provenance.get(k) != v for k,v in bindings.items()) or integrity['quarantinedRows']:
        raise ValueError('companion provenance mismatch or quarantined rows')
    if len(provenance['quarantined']) != integrity['quarantinedSeeds']:
        raise ValueError('quarantine accounting mismatch')
    hashes[str(provenance_path)] = c.base.sha256(provenance_path)
    arrays,spec = c.base._load_prepared(evaluation.PREPARED)
    models = c.FrozenModels('cpu')
    split = json.loads(evaluation.SPLIT.read_text())
    membership = {int(s):i for i,k in enumerate(('train','validation','test')) for s in split['members'][k]}
    if len(membership) != sum(map(len,split['members'].values())):
        raise ValueError('split overlap')
    text = (c.frozen.ROOT/'include/constants/Cards.h').read_text()
    colors = re.findall(r'CardColor::([A-Z]+)', re.search(r'cardColors\[\]\s*=\s*\{(.*?)\};',text,re.S)[1])
    audited = {i for i,color in enumerate(colors) if color in ('RED','COLORLESS','CURSE')}
    tables = {}; old_reasons = Counter(); new_reasons = Counter(); sources = set()
    counts = Counter(); n = 0
    for i,row in enumerate(c.base.iter_rows(evaluation.CORPUS)):
        pre,post = row['transition']['pre'],row['transition']['post']; pi = row['predictorInput']
        source = int(row['sourceSeed']); sources.add(source)
        if i >= len(arrays['y_win']) or (source,int(row['fightIdx'])) != (int(arrays['sourceSeed'][i]),int(arrays['fightIdx'][i])) or membership.get(source) != arrays['split_id'][i]:
            raise ValueError('prepared row/split alignment mismatch')
        if c.base.supported_for_surrogate(pi,pre) != bool(arrays['supported'][i]):
            raise ValueError('global eligibility mismatch')
        new = c.full_support_reasons(pre,pi,models)
        old_cert = pi['globals']['characterClass']==c.base.IRONCLAD_ID and all(x['cardId'] in audited for x in pi['cards']) and all(x['potionId']!=c.base.ENTROPIC_BREW_ID for x in pi['potions'])
        old = new if old_cert else c.base.supported_reasons(pi,pre)+['potion_not_certified']
        old_reasons.update(old); new_reasons.update(new)
        recovered = not new and bool(old)
        if not old and new: raise ValueError('support narrowed unexpectedly')
        counts['previousPotionNotCertified'] += 'potion_not_certified' in old
        counts['potionCertificationRecovered'] += 'potion_not_certified' in old and 'potion_not_certified' not in new
        counts['fullySupportedRecovered'] += recovered
        labels = ['all',f"act:{pi['globals']['act']}",f"room:{pi['globals']['roomClass']}",f"split:{int(arrays['split_id'][i])}"]
        if arrays['split_id'][i]==2: labels += [f"test:act:{pi['globals']['act']}",f"test:room:{pi['globals']['roomClass']}"]
        for label in labels:
            t=tables.setdefault(label,Counter());t['rows']+=1;t['oldSupported']+=not old;t['newSupported']+=not new;t['recovered']+=recovered
        if not new:
            counts['supportedRowsChecked'] += 1
            # Check every outcome, including terminal rows, for inventory creation.
            bad = [slot for slot,(a,b) in enumerate(zip(pre['potions'],post['potions'])) if b!=a and not (slot<pre['potionCapacity'] and a>1 and b==1)]
            if bad:
                output.with_suffix('.counterexample.json').write_text(json.dumps(dict(index=i,slots=bad,row=row),indent=2))
                raise ValueError(f'supported potion creation/swap/substitution at row {i}, source {source}')
            if pre['combatRng'][4]!=post['combatRng'][4] or c.native_rng.replay_misc(pre['combatRng'][2],models.encounter_names[pi['globals']['encounter']])!=post['combatRng'][2]:
                raise ValueError(f'RNG contradiction at {i}')
            if row['transition']['combatOutcome']==c.base.WIN:
                if c.base._copy_through_violations(pre,post): raise ValueError(f'copy-through contradiction at {i}')
                c.potion.encode_masks(np.asarray([pre['potions']]),np.asarray([post['potions']]),np.asarray([pre['potionCapacity']]))
                c.relic.trajectory_constraints(pre['relics'],post['relics'],pi['globals']['encounter'],any(x['id']==c.base._RELIC_IDS['MARK_OF_THE_BLOOM'] for x in pre['relics']))
        n=i+1
        if n%50000==0: print(f'audit {n}/510030',flush=True)
    if n!=510030 or n!=len(arrays['y_win']) or sources!=set(membership): raise ValueError('incomplete row/source accounting')
    if counts['previousPotionNotCertified']!=116302: raise ValueError('old support reproduction differs')
    report = {k:dict(v,oldFallback=v['rows']-v['oldSupported'],newFallback=v['rows']-v['newSupported'],oldRate=v['oldSupported']/v['rows'],newRate=v['newSupported']/v['rows']) for k,v in tables.items()}
    result = dict(schema='potion_generation_support_audit_v1',baseline='3057ea79f8a678ba13f9f2ea2b4834850fa2dd87',hashes=hashes,integrity=integrity,counts=dict(counts),tables=report,oldReasons=dict(old_reasons),newReasons=dict(new_reasons),supportedPotionViolations=0,training=False,gameplay=False)
    output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result['tables']['all']),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);audit(p.parse_args().output)
