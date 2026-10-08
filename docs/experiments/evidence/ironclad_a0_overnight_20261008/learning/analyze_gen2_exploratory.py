#!/usr/bin/env python3
"""Prospectively specified, post-primary GEN2 diagnostics. Never selects actions."""
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import numpy as np
import analyze_gen2_tranche as primary

L=primary.E
DESIGN=L/'GEN2_POST_PRIMARY_DIAGNOSTICS.md'
REVIEW=L/'GEN2_POST_PRIMARY_DIAGNOSTICS_REVIEW.md'
CONTRACT=L/'gen2_tranche32_3ed9/contract_receipt.json'
CHOICES=primary.CHOICES
RESULT=primary.RESULT
BINDINGS={
    DESIGN:'835cb0d121de3854b245c4ed5f20f5edc577b3a0e7bf6a600ccf44855e5ca401',
    REVIEW:'41d471b3e65149927957876e80e3599755d6b83fab46db5c2b76b7eb0b0c2c27',
    CONTRACT:'dec269de73abb320cf926e8e3891bbbdb74205521658849e23f8783ac217aa70',
    CHOICES:'0f7f79637cc1bce3fccb306e39d32c91e97539d75ebb970de6efc27416e923f7',
    RESULT:'5ada874a05f6d947cf0a19435db681a01be89aa23b26ceb26b5c59414aff798f',
    Path(primary.__file__):'f2ed2e94c5fd670aadaba5f12f563b6bd7d7532025de3b271d31f8eb06406fda',
    L/'gen2_tranche32_3ed9/analysis_bundle.json':'2f56269cf2bb6f5cc001890499a460cba0dff3b5df601396b6f9fbd02a0c2857',
}
SEEDS=primary.SEEDS
FAMILIES=['CARD_REWARD','BOSS_RELIC']
MODELS=['P0-s0','F2-s0']
BLOCKS={'selection':list(range(4)),'evaluation':list(range(4,8)),'all8_descriptive':list(range(8))}
FEATURES=['curHp','maxHp','gold','deckSize','fmDElite','fmDRest','fmDShop','fmDBoss','fmCElite','fmCRest','fmCShop','fmCEvent','fmCMonster','fmCTreasure','curMapX','curMapY']
BOOT=np.random.default_rng(20261008).integers(0,len(SEEDS),(10000,len(SEEDS)))
require,sha=primary.require,primary.sha


def mean(values):
    values=list(values)
    return sum(values)/len(values) if values else None


def source_ratio(numerator,denominator):
    """Resample all allocated source clusters; undefined draws remain counted."""
    num=np.asarray([numerator.get(s,0.0) for s in SEEDS],dtype=float)
    den=np.asarray([denominator.get(s,0.0) for s in SEEDS],dtype=float)
    require(np.isfinite(num).all() and np.isfinite(den).all() and (den>=0).all(),'invalid source estimator')
    dn=den[BOOT].sum(axis=1);valid=dn>0
    draws=num[BOOT].sum(axis=1)[valid]/dn[valid]
    return {'estimate':float(num.sum()/den.sum()) if den.sum() else None,
            'ci95_pointwise_unadjusted':list(map(float,np.quantile(draws,[.025,.975]))) if len(draws) else None,
            'bootstrap_undefined_draws':int((~valid).sum()),'bootstrap_replicates':10000,
            'bootstrap_unit':'complete allocated source cluster','bootstrap_seed':20261008,
            'exposed_source_count':int((den>0).sum()),'allocated_source_count':len(SEEDS)}


def source_summary(values,zero_missing=False):
    numerator={};denominator={}
    for s in SEEDS:
        x=values.get(s)
        if x is not None or zero_missing:
            numerator[s]=float(x) if x is not None else 0.0;denominator[s]=1.0
    out=source_ratio(numerator,denominator)
    out['per_source']={str(s):values.get(s,0.0 if zero_missing else None) for s in SEEDS}
    out['zero_for_unexposed']=zero_missing
    return out


def state_summary(values,states,additive=False):
    """Family conditional mean, or contribution with original total-state divisor."""
    groups=defaultdict(list)
    for state,value in values.items():
        if value is not None:groups[state[0]].append(value)
    totals=Counter(s[0] for s in states)
    return source_summary({s:(sum(groups[s])/totals[s] if additive else mean(groups[s])) for s in groups},zero_missing=additive)


def stats(values):
    a=np.asarray(values,dtype=float)
    require(len(a)>=2 and np.isfinite(a).all(),'invalid dispersion values')
    return {'mean':float(a.mean()),'sample_variance':float(a.var(ddof=1)),'range':float(a.max()-a.min())}


def sign(x):return 'positive' if x>0 else 'negative' if x<0 else 'zero'


def key(row):return (row['source_seed'],row['decision_idx'],row['type'])


def locators(tables):
    out={}
    for role in ['labels.csv','map.csv','options.csv','sources.csv']:
        for path in tables[role]:
            with Path(path).open(newline='') as f:
                for line,row in enumerate(csv.DictReader(f),2):
                    state=primary.state_key(row)
                    if state[1]<0:continue
                    k=(state,row.get('optionKey'),int(row['k']) if 'k' in row else None,role)
                    require(k not in out,'duplicate raw locator');out[k]=str(path)+':'+str(line)
    return out


def calibration(selected_states,options,labels,predictions):
    nstates=Counter(s[0] for s in selected_states)
    bias=defaultdict(float);brier=defaultdict(float)
    bins=[{'num_p':defaultdict(float),'num_y':defaultdict(float),'den':defaultdict(float),'rows':0,'sources':set()} for _ in range(5)]
    rows=0
    for state in selected_states:
        weight=1.0/(nstates[state[0]]*len(options[state])*4)
        for option in options[state]:
            for k in BLOCKS['evaluation']:
                p=predictions[(state,option,k)];y=int(labels[(state,option,k)]['finalWon']);rows+=1
                bias[state[0]]+=weight*(p-y);brier[state[0]]+=weight*(p-y)**2
                b=bins[min(4,int(p*5))];b['num_p'][state[0]]+=weight*p;b['num_y'][state[0]]+=weight*y;b['den'][state[0]]+=weight;b['rows']+=1;b['sources'].add(state[0])
    reliability=[]
    for i,b in enumerate(bins):
        mass=sum(b['den'].values())/len(nstates) if nstates else None
        reliability.append({'interval':[i/5,(i+1)/5],'upper_inclusive':i==4,'weighted_mass':mass,'rows':b['rows'],'source_count':len(b['sources']),'mean_prediction':source_ratio(b['num_p'],b['den']),'observed_win_rate':source_ratio(b['num_y'],b['den'])})
    return {'rows':rows,'source_count':len(nstates),'state_count':len(selected_states),'option_count':sum(len(options[s]) for s in selected_states),'bias':source_summary(bias),'brier':source_summary(brier),'reliability':reliability,'weights':'equal exposed sources, equal selected states within source, equal retained options within state, equal4evaluation futures; bin weights renormalized within bin'}


def analyze():
    inputs={}
    for p,h in BINDINGS.items():primary.checked_input(p,h,inputs)
    bundle=primary.read_json(L/'gen2_tranche32_3ed9/analysis_bundle.json')
    for item in bundle['inputs']:primary.checked_input(item['path'],item['sha256'],inputs)
    completed=primary.read_json(RESULT);frozen=primary.read_json(CHOICES)
    require(completed['status']=='DIAGNOSTIC_EVALUATION_COMPLETE' and completed['choice_sha256']==BINDINGS[CHOICES],'primary not completed with bound choice')
    require(frozen['status']=='CHOICES_FROZEN','choices not frozen')
    for item in completed['inputs']:primary.checked_input(item['path'],item['sha256'],inputs)
    _,contract,tables,options,sources,current=primary.context(CONTRACT,BINDINGS[CONTRACT]);inputs.update(current)
    labels,maps=primary.stage_tables(tables,options,list(range(8)),True)
    predictions=primary.model_predictions(maps,inputs)
    fixed={key(r):r for r in frozen['states']};states=sorted(options)
    require(set(fixed)==set(states),'state coverage mismatch')
    raw=locators(tables);source_counts=Counter(s[0] for s in states)
    cases=[];dispersion=[];feature_rows=[];model_rows=[]
    present=[f for f in FEATURES if all(f in r for r in maps.values())]
    missing=[f for f in FEATURES if f not in present]
    for state in states:
        f=fixed[state];baseline=f['baseline_option_key'];opts=options[state]
        require(opts[baseline]['chosen']=='1','baseline custody')
        y=lambda option,ks:[int(labels[(state,option,k)]['finalWon']) for k in ks]
        for model in MODELS:
            for option in opts:
                average=mean(predictions[model][(state,option,k)] for k in BLOCKS['selection'])
                require(abs(average-f['scores'][model][option])<1e-14,'stored selection prediction changed')
        for rule in primary.RULES:
            chosen=f['choices'][rule];aS=y(chosen,BLOCKS['selection']);bS=y(baseline,BLOCKS['selection']);aE=y(chosen,BLOCKS['evaluation']);bE=y(baseline,BLOCKS['evaluation'])
            ds=[a-b for a,b in zip(aS,bS)];de=[a-b for a,b in zip(aE,bE)];scores=f['scores'][rule];best=max(scores.values());ties=[a for a,v in scores.items() if v==best]
            cases.append({'state':list(state),'act':int(sources[state]['act']),'floor':int(sources[state]['floor']),'rule':rule,'baseline':baseline,'frozen_choice':chosen,'changed':chosen!=baseline,'selection_choice_mean':mean(aS),'selection_baseline_mean':mean(bS),'evaluation_choice_mean':mean(aE),'evaluation_baseline_mean':mean(bE),'delta_selection':mean(ds),'delta_evaluation':mean(de),'selection_optimism':mean(ds)-mean(de),'selected_only':sum(v>0 for v in de),'baseline_only':sum(v<0 for v in de),'both_win':sum(a==b==1 for a,b in zip(aE,bE)),'both_lose':sum(a==b==0 for a,b in zip(aE,bE)),'selection_max_tie':len(ties)>1,'baseline_retained_max_tie':len(ties)>1 and chosen==baseline,'selection_tied_keys':ties,'raw_source':raw[(state,None,None,'sources.csv')],'raw_selected_eval_labels':[raw[(state,chosen,k,'labels.csv')] for k in BLOCKS['evaluation']],'raw_baseline_eval_labels':[raw[(state,baseline,k,'labels.csv')] for k in BLOCKS['evaluation']]})
        for option in opts:
            row={'state':list(state),'option':option,'baseline':option==baseline,'blocks':{}}
            for block,ks in BLOCKS.items():
                d=stats(y(option,ks));d['paired_difference']=stats([a-b for a,b in zip(y(option,ks),y(baseline,ks))]) if option!=baseline else None
                row['blocks'][block]=d
            dispersion.append(row)
            for model in MODELS:
                gap=f['scores'][model][option]-f['scores'][model][baseline]
                gain=mean(a-b for a,b in zip(y(option,BLOCKS['evaluation']),y(baseline,BLOCKS['evaluation'])))
                model_rows.append({'state':list(state),'model':model,'option':option,'baseline':option==baseline,'selection_prediction_gap':gap,'evaluation_paired_gain':gain,'gap_sign':sign(gap),'gain_sign':sign(gain),'prediction_dispersion':{block:stats([predictions[model][(state,option,k)] for k in ks]) for block,ks in BLOCKS.items()}})
            feature_rows.append({'state':list(state),'option':option,'features':{feature:stats([float(maps[(state,option,k)][feature]) for k in range(8)]) for feature in present}})
    effects={};exposure={};optimism={}
    for family in ['ALL']+FAMILIES:
        selected_states=[s for s in states if family=='ALL' or s[2]==family];ss=set(selected_states)
        ceiling=sum(all(all(v==1 for v in y_values) for y_values in [[int(labels[(s,a,k)]['finalWon']) for k in BLOCKS['evaluation']] for a in options[s]]) for s in selected_states)
        floor=sum(all(all(v==0 for v in y_values) for y_values in [[int(labels[(s,a,k)]['finalWon']) for k in BLOCKS['evaluation']] for a in options[s]]) for s in selected_states)
        exposure[family]={'sources':len({s[0] for s in ss}),'states':len(ss),'states_by_act':dict(Counter(sources[s]['act'] for s in ss)),'retained_option_counts':dict(Counter(len(options[s]) for s in ss)),'retained_options':sum(len(options[s]) for s in ss),'evaluation_all_options_all_win_states':ceiling,'evaluation_all_options_all_lose_states':floor,'captured_baseline_retained':True,'rules':{}}
        effects[family]={};optimism[family]={}
        for rule in primary.RULES:
            rows=[r for r in cases if tuple(r['state']) in ss and r['rule']==rule]
            exposure[family]['rules'][rule]={'changed_actions':sum(r['changed'] for r in rows),'sources_with_change':len({r['state'][0] for r in rows if r['changed']}),'unchanged_actions':sum(not r['changed'] for r in rows),'selection_max_ties':sum(r['selection_max_tie'] for r in rows),'baseline_retained_max_ties':sum(r['baseline_retained_max_tie'] for r in rows)}
            effects[family][rule]={block:state_summary({tuple(r['state']):r[field] for r in rows},states,additive=family=='ALL') for block,field in [('selection','delta_selection'),('evaluation','delta_evaluation')]}
            effects[family][rule]['evaluation_additive_contribution']=state_summary({tuple(r['state']):r['delta_evaluation'] for r in rows},states,additive=True)
            if rule=='rollout':
                optimism[family]={'all_fixed_states':state_summary({tuple(r['state']):r['selection_optimism'] for r in rows},states,additive=family=='ALL'),'changed_evaluation_signs':dict(Counter(sign(r['delta_evaluation']) for r in rows if r['changed'])),'changed_negative_cases':[r for r in rows if r['changed'] and r['delta_evaluation']<0]}
    for rule in primary.RULES:
        observed=effects['ALL'][rule]['evaluation']['estimate'];expected=completed['summaries'][rule]['equal_source_mean_paired_gain']
        require(abs(observed-expected)<1e-14,'exploratory recomputation differs from frozen primary')
        require(abs(sum(effects[f][rule]['evaluation_additive_contribution']['estimate'] for f in FAMILIES)-expected)<1e-14,'family contributions do not sum')
    dispersion_summary={};model_summary={};feature_summary={}
    for family in ['ALL']+FAMILIES:
        selected=[s for s in states if family=='ALL' or s[2]==family];ss=set(selected)
        dispersion_summary[family]={}
        for block in BLOCKS:
            dstate={};pstate={};spread={}
            for state in selected:
                rows=[r for r in dispersion if tuple(r['state'])==state]
                dstate[state]=mean(r['blocks'][block]['sample_variance'] for r in rows)
                pstate[state]=mean(r['blocks'][block]['paired_difference']['sample_variance'] for r in rows if not r['baseline'])
                means=[r['blocks'][block]['mean'] for r in rows];spread[state]=max(means)-min(means)
            dispersion_summary[family][block]={'within_option_variance':state_summary(dstate,states),'paired_action_difference_variance':state_summary(pstate,states),'empirical_option_mean_range':state_summary(spread,states)}
        model_summary[family]={}
        for model in MODELS:
            rows=[r for r in model_rows if tuple(r['state']) in ss and r['model']==model and not r['baseline']]
            table=Counter((r['gap_sign'],r['gain_sign']) for r in rows)
            weighted={}
            for a in ['negative','zero','positive']:
                for b in ['negative','zero','positive']:
                    metric={s:mean(int(r['gap_sign']==a and r['gain_sign']==b) for r in rows if tuple(r['state'])==s) for s in selected}
                    weighted[a+'/'+b]={'raw_option_count':table[(a,b)],'source_balanced_proportion':state_summary(metric,states)}
            prediction_dispersion={}
            for block in BLOCKS:
                prediction_dispersion[block]={metric:state_summary({s:mean(r['prediction_dispersion'][block][metric] for r in model_rows if tuple(r['state'])==s and r['model']==model) for s in selected},states) for metric in ['sample_variance','range']}
            model_summary[family][model]={'action_ranking_sign_table':weighted,'calibration':calibration(selected,options,labels,predictions[model]),'prediction_dispersion':prediction_dispersion}
        feature_summary[family]={feature:{metric:state_summary({s:mean(r['features'][feature][metric] for r in feature_rows if tuple(r['state'])==s) for s in selected},states) for metric in ['sample_variance','range']} for feature in present}
    return {'schema':'gen2_post_primary_exploratory_v1','status':'EXPLORATORY_DIAGNOSTICS_COMPLETE','scope':'Prospectively specified descriptive diagnostics after frozen primary completion. No reselection, model fit, new simulation or population qualification. All intervals pointwise and unadjusted.','primary_classification_unchanged':completed['primary_classification'],'allocated_sources':len(SEEDS),'source_selected_state_counts':dict(Counter(source_counts.get(s,0) for s in SEEDS)),'exposure':exposure,'fixed_choice_cases':cases,'effects':effects,'rollout_selection_optimism':optimism,'option_dispersion_rows':dispersion,'dispersion_summary':dispersion_summary,'model_ranking_rows':model_rows,'model_summary':model_summary,'feature_dispersion_rows':feature_rows,'feature_dispersion_summary':feature_summary,'feature_columns_present':present,'feature_columns_missing':missing,'limits':primary.LIMITS+['Four evaluation futures give coarse and noisy local contrasts; empirical ceilings and zero variance are not equivalence or certain success. Calibration excludes no-state sources and uses explicit exposed-source denominators.'],'inputs':[{'path':p,'sha256':h} for p,h in sorted(inputs.items())],'analysis_script_sha256':sha(__file__)}


def main():
    out=L/'gen2_tranche32_3ed9_exploratory.json';require(not out.exists(),'refusing existing exploratory report')
    try:result=analyze()
    except Exception as error:result={'status':'INVALID_STOP_EXPLORATORY','error':repr(error),'analysis_script_sha256':sha(__file__)}
    with out.open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'status':result['status'],'path':str(out),'sha256':sha(out)},indent=2))
    return 0 if result['status']=='EXPLORATORY_DIAGNOSTICS_COMPLETE' else 1


if __name__=='__main__':raise SystemExit(main())
