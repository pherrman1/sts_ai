#!/usr/bin/env python3
"""Frozen K4/K16 selection, then separate conditional evaluation; never schedules games."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
OLD = ROOT / 'docs/experiments/evidence/ironclad_a0_overnight_20261008/learning'
SEEDS = list(range(610084200, 610084232))
RULES = {'K4': list(range(4)), 'K16': list(range(16))}
EVAL_K = list(range(16, 32))
SOURCE_SHA = '3ed91ab3491a4cdc1a7de687b2ad87dcc7774fc0'
BINARY_SHA = '27a78efd3f5da731897d36dd9b50a622d2ace4f54dae69dfc157bf6712b027c7'
TEACHER_SHA = 'cf30c66df49aa9a11097320511b5bc70564e838541089465e3c315c2c4815040'
POLICY_SHA = '1d7f29703b20fbb4f9f37740438a316f5ae144a3d2133eec1e56e8239bcec188'
OLD_VERIFIER_SHA = '8f9c9a790fa8cd350572de516df80120134a8fdb4072de661876fdd945f4d3aa'
BOOTSTRAP_SHA = 'f31e7ebd8a94a27043fdf5498c0e88dd53317626c6153896c345b1459667778d'
HEALTH_HELPER_SHA = 'ae0085f07389cf36be09a5cfe15591ba7d44562fbfd5cfb3beab8360a57a71aa'
ROLES = ('options.csv', 'sources.csv', 'labels.csv', 'map.csv', 'receipt.json', 'manifest.json', 'log', 'tree.jsonl')
LIMITS = [
    'One retained BOSS_RELIC state per allocated source at most; all 32 source clusters remain in the primary denominator. Valid no-state sources have zero incremental gain.',
    'Primary is conditional finalWon gain of frozen K16 choice minus frozen K4 choice under the same teacher and sampler; not a population policy or 2pp promotion test.',
    'Retained legal options only. The sampler preserves latent counters and pool membership and is not an exact posterior over player-visible histories.',
    'Selection K4 is nested in K16; evaluation k16..31 is separate. Sibling future draws are coupled, not independent source runs.',
    'The frozen teacher retains original models and learned stopping; no historical P0/F2 action selector, training, retuning, new architecture or deployed policy is inferred.',
    'Source heterogeneity, finite-future uncertainty and teacher/sampler mismatch remain; the bootstrap covers allocated-source sampling, not systematic simulator or teacher errors.',
    'The earlier RemoveLow confirmation and protected historical TEST remain outside this experiment. No sample extension or automatic follow-up follows from any verdict.'
]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def module_from(path, digest, name):
    require(sha(path) == digest, 'reviewed helper changed: '+str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Import only reviewed pure helpers; neither helper opens collection data on import.
VERIFIER_HELPERS = module_from(OLD/'verify_gen2.py', OLD_VERIFIER_SHA, 'reviewed_gen2_helpers')
BOOTSTRAP = module_from(ROOT/'paired_analysis.py', BOOTSTRAP_SHA, 'reviewed_paired_analysis')


def runtime_identity():
    executable = str(Path(sys.executable).resolve())
    return {'python_version': sys.version, 'python_executable': executable,
            'python_executable_sha256': sha(executable), 'numpy_version': np.__version__}


def read_json(path):
    return json.loads(Path(path).read_text())


def checked(path, digest, inputs):
    path = Path(path).resolve()
    require(sha(path) == digest, 'changed input: '+str(path))
    inputs[str(path)] = digest
    return path


def validate_freeze(f):
    require(f['source_seeds'] == SEEDS and f['futures'] == 32 and f.get('future_start', 0) == 0, 'fixed source/future allocation')
    require(f['states_per_seed'] == 1 and f['types'] == ['BOSS_RELIC'], 'fixed one-BOSS state scope')
    require(f['selection_k_by_rule'] == RULES and f['evaluation_k'] == EVAL_K, 'fixed nested selection/evaluation split')
    require(f['source_sha'] == SOURCE_SHA and f['binary_sha256'] == BINARY_SHA, 'unchanged producer identity')
    require(f['teacher_sha256'] == TEACHER_SHA and f['policy_sha256'] == POLICY_SHA, 'unchanged teacher/policy')
    require(Path(f['root']).resolve() == ROOT, 'workspace changed')
    require(f['total_wall_limit_seconds'] == 10800 and f['timeout_seconds_per_source'] == 1800, 'frozen resource caps')
    require(f['max_concurrent_source_processes'] == 6, 'fixed P6 allocation')
    require(f['analysis_runtime'] == runtime_identity(), 'analysis runtime changed')
    require(Path(f['analysis_script']).resolve() == Path(__file__).resolve() and f['analysis_script_sha256'] == sha(__file__), 'analysis source changed')


def state_key(row):
    return (int(row['sourceSeed']), int(row['decisionIdx']), row['type'])


def stage_rows(path, ks):
    # Parse the index before any efficacy field. Out-of-stage values are not
    # interpreted, retained, scored or returned. Hashing whole files is custody.
    with Path(path).open(newline='') as f:
        for row in csv.DictReader(f):
            k = int(row['k'])
            require(0 <= k < 32, 'unallocated future index')
            if k in ks:
                yield row


def build_states(option_rows, source_rows, allocated=SEEDS):
    options, sources = defaultdict(dict), {}
    for row in option_rows:
        key = state_key(row)
        require(key[0] in allocated and key[1] >= 0 and key[2] == 'BOSS_RELIC', 'unreserved option state')
        require(row['optionKey'] not in options[key], 'duplicate semantic option')
        require(row['chosen'] in ('0', '1'), 'invalid chosen flag')
        options[key][row['optionKey']] = row
    covered, empty = Counter(), set()
    for row in source_rows:
        seed = int(row['sourceSeed']); require(seed in allocated, 'unreserved source')
        require(row['trajectoryValid'] == '1', 'invalid source trajectory')
        covered[seed] += 1
        if int(row['decisionIdx']) < 0:
            require(row['decisionIdx'] == '-1' and row['type'] == '' and int(row['options']) == 0, 'noncanonical no-state source')
            empty.add(seed)
            continue
        key = state_key(row)
        require(key in options and key not in sources, 'source/option coverage or duplicate')
        require(1 <= len(options[key]) <= 6 and len(options[key]) == int(row['options']), 'retained option count')
        sources[key] = {k:row[k] for k in ('sourceSeed','decisionIdx','type','act','floor')}
    require(set(covered) == set(allocated) and all(n == 1 for n in covered.values()), 'one source row per allocated source required')
    require(set(sources) == set(options), 'source/option state coverage')
    require(not empty.intersection(k[0] for k in options), 'source marked empty and exposed')
    for rows in options.values():
        require(sum(int(r['chosen']) for r in rows.values()) == 1, 'actual baseline retention')
        require(len({int(r['optionIdx']) for r in rows.values()}) == len(rows), 'duplicate option index')
    return dict(options), sources


def context(freeze_path, freeze_sha, contract_path, contract_sha):
    inputs = {}
    freeze_path = checked(freeze_path, freeze_sha, inputs); freeze = read_json(freeze_path)
    validate_freeze(freeze)
    for path, digest in [(ROOT/'paired_analysis.py', BOOTSTRAP_SHA),
                         (OLD/'verify_gen2.py', OLD_VERIFIER_SHA),
                         (freeze['analysis_script'],freeze['analysis_script_sha256']),
                         (freeze['analysis_protocol'],freeze['analysis_protocol_sha256']),
                         (freeze['verifier'],freeze['verifier_sha256']),
                         (freeze['binary'],freeze['binary_sha256']),
                         (freeze['teacher'],freeze['teacher_sha256']),
                         (freeze['policy'],freeze['policy_sha256'])]:
        checked(path,digest,inputs)
    for path,digest in freeze['artifacts'].items():
        checked(ROOT/path,digest,inputs)
    contract_path = checked(contract_path,contract_sha,inputs); contract=read_json(contract_path)
    require(contract['status'] == 'CONTRACT_RECEIPT_PASS', 'invalid/incomplete collection')
    require(contract['freeze_sha256'] == freeze_sha and Path(contract['freeze']).resolve() == freeze_path, 'contract freeze binding')
    require(contract['verifier_sha256'] == freeze['verifier_sha256'] and contract['source_seeds'] == SEEDS, 'contract verifier/allocation binding')
    require(contract['source_trajectory_valid'] is True and contract['optional_recall_policy_bound_and_banner_checked'] is True, 'contract validity/corrected reference')
    require(contract['native_tree_health_checked'] is True and contract['native_tree_health_helper_sha256'] == HEALTH_HELPER_SHA, 'strict native tree health required')
    health = contract['native_tree_health']
    require(set(health) == {'fatal_findings','roots','completed_simulations','singleton_skips','cycle_rollouts','engine_stop','turn_limit'} and
            all(isinstance(value,int) and value >= 0 for value in health.values()) and health['fatal_findings'] == 0, 'invalid native tree health summary')
    require(contract['evaluation_outcomes_reported'] is False and 0 <= contract['states'] <= 32, 'contract scope/outcome barrier')
    raw = Path(freeze['raw_directory']).resolve()
    require(raw == ROOT/'build/overnight_20261008/learning/gen2-k-precision-3ed9', 'raw directory changed')
    expected = {raw/f'seed-{seed}.{role}' for seed in SEEDS for role in ROLES}
    supplied = [Path(x['path']).resolve() for x in contract['inputs']]
    require(len(supplied) == len(set(supplied)) and set(supplied) == expected, 'exact32 prefixes by8 input roles required')
    for item in contract['inputs']:
        checked(item['path'],item['sha256'],inputs)
    tables = {role:[raw/f'seed-{seed}.{role}' for seed in SEEDS] for role in ROLES}
    invocations = [read_json(p) for p in tables['receipt.json']]
    for seed,inv in zip(SEEDS,invocations):
        require(inv['source_seed'] == seed and inv['status'] == 'completed' and inv['exit_code'] == 0, 'source invocation failed')
        require(inv['freeze_sha256'] == freeze_sha and Path(inv['freeze']).resolve() == freeze_path, 'invocation freeze binding')
        require(all(math.isfinite(inv[k]) for k in ('started_epoch','finished_epoch','wall_seconds')), 'nonfinite invocation timing')
        require(freeze['frozen_epoch'] <= inv['started_epoch'] <= inv['finished_epoch'] <= freeze['absolute_stop_epoch'], 'freeze/absolute-stop chronology')
        require(0 <= inv['wall_seconds'] <= freeze['timeout_seconds_per_source'], 'per-source wall cap')
    require(max(r['finished_epoch'] for r in invocations)-min(r['started_epoch'] for r in invocations) <= freeze['total_wall_limit_seconds'], 'total wall cap')
    options,sources = build_states(
        [r for p in tables['options.csv'] for r in VERIFIER_HELPERS.table(p)],
        [r for p in tables['sources.csv'] for r in VERIFIER_HELPERS.table(p)])
    require(len(options) == contract['states'], 'contract state coverage')
    require(contract['no_state_sources'] == sorted(set(SEEDS)-{key[0] for key in options}), 'contract no-state coverage')
    require(sum(len(opts)*32 for opts in options.values()) == contract['label_rows'], 'contract branch count')
    return freeze,contract,tables,options,sources,inputs


def stage_labels(tables, options, ks):
    expected = {(s,option,k) for s,rows in options.items() for option in rows for k in ks}
    labels,maps = {},set()
    for path in tables['labels.csv']:
        for row in stage_rows(path,ks):
            state=state_key(row); key=(state,row['optionKey'],int(row['k']))
            require(key in expected and key not in labels, 'extra/duplicate stage label')
            require(row['valid']=='1' and not row['error'] and row['finalWon'] in ('0','1'), 'invalid stage outcome')
            opt=options[state][row['optionKey']]
            require(all(row[f]==opt[f] for f in ('optionIdx','chosen')), 'label action binding')
            future=int(hashlib.sha256(f'ooc-cf-pilot-v2-future:{state[0]}:{state[1]}:{key[2]}'.encode()).hexdigest()[:16],16)
            require(int(row['futureSeed'])==future,'coupled future identity')
            labels[key]=row
    require(set(labels)==expected,'incomplete stage labels')
    for path in tables['map.csv']:
        for row in stage_rows(path,ks):
            key=(state_key(row),row['optionKey'],int(row['k']))
            require(key in expected and key not in maps,'extra/duplicate stage MAP')
            require(all(row[f]==labels[key][f] for f in ('optionIdx','chosen','mapAct','mapFloor')),'stage MAP join')
            maps.add(key)
    require(maps==expected,'incomplete stage MAP coverage')
    return labels


def choose(scores, baseline):
    require(baseline in scores and scores and all(math.isfinite(x) for x in scores.values()), 'invalid selection scores')
    tied=[key for key,value in scores.items() if value==max(scores.values())]
    return baseline if baseline in tied else min(tied)


def selection_states(options,sources,labels):
    output=[]
    for state,opts in sorted(options.items()):
        baseline=next(k for k,r in opts.items() if r['chosen']=='1')
        scores={rule:{option:sum(int(labels[(state,option,k)]['finalWon']) for k in ks)/len(ks) for option in opts} for rule,ks in RULES.items()}
        output.append({'source_seed':state[0],'decision_idx':state[1],'type':state[2],
                       'act':int(sources[state]['act']),'floor':int(sources[state]['floor']),
                       'baseline_option_key':baseline,'scores':scores,
                       'choices':{rule:choose(scores[rule],baseline) for rule in RULES}})
    return output


def cluster_summary(gains, allocated=SEEDS):
    require(set(gains)<=set(allocated) and len(allocated)==len(set(allocated)), 'unallocated/duplicate source gain')
    require(all(len(xs)<=1 and all(math.isfinite(x) and -1<=x<=1 for x in xs) for xs in gains.values()),'invalid source gain or multiple states')
    values=[gains.get(seed,[0.0])[0] if gains.get(seed) else 0.0 for seed in allocated]
    mean,lo,hi=BOOTSTRAP.bootstrap_ci(np.asarray(values),n_boot=10000,ci=.95,rng=np.random.default_rng(20261008))
    return {'equal_source_mean_paired_gain':mean,'source_cluster_bootstrap_ci95':[lo,hi],
            'per_source_mean_paired_gain':dict(zip(map(str,allocated),values)),
            'allocated_source_clusters':len(allocated),'observed_source_clusters':sum(bool(gains.get(s)) for s in allocated),
            'bootstrap_unit':'whole allocated source run','bootstrap_replicates':10000,'bootstrap_seed':20261008,
            'no_state_rule':'valid no-state source contributes zero incremental gain'}


def classify(ci):
    lo,hi=ci
    require(math.isfinite(lo) and math.isfinite(hi) and lo<=hi,'invalid primary interval')
    return ('LOCAL_K16_SELECTION_GAIN_SUPPORTED' if lo>0 else
            'LOCAL_K16_SELECTION_HARM_SUPPORTED' if hi<0 else 'LOCAL_CONDITIONAL_INCONCLUSIVE')


def compare(left,right):
    require(len(left)==len(right)==16,'evaluation requires16paired futures')
    delta=[a-b for a,b in zip(left,right)]
    return {'left_wins':sum(left),'right_wins':sum(right),'left_only':sum(x>0 for x in delta),
            'right_only':sum(x<0 for x in delta),'both_win':sum(a==b==1 for a,b in zip(left,right)),
            'both_lose':sum(a==b==0 for a,b in zip(left,right)),'paired_gain':sum(delta)/16}


def evaluate_states(choice,options,sources,labels):
    frozen={(s['source_seed'],s['decision_idx'],s['type']):s for s in choice['states']}
    require(len(frozen)==len(choice['states']) and set(frozen)==set(options),'frozen state coverage')
    gains={name:defaultdict(list) for name in ('K16-K4','K4-baseline','K16-baseline')}; states=[]
    for state,opts in sorted(options.items()):
        fixed=frozen[state];baseline=fixed['baseline_option_key']
        require(baseline in opts and opts[baseline]['chosen']=='1','frozen actual baseline changed')
        require(fixed['act']==int(sources[state]['act']) and fixed['floor']==int(sources[state]['floor']),'frozen source location changed')
        require(set(fixed['choices'])==set(RULES) and all(x in opts for x in fixed['choices'].values()),'frozen action absent')
        win={name:[int(labels[(state,key,k)]['finalWon']) for k in EVAL_K] for name,key in dict(fixed['choices'],baseline=baseline).items()}
        comparisons={name:compare(win[left],win[right]) for name,left,right in [('K16-K4','K16','K4'),('K4-baseline','K4','baseline'),('K16-baseline','K16','baseline')]}
        for name,row in comparisons.items():gains[name][state[0]].append(row['paired_gain'])
        states.append({k:fixed[k] for k in ('source_seed','decision_idx','type','act','floor','baseline_option_key','choices')} | {'future_pairs':16,'comparisons':comparisons})
    summaries={name:cluster_summary(values) for name,values in gains.items()}
    for name,row in summaries.items():row['role']='single preregistered primary' if name=='K16-K4' else 'descriptive source-baseline comparison only; no decision rule'
    return states,summaries


def select(args):
    freeze,contract,tables,options,sources,inputs=context(args.freeze,args.freeze_sha,args.contract,args.contract_sha)
    labels=stage_labels(tables,options,RULES['K16'])
    return {'schema':'k_precision_choices_v1','status':'CHOICES_FROZEN','freeze':str(args.freeze.resolve()),'freeze_sha256':args.freeze_sha,
            'contract':str(args.contract.resolve()),'contract_sha256':args.contract_sha,
            'source_sha':SOURCE_SHA,'binary_sha256':BINARY_SHA,'source_seeds':SEEDS,
            'selection_k_by_rule':RULES,'evaluation_k':EVAL_K,'evaluation_outcomes_opened':False,
            'tie_rule':'highest selection mean; exact ties favor actual captured baseline, then semantic key lexicographic',
            'states':selection_states(options,sources,labels),'inputs':[{'path':p,'sha256':h} for p,h in sorted(inputs.items())],
            'frozen_epoch':time.time(),'analysis_script_sha256':sha(__file__),'analysis_runtime':runtime_identity(),'limits':LIMITS}


def evaluate(args):
    inputs={};choice_path=checked(args.choices,args.choices_sha,inputs);choice=read_json(choice_path)
    require(choice['status']=='CHOICES_FROZEN' and choice['analysis_script_sha256']==sha(__file__),'reviewed frozen choices required')
    require(choice['source_seeds']==SEEDS and choice['selection_k_by_rule']==RULES and choice['evaluation_k']==EVAL_K,'frozen allocation changed')
    require(choice['evaluation_outcomes_opened'] is False and choice['frozen_epoch']<time.time(),'frozen stage barrier')
    require(choice['analysis_runtime']==runtime_identity(),'choice runtime changed')
    for item in choice['inputs']:checked(item['path'],item['sha256'],inputs)
    freeze,contract,tables,options,sources,current=context(choice['freeze'],choice['freeze_sha256'],choice['contract'],choice['contract_sha256'])
    require({x['path']:x['sha256'] for x in choice['inputs']}==current,'frozen exact input set changed')
    inputs.update(current)
    # First evaluation efficacy interpretation occurs only after every choice/input binding passes.
    labels=stage_labels(tables,options,EVAL_K)
    states,summaries=evaluate_states(choice,options,sources,labels)
    return {'schema':'k_precision_evaluation_v1','status':'CONDITIONAL_EVALUATION_COMPLETE',
            'choice':str(choice_path),'choice_sha256':args.choices_sha,'freeze_sha256':choice['freeze_sha256'],
            'source_sha':SOURCE_SHA,'binary_sha256':BINARY_SHA,'source_seeds':SEEDS,
            'selection_k_by_rule':RULES,'evaluation_k':EVAL_K,'states':states,'summaries':summaries,
            'primary_comparison':'K16-K4','primary_classification':classify(summaries['K16-K4']['source_cluster_bootstrap_ci95']),
            'primary_decision_rule':'CI lower > 0 supports local K16 gain; upper < 0 supports local K16 harm; otherwise inconclusive; no2pp threshold',
            'contract_cost':{k:contract[k] for k in ('source_cpu_seconds','branch_cpu_seconds','invocation_wall_seconds_sum','label_rows')},
            'inputs':[{'path':p,'sha256':h} for p,h in sorted(inputs.items())],
            'evaluation_epoch':time.time(),'analysis_script_sha256':sha(__file__),'analysis_runtime':runtime_identity(),'limits':LIMITS}


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='stage',required=True)
    sub.add_parser('runtime')
    select_parser=sub.add_parser('select');select_parser.add_argument('--freeze',type=Path,required=True)
    select_parser.add_argument('--freeze-sha',required=True);select_parser.add_argument('--contract',type=Path,required=True)
    select_parser.add_argument('--contract-sha',required=True);select_parser.add_argument('--output',type=Path,required=True)
    eval_parser=sub.add_parser('evaluate');eval_parser.add_argument('--choices',type=Path,required=True)
    eval_parser.add_argument('--choices-sha',required=True);eval_parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.stage=='runtime':print(json.dumps(runtime_identity(),indent=2));return
    require(not args.output.exists() and not args.output.is_symlink(),'refusing overwrite')
    require(args.output.resolve().is_relative_to(HERE),'outputs must stay in owned analysis directory')
    result=select(args) if args.stage=='select' else evaluate(args)
    with args.output.open('x') as f:
        json.dump(result,f,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    print(json.dumps({'stage':args.stage,'status':result['status'],'output':str(args.output.resolve()),'sha256':sha(args.output),
                      **({'primary_classification':result['primary_classification']} if args.stage=='evaluate' else {})},indent=2))


if __name__=='__main__':
    main()
