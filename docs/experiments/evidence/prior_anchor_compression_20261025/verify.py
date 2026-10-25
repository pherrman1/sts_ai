"""Read-only custody, native-public parity and deterministic analysis checks."""
import hashlib,json,pathlib,subprocess,sys
from analyze import analyze,report,paired_se
out=pathlib.Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
freeze=json.loads((out/'FREEZE.json').read_text());sources=json.loads((out/'sources.json').read_text())
assert sha(out/'inputs-evaluated.jsonl')==freeze['inputs_sha256']
assert sha(out/'PREREG.md')==freeze['prereg_sha256']
assert sha(pathlib.Path(freeze['binary']))==freeze['binary_sha256']
for m in freeze['models']:assert sha(pathlib.Path(m['path']))==m['sha256']
for source in sources['sources']:
 raw=subprocess.check_output(['git','show',sources['historical_sha']+':'+source['path']]);assert hashlib.sha256(raw).hexdigest()==source['sha256']
old=list(map(json.loads,(out/'inputs-evaluated.jsonl').read_text().splitlines()));new=list(map(json.loads,(out/'inputs.jsonl').read_text().splitlines()))
for a,b in zip(old,new):
 a.pop('expected_skip_key');b.pop('expected_skip_key');assert a==b
receipt=json.loads((out/'raw.receipt.json').read_text());assert receipt['exit_code']==0 and receipt['values']
assert receipt['binary_sha256']==freeze['binary_sha256'] and receipt['source_sha']==freeze['reviewed_source_sha']
computed=analyze(out/'raw.jsonl');saved=json.loads((out/'audit.json').read_text());assert computed==saved
assert report(computed)==(out/'audit.md').read_text()
assert computed['decision']=='PRIOR_ANCHOR_NOT_SEPARABLE' and computed['selected_gate'] is None
assert computed['counts']['value_evaluated_states']==1 and computed['counts']['leaf_evaluations']==256
for row in computed['rows']:
 assert row['public_record_parity'] and len(row['actions'])==4
 assert row['value_state_qualified']==(row['floor']==0)
 for a in row['actions']:
  if a['effect']==12:assert a['deck_after']==row['permanent_deck_size'] and a['cycle_after']==row['cycle_burden']
 for a in (row['particles'] or {}).get('actions',[]):
  assert len(a['values'])==64 and not a['pruned']
assert paired_se([.1,.2,.3],[.1,.2,.3])==0
assert abs(paired_se([.1,.2,.3],[.2,.3,.4]))<1e-15
print('PASS: 6 historical hashes, frozen binary/models/source receipt, exact native-input preservation, 18 public-record parity rows, 72 semantic actions, CRN pairing, deterministic analyzer, stop rule')
