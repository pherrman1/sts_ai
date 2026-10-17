#!/usr/bin/env python3
"""Export the §494 rollout-target student (selected.pt + vocabulary.json) for native C++.

Reads the PyTorch zip checkpoint without torch: a restricted unpickler that only
rebuilds float tensors and an OrderedDict. Output (little-endian):
  b'STSRSD01', u32 tensors, then per tensor u32 name length, name, u32 ndim,
  u32 dims..., float32 data (row-major); then u32 vocabulary size and per entry
  u32 length + UTF-8 feature name, in DictVectorizer column order.

  rollout_student_export.py export <selected.pt> <vocabulary.json> <out.bin>
  rollout_student_export.py reference <selected.pt> <vocabulary.json> <rows.jsonl> <out.jsonl>
      numpy forward of the attention student on captured sibling rows
      ({"record":..., "x2b":...}); used for native parity.
"""
import collections
import json
import pickle
import struct
import sys
import zipfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from heart_record_encoder import encode_record  # noqa: E402

DTYPES = {'FloatStorage': np.float32, 'LongStorage': np.int64}


def load_state(path):
    z = zipfile.ZipFile(path)
    prefix = z.namelist()[0].split('/')[0]
    if z.read(f'{prefix}/byteorder').decode() != 'little':
        raise ValueError('big-endian checkpoint')

    def rebuild(storage, offset, size, stride, *_):
        data = storage[offset:]
        return np.lib.stride_tricks.as_strided(data, shape=tuple(size),
                                               strides=tuple(s * data.itemsize for s in stride)).copy()

    class Unpickler(pickle.Unpickler):
        def find_class(self, module, name):
            if (module, name) == ('torch._utils', '_rebuild_tensor_v2'):
                return rebuild
            if (module, name) == ('collections', 'OrderedDict'):
                return collections.OrderedDict
            if module == 'torch' and name in DTYPES:
                return name
            raise pickle.UnpicklingError(f'refusing {module}.{name}')

        def persistent_load(self, pid):
            kind, storage, key, _location, numel = pid
            if kind != 'storage' or storage not in DTYPES:
                raise pickle.UnpicklingError('unexpected storage')
            data = np.frombuffer(z.read(f'{prefix}/data/{key}'), dtype=DTYPES[storage])
            if len(data) != numel:
                raise ValueError('storage size mismatch')
            return data

    return Unpickler(z.open(f'{prefix}/data.pkl')).load()


def export(pt, vocabulary, out):
    state = load_state(pt)
    names = json.loads(Path(vocabulary).read_text())
    with open(out, 'wb') as f:
        f.write(b'STSRSD01')
        f.write(struct.pack('<I', len(state)))
        for name, t in state.items():
            t = np.ascontiguousarray(t, dtype=np.float32)
            f.write(struct.pack('<I', len(name)) + name.encode())
            f.write(struct.pack('<I', t.ndim) + struct.pack(f'<{t.ndim}I', *t.shape))
            f.write(t.astype('<f4').tobytes())
        f.write(struct.pack('<I', len(names)))
        for n in names:
            b = n.encode()
            f.write(struct.pack('<I', len(b)) + b)
    print(json.dumps({'tensors': {k: list(v.shape) for k, v in state.items()}, 'vocabulary': len(names)}))


def layer_norm(x, w, b, eps=1e-5):
    m = x.mean(-1, keepdims=True)
    v = ((x - m) ** 2).mean(-1, keepdims=True)
    return (x - m) / np.sqrt(v + eps) * w + b


def forward(state, columns, record, x2b):
    """float64 reference of heart_rollout_distill.Net('attention') for one row."""
    s = {k: v.astype(np.float64) for k, v in state.items()}
    features, tokens = encode_record(record)
    x = np.zeros(len(columns))
    for k, v in features.items():
        if k in columns:
            x[columns[k]] = v
    t = np.stack([s['kind.weight'][k] + s['entity.weight'][e] + s['attrs.weight'] @ np.array(a)
                  for k, e, a in tokens])
    h = np.concatenate([s['cls'][0], t])
    for i in range(2):
        p = f'encoder.layers.{i}.'
        y = layer_norm(h, s[p + 'norm1.weight'], s[p + 'norm1.bias'])
        qkv = y @ s[p + 'self_attn.in_proj_weight'].T + s[p + 'self_attn.in_proj_bias']
        q, k, v = np.split(qkv, 3, axis=1)
        heads = []
        for j in range(4):
            sl = slice(16 * j, 16 * (j + 1))
            a = q[:, sl] @ k[:, sl].T / 4.0
            a = np.exp(a - a.max(1, keepdims=True))
            heads.append((a / a.sum(1, keepdims=True)) @ v[:, sl])
        h = h + np.concatenate(heads, 1) @ s[p + 'self_attn.out_proj.weight'].T + s[p + 'self_attn.out_proj.bias']
        y = layer_norm(h, s[p + 'norm2.weight'], s[p + 'norm2.bias'])
        y = np.maximum(y @ s[p + 'linear1.weight'].T + s[p + 'linear1.bias'], 0)
        h = h + y @ s[p + 'linear2.weight'].T + s[p + 'linear2.bias']
    z = np.concatenate([x, h[0]])
    for i in (0, 2, 4):
        z = z @ s[f'layers.{i}.weight'].T + s[f'layers.{i}.bias']
        if i != 4:
            z = np.maximum(z, 0)
    base = min(max(x2b, 1e-4), 1 - 1e-4)
    return float(1 / (1 + np.exp(-(z[0] + np.log(base / (1 - base))))))


def reference(pt, vocabulary, rows, out):
    state = load_state(pt)
    columns = {n: i for i, n in enumerate(json.loads(Path(vocabulary).read_text()))}
    with open(out, 'w') as f:
        for line in open(rows):
            r = json.loads(line)
            f.write(json.dumps({'value': forward(state, columns, r['record'], r['x2b'])}) + '\n')


if __name__ == '__main__':
    {'export': export, 'reference': reference}[sys.argv[1]](*sys.argv[2:])
