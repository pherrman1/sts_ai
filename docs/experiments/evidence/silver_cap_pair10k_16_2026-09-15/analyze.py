import csv,json,statistics,re,math,gzip
from pathlib import Path
p=Path(__file__).resolve().parent
def rows(name):
    path=p/name
    with (path.open() if path.exists() else gzip.open(str(path)+'.gz','rt')) as f:
        return list(csv.DictReader(f))
summary={}; results={};decisions={}
for cap in (32768,131072):
    k=str(cap);rr=rows(k+'.csv');dd=rows(k+'-decisions.csv');results[k]={int(r['seed']):r for r in rr};decisions[k]=dd
    assert len(rr)==16 and set(results[k])==set(range(16))
    assert all(int(r['configured_cap'])==cap and r['configured_cap_mode']=='allocated' and int(r['configured_simulations'])==int(r['simulations_added'])==10000 for r in dd)
    assert set(int(r['run_seed']) for r in dd)==set(range(16))
    pressure=[r for r in dd if r['exact_candidate_found']=='1' and int(r['allocated_nodes_before_root'])>=cap]
    log=gzip.decompress((p/(k+'.log.gz')).read_bytes()).decode();rss=int(re.search(r'Maximum resident set size \(kbytes\): (\d+)',(p/(k+'-time.txt')).read_text())[1])
    telemetry=[l for l in log.splitlines() if l.startswith('[silver-combat]')]
    assert telemetry and all(not re.search(r'(?:conversion_failures|semantic_resolution_failures|transaction_failures|knowledge_failures)=[1-9]',l) for l in telemetry)
    assert not re.search(r'(?:simulatorHealthFailures|fatalFailures)=[1-9]',log)
    summary[k]={'wins':sum(int(r['won']) for r in rr),'mean_floor':statistics.mean(int(r['floor']) for r in rr),'mean_hp':statistics.mean(int(r['hpEnd']) for r in rr),'mean_seconds':statistics.mean(float(r['sec']) for r in rr),'decisions':len(dd),'exact_reroots':sum(int(r['exact_reroot']) for r in dd),'cap_pressure_candidates':len(pressure),'cap_pressure_rescued':sum(r['exact_reroot']=='1' for r in pressure),'allocated_cap_fallbacks':sum(r['fallback_reason']=='allocated_cap' for r in dd),'max_allocated_before_root':max(int(r['allocated_nodes_before_root']) for r in dd),'max_allocated_after_search':max(int(r['allocated_nodes_after_search']) for r in dd),'total_nodes_created':sum(int(r['nodes_created']) for r in dd),'peak_process_rss_kib':rss,'silver_combat_records':len([l for l in log.splitlines() if l.startswith('[silver-combat]')]),'failure_lines':[l for l in log.splitlines() if any(t in l.lower() for t in ['fatalfailure','simulator health failure','silver live backend failure'])]}
a,b=results['32768'],results['131072']
summary['paired']={'32k_only_win':[s for s in a if a[s]['won']=='1' and b[s]['won']=='0'],'128k_only_win':[s for s in a if b[s]['won']=='1' and a[s]['won']=='0'],'non_timing_rows_identical':[s for s in a if all(a[s][k]==b[s][k] for k in a[s] if k!='sec')]}
n=len(summary['paired']['32k_only_win'])+len(summary['paired']['128k_only_win'])
k=min(len(summary['paired']['32k_only_win']),len(summary['paired']['128k_only_win']))
summary['paired']['exact_two_sided_discordant_p']=min(1,2*sum(math.comb(n,i) for i in range(k+1))/2**n) if n else 1
ma=json.loads((p/'32768.csv.meta.json').read_text());mb=json.loads((p/'131072.csv.meta.json').read_text())
assert ma['config']['executableGitSha']==mb['config']['executableGitSha']=='2b29e9723a00b9dc6fcea45507e4dcf86c968cde'
for m in (ma,mb):
    assert (m['sims'],m['nSeeds'],m['asc'],m['threads'])==(10000,16,0,4)
    for key in ('silverReuseCap','silverScalingDiagnosticFile'):m['config'].pop(key)
assert ma['config']==mb['config'] and ma['models']==mb['models']
first=[]
for seed in range(16):
    aa=[r for r in decisions['32768'] if int(r['run_seed'])==seed]
    bb=[r for r in decisions['131072'] if int(r['run_seed'])==seed]
    diff=next(((i,x,y) for i,(x,y) in enumerate(zip(aa,bb)) if any(x[k]!=y[k] for k in x if k!='configured_cap')),None)
    if diff:
        i,x,y=diff
        assert int(x['allocated_nodes_before_root'])>=32768, f'prepressure divergence seed{seed}: {x}'
        first.append({'seed':seed,'index':i,'floor':x['floor'],'before_32k':x['allocated_nodes_before_root'],'before_128k':y['allocated_nodes_before_root'],'different_columns':[k for k in x if k!='configured_cap' and x[k]!=y[k]]})
summary['first_diagnostic_difference']=first
summary['prepressure_diagnostics_identical']=True
paired=[]
for s in sorted(a):paired.append({'seed':s,'won_32k':a[s]['won'],'won_128k':b[s]['won'],'floor_32k':a[s]['floor'],'floor_128k':b[s]['floor'],'hp_32k':a[s]['hpEnd'],'hp_128k':b[s]['hpEnd'],'seconds_32k':a[s]['sec'],'seconds_128k':b[s]['sec']})
with (p/'paired-seeds.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=paired[0],lineterminator="\n");w.writeheader();w.writerows(paired)
(p/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
