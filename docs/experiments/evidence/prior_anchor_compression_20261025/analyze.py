"""Fixed safety gates; no threshold fitting or new game evaluation."""
import argparse,json,math,pathlib,statistics

def paired_se(a,b):
    if len(a)!=len(b) or len(a)<2:raise ValueError('unpaired/inadequate CRN observations')
    return statistics.stdev([x-y for x,y in zip(a,b)])/math.sqrt(len(a))

def analyze(path):
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    if len(rows)!=18:raise ValueError('expected 18 historical executed skips')
    for row in rows:
        actions=row['actions'];ranked=sorted(actions,key=lambda a:(-a['prior'],a['id']))
        if not math.isclose(sum(a['prior'] for a in actions),1,abs_tol=1e-12):raise ValueError('not probabilities')
        if row['heart1_prior_nodes']!=1 or row['heart1_prior_fallbacks']:raise ValueError('prior fell back')
        stats={a['id']:a for a in row['particles']['actions']} if row['particles'] else {}
        complete=stats and all(not a['pruned'] and a['particles']==64 for a in stats.values())
        best=max(stats.values(),key=lambda a:(a['mean'],-a['id'])) if complete else None
        for i,a in enumerate(ranked):
            a['prior_rank']=i+1;a['log_prior_gap']=math.log(ranked[0]['raw_prior_weight'])-math.log(a['raw_prior_weight'])
            a['P4']=i<4;a['P2']=a['log_prior_gap']<=2.0
            a.update(value_mean=None,value_se=None,value_gap=None,combined_se=None,V5=None)
            if best:
                s=stats[a['id']];combined=paired_se(s['values'],best['values'])
                gap=best['mean']-s['mean'];a.update(value_mean=s['mean'],value_se=s['stdErr'],
                    value_gap=gap,combined_se=combined,V5=(i==0 or gap<=max(0.05,2*combined)))
            elif i==0:a['V5']=True # prior argmax always eligible, even if value unavailable
        skips=[a for a in actions if a['effect']==12]
        if len(skips)!=1:raise ValueError('skip identity ambiguous')
        inputs=[json.loads(line) for line in (path.parent/'inputs.jsonl').read_text().splitlines()]
        expected=next(r for r in inputs if r['case']==row['case'] and r['decision']==row['decision'])
        if skips[0]['key']!=expected['expected_skip_key']:raise ValueError('frozen skip semantic identity mismatch')
        row['skip']=skips[0];row['prior_argmax_id']=ranked[0]['id']
    positives=[r for r in rows if r['case']=='032/11111'];assert len(positives)==5
    negative=next(r for r in rows if r['case']=='326/13-skip' and r['floor']==0)
    gates={}
    for gate in ['P4','P2','V5']:
        p=[r['skip'][gate] for r in positives];bad=negative['skip'][gate]
        passed=all(v is True for v in p) and bad is False
        failed=any(v is False for v in p) or bad is True
        gates[gate]={'positive_eligible':p,'destructive_eligible':bad,'status':'PASS' if passed else 'FAIL' if failed else 'UNAVAILABLE'}
    selected=next((g for g in ['P4','P2','V5'] if gates[g]['status']=='PASS'),None)
    decision='STAGE_A_PASS' if selected else 'PRIOR_ANCHOR_NOT_SEPARABLE' if all(g['status']=='FAIL' for g in gates.values()) else 'AUDIT_INCONCLUSIVE'
    counts={'states':len(rows),'positive':len(positives),'actions':sum(len(r['actions']) for r in rows),
      'value_qualified_states':sum(r['value_state_qualified'] for r in rows),
      'value_evaluated_states':sum(r['particles'] is not None for r in rows),
      'leaf_evaluations':sum(r['particles']['evaluations'] for r in rows if r['particles']),
      'transitions':sum(r['particles']['transitions'] for r in rows if r['particles']),
      'terminal_particles':sum(r['particles']['terminalParticles'] for r in rows if r['particles']),
      'evaluation_cpu_seconds':sum(r['particles']['cpuSeconds'] for r in rows if r['particles'])}
    return {'decision':decision,'selected_gate':selected,'gates':gates,'counts':counts,'rows':rows}

def report(result):
    lines=['# Fixed Stage A separability audit','',f"Decision: **{result['decision']}**. Selected gate: {result['selected_gate']}.",'',
      'Skip probabilities/ranks use the existing planner semantic action set after its ordinary forced-gold and tree-rule reward collection. Each audited root then has three card takes and one skip. Log gaps use unnormalized weights, which give the same log probability gaps. Ties use deterministic action ID.','',
      '| Case | decision / state index | floor | deck | burden | skip p | rank | log gap | value mean ± SE | gap | paired SE | P4 | P2 | V5 |',
      '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|:---:|']
    def num(v):return 'null' if v is None else f'{v:.6g}'
    def eligible(v):return 'null' if v is None else 'yes' if v else 'no'
    for r in result['rows']:
      a=r['skip'];lines.append(f"| {r['case']} | {r['decision']} / {r['state_index']} | {r['floor']} | {r['permanent_deck_size']} | {r['cycle_burden']} | {a['prior']:.6g} | {a['prior_rank']} | {a['log_prior_gap']:.4f} | {num(a['value_mean'])} ± {num(a['value_se'])} | {num(a['value_gap'])} | {num(a['combined_se'])} | {eligible(a['P4'])} | {eligible(a['P2'])} | {eligible(a['V5'])} |")
    lines+=['','All skip actions preserve the displayed deck size and burden. Full candidate before/after counts, semantic identities, prior statistics, value availability and particle arrays are in audit.json.', '',
      'Later CRN values are null because retained public records lack exact replay snapshots and latent transition/continuation state. They were never sent to the value evaluator. The exact initial Neow root requires full restored public-record equality and uses the current deployed rollout3/CTM/X2-B+M0 stack. If V5 admits this known destructive action, that alone fails its required separation condition; missing positive values cannot change that failure.','',
      'Gate results: `'+json.dumps(result['gates'],sort_keys=True)+'`.', '',
      'Resource counts: `'+json.dumps(result['counts'],sort_keys=True)+'`.','',
      'This Stage A audit contains no Stage B planner, positive challenge, negative challenge or current-policy campaign result. Historical later 326 skips are not labeled individually destructive.']
    return '\n'.join(lines)+'\n'

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input',type=pathlib.Path);p.add_argument('output',type=pathlib.Path);a=p.parse_args()
    result=analyze(a.input);a.output.write_text(json.dumps(result,indent=2)+'\n');a.output.with_suffix('.md').write_text(report(result))
    print(json.dumps({k:result[k] for k in ['decision','selected_gate','gates','counts']},indent=2))
