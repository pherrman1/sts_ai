#!/usr/bin/env python3
"""Scorer for STS_OOC_VALUE_CHOOSER (apps/one_combat/ooc_mcts_adapter.h): JSON lines on stdin
{"act": A, "floor": F, "records": [public records]} -> {"values": [V_A{A}(record)]} on stdout, with the stage-5b
models (§725, value_clean_labels_capture2_20261030/stage5b.py; V_A1 d7e69feed627, V_A2 e557c80cbfa6) and the
full encoder they were fitted with. Scores on CSR input, as fitted (absent = missing, §725 eval bug).
usage: value_chooser_server.py MODEL_DIR   (holds V_A1.pkl, V_A2.pkl[, V_A3.pkl])"""
import sys, os, json, pickle, hashlib
HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.join(HERE, '..')
sys.path.insert(0, os.path.join(EV, 'value_clean_labels_capture2_20261030'))
from stage5b import VCal, SF  # noqa: E402,F401  (VCal: the pickles name __main__.VCal)
SHA = {'V_A1.pkl': 'd7e69feed627', 'V_A2.pkl': 'e557c80cbfa6', 'V_A3.pkl': 'f4d72f665452'}


def load(model_dir):
    models = {}
    for name, sha in SHA.items():
        p = os.path.join(model_dir, name)
        if not os.path.exists(p): continue
        raw = open(p, 'rb').read()
        if hashlib.sha256(raw).hexdigest()[:12] != sha: raise SystemExit(f'bad {p}')
        models[int(name[3])] = pickle.loads(raw)
    return models


def main(model_dir):
    models = load(model_dir)
    print(f'[value_chooser] loaded acts {sorted(models)} from {model_dir}', file=sys.stderr, flush=True)
    for line in sys.stdin:
        req = json.loads(line)
        try:
            V = models[int(req['act'])]
            X = SF.csr([SF.enc(r) for r in req['records']])
            out = {'values': [float(v) for v in V(X)]}
        except Exception as e:  # noqa: BLE001  the engine refuses the reply and stops the run
            out = {'error': repr(e)}
        sys.stdout.write(json.dumps(out) + '\n'); sys.stdout.flush()


if __name__ == '__main__':
    main(sys.argv[1])
