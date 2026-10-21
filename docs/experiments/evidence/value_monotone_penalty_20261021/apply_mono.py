"""Apply the --mono-* edits of main's tools/heart1/distill.py to the gen-2 sweep's patched distill.py.

usage: apply_mono.py MAIN_DISTILL_PY TARGET_DISTILL_PY (TARGET edited in place). Every anchor must match once."""
import sys
main_new, target = sys.argv[1], sys.argv[2]
m = open(main_new).read(); s = open(target).read()
def block(start, end):  # text in main_new from start up to (not incl) end
    i = m.index(start); return m[i:m.index(end, i)]
def rep(old, new):
    global s
    assert s.count(old) == 1, old; s = s.replace(old, new)
rep('--select last keeps the last epoch', block('--mono-weight M adds', '--select last keeps') + '--select last keeps the last epoch')
rep('a = ap.parse_args()', block('ap.add_argument("--mono-weight"', 'a = ap.parse_args()') + 'a = ap.parse_args()')
rep('def outputs_of(model, b):\n', 'def outputs_of(model, b, amp=True):\n')
rep('enabled=a.amp and a.device.startswith("cuda")', 'enabled=amp and a.amp and a.device.startswith("cuda")')
rep('opt = torch.optim.AdamW(', block('mono_rules = [r for r', 'opt = torch.optim.AdamW(') + 'opt = torch.optim.AdamW(')
rep('    tot = n = 0\n', '    tot = n = mono_tot = 0\n')
rep('''        kl, bce, anc, _, _ = losses(b, m, t, full, z)
        loss = combine(kl, bce, anc, m, z); opt.zero_grad(set_to_none=True); loss.backward()''',
    block('        kl, bce, anc, _, v = losses', '        torch.nn.utils.clip_grad_norm_').rstrip('\n'))
rep('"train_rows": n})\n', '"train_rows": n})\n' + block('    if a.mono_weight: hist[-1]', '    print(f"ep {ep+1}'))
rep('print("best per group:", json.dumps(best[2]), flush=True)\njson.dump({',
    block('print("best per group:"', 'json.dump({') + 'json.dump({"monotone": mono, ')
open(target, 'w').write(s)
