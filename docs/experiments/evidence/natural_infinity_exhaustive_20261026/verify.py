#!/usr/bin/env python3
"""Offline evidence audit: no game, oracle, model inference, or retries."""
import gzip
import json
from stage_a import HERE, SOURCE, git, sha, check
from stage_b import custody
from freeze_b import freeze
from report import generate
from study import study


def rows(raw):
    return [json.loads(v) for v in raw[:raw.rfind(b'\n')+1].splitlines()]


def main():
    check()
    custody()
    for fight in (12,13):
        for name,body in freeze(fight).items():
            assert (HERE/f'combat{fight}'/name).read_text()==body
    for folder in (HERE,HERE/'combat12',HERE/'combat13'):
        for name,body in generate(folder).items():
            assert (folder/name).read_text()==body
    for name,body in study().items():
        assert (HERE/name).read_text()==body
    expected={name:rows(gzip.decompress(git(SOURCE+'capture/11111.'+name+'.gz'))) for name in ('trace.jsonl','states.jsonl')}
    phases={}
    for phase in ('discover12','capture12','capture13'):
        launch=json.loads((HERE/(phase+'.launch.json')).read_text())
        receipt=json.loads((HERE/(phase+'.receipt.json')).read_text())
        assert receipt['prefix_checked'] and receipt['command']==launch['command']
        gate=(HERE/'STAGE_A_GATE_AT_FIRST_LAUNCH.json' if phase=='discover12' else HERE/'RESULT.json').read_bytes()
        assert sha(gate)==receipt['stage_a_result_sha256']
        actual={}
        for name,ident in receipt['files'].items():
            packed=(HERE/(phase+'.'+name+'.gz')).read_bytes();raw=gzip.decompress(packed)
            assert sha(packed)==ident['compressed_sha256'] and sha(raw)==ident['sha256']
            if name in expected:
                actual[name]=rows(raw)
                assert actual[name][:len(expected[name])]==expected[name]
        assert all(r['integrity_so_far'] for r in actual['trace.jsonl'] if r.get('kind')=='infinity_mask_boundary')
        completed=[r for r in actual['trace.jsonl'] if r.get('kind')=='battle']
        assert max(r['fight'] for r in completed)<=13
        assert not any(r.get('kind')=='infinity_mask_boundary' and r['pre']['screen']=='BATTLE' and r['fight']>13
                       for r in actual['trace.jsonl'])
        for boundary in actual['trace.jsonl']:
            if boundary.get('kind')=='infinity_mask_boundary' and boundary['pre']['floor']>=18:
                inv=boundary['interventions']
                assert inv['matched']==5 and inv['failed']==inv['not_seen']==0
                assert sum(c.rstrip('+')=='Dropkick' for c in boundary['pre']['deck'])==2
        # Verify complete, unfiltered ordinary decision coverage against each raw capture.
        if phase!='discover12':
            capture=rows(gzip.decompress((HERE/(phase+'.public.jsonl.gz')).read_bytes()))
            assert [r['decision'] for r in capture]==list(range(1,len(capture)+1))
            assert all(r['capture_valid'] and r['configured_simulations']==10000 for r in capture)
            ordinary=[r['decision'] for r in capture if r['public_wire']['state']['inputState']==1]
            f=json.loads((HERE/('combat'+phase.removeprefix('capture'))/'FREEZE.json').read_text())
            assert ordinary==[r['decision'] for r in f['roots']]
        phases[phase]=dict(status=receipt['status'],prefix_trace_records=len(expected['trace.jsonl']),
                          prefix_state_records=len(expected['states.jsonl']),wall_seconds=receipt['wall_seconds'],
                          child_cpu_seconds=receipt['child_user_seconds']+receipt['child_system_seconds'])
        expected=actual
    assert phases['capture13']['status']=='THREE_COMBAT_HORIZON'
    final=json.loads((HERE/'STUDY.json').read_text())
    assert final['total_ordinary_roots']==66 and final['total_supported_worlds']==264
    assert final['stopping_label']=='TARGET_COMBAT_INCONCLUSIVE'
    assert [(a['fight'],a['decision'],a['cap_worlds'],a['unsupported_worlds']) for a in final['ambiguities']]==[(13,11,4,0)]
    print(json.dumps(dict(status='PASS',checks=['pinned artifacts and exhaustive freezes','source/binary/eight-model custody',
        'all raw archive and oracle receipt hashes','all matrices and whole-study regeneration',
        'three complete deterministic replay prefixes','complete ordinary-root coverage','five interventions only',
        'no fourth completed combat','fixed cap ambiguity retained, never negative'],phases=phases),indent=2))


if __name__=='__main__':
    main()
