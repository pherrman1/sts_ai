"""Public-state accounting for exactly the frozen five-skip search; no simulator."""
from collections import Counter
import hashlib
import json

SEED=111101032

def sha_value(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
def core(state):
    cards=Counter(c.rstrip('+') for c in state['deck'])
    return {'dropkicks':cards['Dropkick'],'bash':cards['Bash']>0,'pommel':cards['Pommel Strike']>0}
def engine(state):
    c=core(state);return c['dropkicks']>=2 and c['bash'] and c['pommel']
def summary_check(summary,manifest):
    entries=summary['entries'];assert len(entries)==5 and summary['manifest_entries']==5
    assert [{k:v for k,v in r.items() if k not in ['status','error']} for r in entries]==manifest['interventions']
    counts=Counter(r['status'] for r in entries)
    assert set(counts)<= {'MATCHED_EXECUTED','NOT_SEEN','DISABLED_BY_DESIGN'}
    assert summary['failed']==0 and summary['matched']==counts['MATCHED_EXECUTED'] and summary['not_seen']==counts['NOT_SEEN'] and summary['disabled_by_design']==counts['DISABLED_BY_DESIGN']
    assert sum(counts.values())==5
    for row in entries:assert (row['status']=='DISABLED_BY_DESIGN')==(not row['enabled'])

def locate_stop(rows):
    """First predeclared entry/horizon/death endpoint; never score later records."""
    completion=None
    for index,row in enumerate(rows):
        kind=row.get('kind')
        if kind=='infinity_mask_boundary':
            state=row['pre']
            if completion is None and engine(state):completion={'row':index,'state':state,'source':'boundary'}
            if completion is not None and state['screen']=='BATTLE':
                return {'kind':'TARGET_REACHED','row':index,'completion':completion,'boundary':row}
            if completion is None and state['floor']>=19:
                return {'kind':'REGION_PASSED_WITHOUT_ENGINE','row':index,'completion':None,'boundary':row}
        elif kind in ['ooc','battle']:
            if completion is None and engine(row['post']):completion={'row':index,'state':row['post'],'source':'post','decision':row.get('idx')}
            if row['post']['hp']<=0:return {'kind':'DEAD','row':index,'completion':completion,'terminal':row}
    return None

def assess(mask,manifest,rows,endpoint,*,control=False):
    end=endpoint['row'];prefix=rows[:end+1]
    normal=[r for r in prefix if r.get('kind') in ['ooc','battle']]
    boundary=endpoint.get('boundary');state=boundary['pre'] if boundary else endpoint['terminal']['post']
    # Mask0 reuses qualification and logical disabled statuses; every other mask
    # uses the native checkpoint snapshot (or real normal-end summary on death).
    if control:
        entries=[dict(e,status='DISABLED_BY_DESIGN') for e in manifest['interventions']]
        summary={'entries':entries,'manifest_entries':5,'matched':0,'not_seen':0,'disabled_by_design':5,'failed':0}
    elif boundary:summary=boundary['interventions']
    else:
        summaries=[r for r in rows if r.get('kind')=='infinity_skip_summary'];assert len(summaries)==1;summary=summaries[0]
    summary_check(summary,manifest)
    fired=[r for r in normal if r.get('by')=='infinity_skip']
    assert len(fired)==summary['matched']
    assert len({(r['pre']['act'],r['pre']['floor']) for r in fired})==len(fired)
    for action in fired:
        item=next(e for e in summary['entries'] if e['act']==action['pre']['act'] and e['floor']==action['pre']['floor'])
        assert item['status']=='MATCHED_EXECUTED' and item['enabled']
        assert action['pre']['deck']==action['post']['deck']
    offered=[];pandora_choice=None
    for i,row in enumerate(prefix):
        if row.get('kind') not in ['ooc','battle']:continue
        relic_offers=row.get('offer',{}).get('relics',[])
        if any((r[0] if isinstance(r,list) else r)=='PANDORAS_BOX' for r in relic_offers):offered.append(i)
        if 'PANDORAS_BOX' not in row['pre']['relics'] and 'PANDORAS_BOX' in row['post']['relics']:
            added=Counter(row['post']['deck'])-Counter(row['pre']['deck'])
            removed=Counter(row['pre']['deck'])-Counter(row['post']['deck'])
            pandora_choice={'row':i,'decision':row.get('idx'),'act':row['pre']['act'],'floor':row['pre']['floor'],'by':row.get('by'),'added':dict(added),'removed':dict(removed),'dropkicks_produced':sum(n for c,n in added.items() if c.rstrip('+')=='Dropkick'),'pre':row['pre'],'post':row['post']}
            assert row.get('by')!='infinity_skip'
    completion=endpoint['completion'];target=None
    if endpoint['kind']=='TARGET_REACHED':
        target={'seed':SEED,'act':state['act'],'floor':state['floor'],'fight':boundary['fight'],'encounter':boundary['encounter'],'state':state,'pre_sha256':sha_value(state),'boundary_index':boundary['index']}
    result={'mask':f'{mask:05b}','numeric_mask':mask,'enabled_skip_count':mask.bit_count(),'matched':summary['matched'],'not_seen':summary['not_seen'],'disabled':summary['disabled_by_design'],'statuses':summary['entries'],'stop':endpoint['kind'],'highest_floor':state['floor'],'alive':state['hp']>0,'pandora_offered':bool(offered),'pandora_offer_rows':offered,'pandora_obtained':'PANDORAS_BOX' in state['relics'],'pandora_selected_naturally':pandora_choice is not None,'pandora_choice':pandora_choice,'dropkicks':core(state)['dropkicks'],'bash_present':core(state)['bash'],'pommel_present':core(state)['pommel'],'engine_complete':completion is not None,'engine_intact_at_target':bool(target and engine(state)),'engine_completion':completion,'permanent_deck_at_engine_completion':len(completion['state']['deck']) if completion else None,'target_alive':bool(target and state['hp']>0),'target':target,'target_deck_size':len(state['deck']) if target else None,'target_hp':state['hp'] if target else None,'current_deck_size':len(state['deck']),'endpoint_row':end,'prefix_sha256':sha_value(prefix),'oracle_executed':False}
    return result

def rank(row):
    return (-int(row['engine_complete']),-int(row['target_alive']),row['target_deck_size'] if row['target_deck_size'] is not None else 10**6,-(row['target_hp'] if row['target_hp'] is not None else -1),row['enabled_skip_count'],row['numeric_mask'])
def gate(row):return row['engine_complete'] and row['target_alive'] and row['engine_intact_at_target'] and row['target_deck_size']<=14

def control_result(manifest,trace):
    completion=None
    for i,row in enumerate(trace):
        if completion is None and engine(row['pre']):completion={'row':i,'state':row['pre'],'source':'pre'}
        if row['kind']=='battle' and completion is not None:
            boundary={'kind':'infinity_mask_boundary','index':i,'fight':row['fight'],'encounter':row['encounter'],'pre':row['pre']}
            # The qualification played this fight to establish parity. Its outcome
            # is deliberately excluded from all mask0 search measurements.
            prefix=trace[:i]+[boundary]
            return assess(0,manifest,prefix,{'kind':'TARGET_REACHED','row':i,'completion':completion,'boundary':boundary},control=True)
        if completion is None and engine(row['post']):completion={'row':i,'state':row['post'],'source':'post','decision':row.get('idx')}
    raise AssertionError('qualified historical target missing')
