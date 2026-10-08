#!/usr/bin/env python3
"""Count observed or explicitly inferred optional RECALL in completed Fprod traces."""
import argparse
from collections import Counter,defaultdict
import csv,hashlib,json
from pathlib import Path
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(); p.add_argument('run_dir',type=Path); p.add_argument('--out',required=True,type=Path)
    a=p.parse_args(); inputs=[]; cases=[]; covered=set(); rests=0
    for receipt_path in sorted(a.run_dir.glob('Fprod_*.receipt.json')):
        receipt=json.loads(receipt_path.read_text())
        if receipt['status']!='completed' or receipt['exit_code']!=0: raise ValueError('unfinished Fprod attempt')
        for key in ('csv','trace','strategic'):
            record=receipt['outputs'][key]
            if sha(record['path'])!=record['sha256']: raise ValueError('changed '+key)
            inputs.append({'path':record['path'],'sha256':record['sha256']})
        csvpath=Path(receipt['outputs']['csv']['path'])
        with csvpath.open() as f:
            seeds={int(r['seed']) for r in csv.DictReader(f)}
        if covered&seeds: raise ValueError('duplicate sources')
        covered|=seeds
        strategic_path=Path(receipt['outputs']['strategic']['path'])
        strategic=defaultdict(list)
        with strategic_path.open() as f:
            for line,r in enumerate(csv.DictReader(f),2):
                if r['screen']=='7': strategic[(int(r['seed']),int(r['act']),int(r['floor']))].append((line,r))
        trace_path=Path(receipt['outputs']['trace']['path'])
        rows=[]
        with trace_path.open() as f:
            for line,raw in enumerate(f,1):
                r=json.loads(raw)
                if r['kind']=='ooc' and r['pre']['screen']=='REST': rows.append((line,r))
        for position,(line,row) in enumerate(rows):
            pre,post=row['pre'],row['post']; seed=int(row['seed']); key=(seed,pre['act'],pre['floor'])
            rests+=1
            matching=strategic.get(key,[])
            if len(matching)!=1: raise ValueError('nonunique strategic REST join '+str(key))
            sline,s=matching[0]; bits=[int(b) for b in s['actionBits'].split('|')]
            if 2 not in bits or len(bits)==1: continue
            take=int(s['takeIdx']); owned=s['owned']=='1'
            chosen=bits[take] if owned else None
            same_inventory=all(Counter(pre[k])==Counter(post[k]) for k in ('deck','relics','potions'))
            no_visible_change=(pre['hp']==post['hp'] and pre['maxHp']==post['maxHp']
                and pre['gold']==post['gold'] and same_inventory and post['screen']=='MAP')
            later=[]
            for nl,nxt in rows[position+1:]:
                if int(nxt['seed'])!=seed: continue
                nkey=(seed,nxt['pre']['act'],nxt['pre']['floor'])
                for _,ns in strategic[nkey]: later.append([int(b) for b in ns['actionBits'].split('|')])
            disappeared=bool(later) and all(2 not in b for b in later)
            classification=None; basis=[]
            if owned and chosen==2:
                classification='DIRECT_STRATEGIC_RECALL'; basis=['owned strategic action bits2; other legal choices existed']
            elif not owned and no_visible_change:
                if disappeared:
                    classification='INFERRED_FALLBACK_RECALL'; basis=['declined strategic gate','no visible change','all later REST menus omit Ruby option']
                elif pre['hp']<pre['maxHp'] and 'MARK_OF_THE_BLOOM' not in pre['relics'] and not ({3,6}&set(bits)):
                    classification='INFERRED_FALLBACK_RECALL'; basis=['declined strategic gate','only Ruby matches transition among captured legal actions','heal would change HP; smith/toke/dig change screen']
                else:
                    classification='AMBIGUOUS_FALLBACK_NO_VISIBLE_CHANGE'; basis=['could be full-health REST or counter-only action; no later Ruby menu witness']
            if classification:
                cases.append({'seed':seed,'act':pre['act'],'floor':pre['floor'],'hp':pre['hp'],'max_hp':pre['maxHp'],
                  'trace_locator':str(trace_path)+':'+str(line),'strategic_locator':str(strategic_path)+':'+str(sline),
                  'trace_idx':row['idx'],'classification':classification,'basis':basis,'legal_action_bits':bits,
                  'selected_action_bits':chosen,'strategic_owned':owned,'strategic_margin':float(s['bestSecondMargin']),
                  'later_ruby_option_absent':disappeared,'relics':pre['relics']})
    if covered!=set(range(610081000,610081032)): raise ValueError('requires exactly frozen32 Fprod sources')
    result={'schema':'overnight_optional_recall_audit_v1','source_seeds':sorted(covered),'rest_decisions':rests,
      'counts':dict(Counter(c['classification'] for c in cases)), 'cases':cases,'inputs':inputs,
      'script_sha256':sha(__file__),
      'limits':['Strategic files use CSV despite .jsonl suffix. Outcome columns were not used for counting.',
      'OOC trace omits keys and exact fallback action; inference categories remain distinct from direct selected-action evidence.',
      'Optional means Ruby plus at least one other captured legal action. Forced-only Ruby is excluded.',
      'No counterfactual quality claim; this counts exposure to the keys-off contract violation.']}
    with a.out.open('x') as f: json.dump(result,f,indent=2); f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['inputs']},indent=2))

if __name__=='__main__': main()
