import csv,json,re,sys
from pathlib import Path
folder=Path(sys.argv[1]); name=sys.argv[2]; start,count=map(int,sys.argv[3:]); expected=set(range(start,start+count))
def rows(suffix):
 with (folder/(name+suffix)).open() as f: data=list(csv.DictReader(f))
 result={int(r['seed']):r for r in data}
 assert len(data)==len(result)==count and set(result)==expected
 return result
actual=rows('.csv'); trace=rows('.csv.mcts.csv')
enabled=json.loads((folder/(name+'.config.json')).read_text())['env']['STS_OOC_MCTS']=='1'
reasons=[json.loads(line) for line in (folder/(name+'.csv.mcts.csv.support.jsonl')).read_text().splitlines()]
assert len(reasons)==count and {r['seed'] for r in reasons}==expected
for r in reasons: assert sum(r['reasons'].values())==int(trace[r['seed']]['unsupportedCombats'])
for r in trace.values():
 owned,fallback,aborts,discarded,completed,attempted=[int(r[k]) for k in ('mctsOwned','mctsFallback','mctsSupportAborts','discardedSimulations','simulations','simulationAttempts')]
 assert completed==10000*owned+discarded and attempted==completed+aborts
 assert int(r['unsupportedCombats'])==aborts<=fallback and 0<=discarded<=9999*aborts
 assert int(r['imaginedCombats'])==int(r['combatSurrogateSamples'])+aborts
 assert (int(r['oocDecisions'])==owned+fallback) if enabled else (owned+fallback+completed+attempted==0)
 assert 0<=int(r['maxDepth'])<=32 and int(r['realCombats'])>0
 assert int(r['battleLeaves'])==0
log=(folder/(name+'.log')).read_text()
assert len(re.findall(r'\[silver-combat\]',log))==sum(int(r['realCombats']) for r in trace.values())
assert not re.findall(r'(?:conversion_failures|semantic_resolution_failures|transaction_failures|knowledge_failures)=[1-9][0-9]*',log)
meta=json.loads((folder/(name+'.csv.meta.json')).read_text())
assert meta['nSeeds']==count and meta['threads']==24 and meta['seedBlock']=={'lo':start,'hi':start+count-1}
assert meta['config']['executableGitSha']=='54f2820f426c45540b02eb075cf73102b00de8f0'
assert meta['sims']==10000 and meta['asc']==0 and meta['config']['effectiveCombatBackend']=='silver' and meta['config']['silverExactRootBudgets'] and meta['config']['fairPlay']
print(json.dumps({'arm':name,'rows':count,'validation':'PASS','wins':sum(int(r['won']) for r in actual.values()),'owned':sum(int(r['mctsOwned']) for r in trace.values()),'supportAborts':sum(int(r['mctsSupportAborts']) for r in trace.values()),'surrogateSamples':sum(int(r['combatSurrogateSamples']) for r in trace.values()),'realCombats':sum(int(r['realCombats']) for r in trace.values()),'maxDepth':max(int(r['maxDepth']) for r in trace.values())},indent=2))
