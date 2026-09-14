#!/usr/bin/env python3
"""Whole-corpus target representability under exact potion-effect posteriors."""
import argparse
from collections import Counter
import json
from pathlib import Path
import numpy as np
from tools import combat_transition_composed as c,combat_transition_composed_evaluate as e
from tools import combat_transition_potion_trajectory as t,combat_transition_potion_trajectory_evaluate as trajectory
from tools import combat_transition_gold as gold,combat_transition_gold_proc_budget as budget
from tools import combat_transition_sparse_events as events,combat_transition_sparse_evaluate as sparse


def run(folder,output,sha):
    sparse.frozen(sha)
    if output.exists():raise ValueError('refusing overwrite')
    cache,graphs,meta=trajectory.load(folder)
    posterior_meta=json.loads((folder/'trace_posteriors.json').read_text())
    if c.base.sha256(folder/'trace_posteriors.npz')!=posterior_meta['artifactSha256']:raise ValueError('posterior binding differs')
    with np.load(folder/'trace_posteriors.npz') as raw:posteriors={int(i):p for i,p in zip(raw['ids'],raw['posterior'])}
    counts=Counter();failures=[]
    local_by_index={int(index):local for local,index in enumerate(cache['ids'])}
    for index,row in enumerate(c.base.iter_rows(e.CORPUS)):
        if index not in local_by_index:continue
        local=local_by_index[index];counts['rows']+=1
        if not cache['win'][local]:counts['deathShortCircuit']+=1;continue
        pre,post,pi=row['transition']['pre'],row['transition']['post'],row['predictorInput']
        escaped=bool(post['smokeBombUsed']);counts['escapeSurvivors']+=escaped
        adjusted=pre
        if pi['globals']['encounter']==c.base.WRITHING_MASS_ID:
            event=events.writhing_target(pre,post);adjusted=events.writhing_posts(pre)[event];counts['writhingSurvivors']+=1
        deltas=tuple(change['delta'] for change in events.ritual_changes(adjusted,post))
        if deltas:counts['ritualSurvivors']+=1
        if local in posteriors:
            posterior=posteriors[local];traces=np.flatnonzero(posterior>0)
        else:
            mask=int(cache['mask'][local]);_,used=t.consume(pre['potions'],mask)
            effects=sum(1<<bit for bit,p in enumerate(t.EFFECT_IDS) if p in used)
            traces=[mask+32*effects];posterior=None
        target=(post['gold'],post['info']['stolenGold']);represented=0.
        for trace in traces:
            mask=int(trace)&31;flags=int(trace)>>5;consumed=tuple(p for bit,p in enumerate(t.EFFECT_IDS) if flags&(1<<bit))
            try:
                if deltas not in events.ritual_posts(pre,pi,mask,consumed,escaped):continue
                legal=budget.joint_gold_posts(pre,pi,mask,deltas,consumed,escaped)
            except ValueError:continue
            if target in legal:represented+=float(posterior[trace]) if posterior is not None else 1.
        if represented<=0:
            failures.append(dict(index=index,source=row['sourceSeed'],fight=row['fightIdx'],encounter=gold.encounter_name(pi['globals']['encounter']),escaped=escaped,goldTarget=target,daggerDeltas=deltas,preGold=pre['gold'],prePotions=pre['potions'],traces=list(map(int,traces))))
        else:counts['jointRepresentableSurvivors']+=1
        if index%100000==0:print('joint native target audit',index,flush=True)
    result=dict(sourceSha=sha,counts=counts,failures=failures,classification='NATIVE_JOINT_TARGETS_PASS' if not failures else 'NATIVE_JOINT_TARGETS_FAIL',trajectorySha256=posterior_meta['modelSha256'],posteriorSha256=posterior_meta['artifactSha256'],supportChanged=False,scope='target representability only; no probability/native artifact qualification')
    c.base.json_dump(output,result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--trajectory-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--source-sha',required=True);a=p.parse_args();run(a.trajectory_dir,a.output,a.source_sha)
