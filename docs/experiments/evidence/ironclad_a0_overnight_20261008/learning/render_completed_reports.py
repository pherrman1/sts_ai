#!/usr/bin/env python3
"""Presentation only: fixed completed report inputs; no raw-file access or inference."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
EV = HERE.parent
FULL = [
    ('W1', 'wave1_report.json'), ('W2', 'wave2_report.json'),
    ('W3 screen', 'wave3_report.json'), ('W3 development', 'wave3_development_report.json'),
    ('Removal screen', 'wave4_removal_report.json'),
    ('Removal development', 'removal_development_report.json'),
    ('Card rank screen', 'wave5_card_rank_report.json'),
]
CONDITIONAL = [
    ('GEN2 canary', 'learning/gen2_probe_3ed9_evaluation.json'),
    ('GEN2 tranche', 'learning/gen2_tranche32_3ed9_evaluation.json'),
    ('Targeted REST', 'learning/targeted_rest_631f_evaluation_result.json'),
    ('Champ D13', 'audit/champ_d13_evaluation_report.json'),
]


def read_report(rel, expected_sha=None):
    # Never follow the report's input paths, manifests, receipts or raw data.
    path = EV / rel
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if expected_sha and sha != expected_sha:
        raise ValueError('completed report hash mismatch: '+rel)
    return json.loads(raw), dict(path=str(path), sha256=sha, bytes=len(raw))


def finite_nonnegative(x):
    return isinstance(x, (float, int)) and math.isfinite(x) and x >= 0


def full_report(label, rel, expected_sha=None):
    d, identity = read_report(rel, expected_sha)
    if d.get('all_pairs_complete') is not True or not d.get('comparisons'):
        raise ValueError('incomplete report: '+rel)
    if label == 'Final confirmation' and d.get('phase') != 'confirmation':
        raise ValueError('optional final report is not a confirmation report')
    for arm in d['arms'].values():
        if not all(finite_nonnegative(arm[k]) for k in ['n', 'wins', 'observed_profile_thread_cpu_seconds_sum', 'process_wall_seconds_sum']):
            raise ValueError('missing or invalid completed arm/cost metadata')
    comparisons = []
    for name, row in d['comparisons'].items():
        matches = [(c,b) for c in d['arms'] for b in d['arms'] if f'{c}-{b}' == name]
        if len(matches) != 1:
            raise ValueError('ambiguous comparison name')
        candidate, control = matches[0]
        if row['pairs'] != d['arms'][candidate]['n'] or row['pairs'] != d['arms'][control]['n']:
            raise ValueError('completed report sample mismatch')
        comparisons.append(dict(name=name, candidate=candidate, control=control, **row))
    return dict(label=label, report=identity, phase=d['phase'], source_sha=d['source_sha'],
                binary_sha256=d['binary_sha256'], manifest_sha256=d['manifest_sha256'],
                analysis_script_sha256=d['analysis_script_sha256'],
                comparison_scope=d.get('comparison_scope'), arms=d['arms'], comparisons=comparisons)


def conditional_report(label, rel):
    d, identity = read_report(rel)
    if d.get('status') not in ('DIAGNOSTIC_EVALUATION_COMPLETE', 'EVALUATION_INTEGRITY_PASS'):
        raise ValueError('conditional report not complete')
    result = dict(label=label, report=identity, raw_status=d['status'],
                  raw_classification=d.get('classification', d.get('primary_classification')),
                  limits=d.get('limits', d.get('limitations')), source_sha=d.get('source_sha'),
                  freeze_sha256=d.get('freeze_sha256'), rows=[])
    if label.startswith('GEN2'):
        result.update(source_clusters=len(d['source_seeds']), states=len(d['states']),
                      selection_k=d['selection_k'], evaluation_k=d['evaluation_k'],
                      cost=d['contract_cost'], inference=d['inference'])
        for rule, summary in d['summaries'].items():
            # Descriptive sum of already-reported counts; never used for gain/CI.
            rows = [s['rules'][rule] for s in d['states']]
            result['rows'].append(dict(rule=rule, pairs=sum(s['future_pairs'] for s in d['states']),
                selected_wins=sum(r['selected_wins'] for r in rows),
                baseline_wins=sum(s['baseline_wins'] for s in d['states']),
                candidate_only=sum(r['selected_only'] for r in rows), control_only=sum(r['baseline_only'] for r in rows),
                gain=summary['equal_source_mean_paired_gain'],
                ci95=summary.get('source_cluster_bootstrap_ci95'), action_changes=summary['action_changes'],
                role=summary.get('role', 'descriptive canary rule'),
                raw_classification=d.get('primary_classification') if rule == d.get('primary_rule') else None))
    elif label == 'Targeted REST':
        result.update(source_clusters=d['independent_source_decisions'], states=1,
                      evaluation_k=d['evaluation_k'], cost={k:d[k] for k in ['source_cpu_seconds','branch_cpu_seconds','process_wall_seconds']})
        result['rows'] = [dict(rule=f"{d['selected_action']} vs {d['baseline_action']}",
            pairs=d['conditional_future_pairs'], selected_wins=d['selected_wins'], baseline_wins=d['baseline_wins'],
            candidate_only=d['selected_only'], control_only=d['baseline_only'], gain=d['paired_gain'],
            ci95=d['paired_bootstrap_ci95'], raw_classification=d['classification'])]
    else:
        if d.get('stage') != 'evaluation' or d.get('failures'):
            raise ValueError('invalid Champ evaluation')
        result.update(source_clusters=d['independent_source_decisions'], states=1,
                      evaluation_k=d['allocated_k'], cost={k:d[k] for k in ['cpu_seconds_by_arm','process_wall_seconds']})
        result['rows'] = [dict(rule='SHRUG vs END (fight wins)', pairs=d['pairs'],
            selected_wins=d['wins']['SHRUG'], baseline_wins=d['wins']['END'],
            candidate_only=d['shrug_only'], control_only=d['end_only'], gain=d['paired_gain'],
            ci95=d['paired_bootstrap_ci95'], raw_classification=d['classification'])]
    return result


def effect(row):
    ci = row['ci95']
    return f"{100*row['gain']:+.3f}" + (f" [{100*ci[0]:+.3f}, {100*ci[1]:+.3f}]" if ci is not None else ' [no CI recorded]')


def render(data):
    lines = ['# Completed campaign results', '',
        'Presentation of frozen reports only. Every recorded decision is reproduced verbatim. Controls remain within their original phase/source; no pooled control, combined efficacy estimate or campaign cost total is produced.', '',
        'Full-run comparison effects and intervals are in percentage points, candidate minus control. C-only/B-only are the two paired discordances. The reported paired bootstrap intervals are copied, not recalculated.', '',
        '| Report / phase | Source SHA | Candidate / control | Pairs | Wins C / B | C-only / B-only | Gain [95% CI], pp | Raw decision |',
        '|---|---|---|---:|---:|---:|---|---|']
    for report in data['full_run_reports']:
        for row in report['comparisons']:
            c,b = report['arms'][row['candidate']],report['arms'][row['control']]
            lines.append(f"| {report['label']} / {report['phase']} | `{report['source_sha'][:12]}` | {row['candidate']} / {row['control']} | {row['pairs']} | {c['wins']} / {b['wins']} | {row['candidate_only']} / {row['control_only']} | {effect(row)} | `{row['decision']}` |")
    lines += ['', 'W1 is the early fair-public diagnostic before the optional-Recall correction. Later corrected-reference results are separate. Discovery cohorts were reused adaptively for screening; they are not fresh qualification samples. Full-run win counts concern the fixed Act-3 endpoint.', '',
        'Observed cost, listed once per report/arm. CPU is the reported sum of profile thread-CPU seconds, not total machine utilization. Wall is the sum of invocation process durations, not parallel campaign elapsed time. A control repeated in comparison rows has only this one cost row; controls from overlapping seed cohorts are not pooled or presented as independent efficacy evidence.', '',
        '| Report | Arm | Runs | Observed profile CPU, s | Summed process wall, s |', '|---|---|---:|---:|---:|']
    for r in data['full_run_reports']:
        for name,a in r['arms'].items():
            lines.append(f"| {r['label']} | {name} | {a['n']} | {a['observed_profile_thread_cpu_seconds_sum']:.3f} | {a['process_wall_seconds_sum']:.3f} |")
    lines += ['', 'Conditional probes remain separate from whole-run policy evidence. GEN2 wins/discordances below are descriptive totals over correlated state/future pairs; its gain and CI use the frozen equal-source estimand. Those totals must not be used to replace the source-cluster analysis. REST and Champ each have one selected source state; their intervals resample conditional future pairs.', '',
        '| Probe / rule | Sources / states | Conditional pairs | Wins C / B | C-only / B-only | Gain [95% CI], pp | Exact recorded classification |',
        '|---|---:|---:|---:|---:|---|---|']
    for p in data['conditional_reports']:
        for r in p['rows']:
            verdict=r.get('raw_classification')
            lines.append(f"| {p['label']} / {r['rule']} | {p['source_clusters']} / {p['states']} | {r['pairs']} | {r['selected_wins']} / {r['baseline_wins']} | {r['candidate_only']} / {r['control_only']} | {effect(r)} | " + (f'`{verdict}`' if verdict else 'No per-rule classification recorded') + ' |')
    lines += ['', '| Conditional report | Exact status | CPU seconds | Process wall seconds |', '|---|---|---|---:|']
    for p in data['conditional_reports']:
        cost=p['cost']
        if 'cpu_seconds_by_arm' in cost:
            cpu=', '.join(f'{arm}: {value:.3f}' for arm,value in cost['cpu_seconds_by_arm'].items())
        else:
            cpu=f"source: {cost['source_cpu_seconds']:.3f}; branches: {cost['branch_cpu_seconds']:.3f}"
        wall=cost.get('process_wall_seconds',cost.get('invocation_wall_seconds_sum'))
        lines.append(f"| {p['label']} | `{p['raw_status']}` | {cpu} | {wall:.3f} |")
    lines += ['', 'GEN2 collection cost covers source runs and all retained branches across both selection and evaluation futures, shared by all three frozen rules. It is not three independent per-rule costs. REST/Champ cost here is their evaluation-stage report only, excluding preparatory selection/canaries.', '',
        'Conditional scope and limitations copied from the reports:', '']
    for p in data['conditional_reports']:
        lines.append(f"- **{p['label']}**: " + ' '.join(p['limits']))
    lines += ['', 'The GEN2 tranche rollout rule is the preregistered primary; P0/F2 are secondary exploratory rules. The four-source canary is descriptive only. Champ measures a single fight outcome, whereas REST/GEN2 continuations use the recorded run endpoint.', '',
        'Frozen report identities (no referenced raw inputs were opened):', '', '| Report | SHA256 |', '|---|---|']
    for r in data['full_run_reports']+data['conditional_reports']:
        lines.append(f"| [{r['label']}]({r['report']['path']}) | `{r['report']['sha256']}` |")
    lines += ['', 'Knowledge impact: presentation of existing experiment evidence; no new analysis, verdict, policy or qualification claim.']
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-prefix',type=Path,required=True)
    parser.add_argument('--completed-final-report-sha256',help='Explicitly include ONLY completed final_confirmation_report.json with this exact hash')
    args=parser.parse_args()
    paths=[Path(str(args.output_prefix)+ext).resolve() for ext in ('.json','.md')]
    if any(p.exists() for p in paths) or any(not p.is_relative_to(HERE) for p in paths):
        raise ValueError('Use new output paths under learning; existing outputs are never replaced')
    full=[full_report(label,rel) for label,rel in FULL]
    if args.completed_final_report_sha256:
        full.append(full_report('Final confirmation','final_confirmation_report.json',args.completed_final_report_sha256))
    data=dict(schema='completed_report_presentation_v1', created_utc=datetime.now(timezone.utc).isoformat(),
              rendering_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              final_report_included=bool(args.completed_final_report_sha256),
              full_run_reports=full,conditional_reports=[conditional_report(label,rel) for label,rel in CONDITIONAL])
    for path,body in zip(paths,[json.dumps(data,indent=2)+'\n',render(data)]):
        with path.open('x') as f:f.write(body)
    print(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},indent=2))


if __name__=='__main__':
    main()
