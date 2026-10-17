"""Stream reviewed CTM cache rows without numerical decoding of held-out labels.

Callers must bind input custody and split/index provenance. This module has no
model training, scoring, qualification, source rebinding, or deployment path.
"""
import math
import zipfile
import numpy as np


def require(ok, message):
    if not ok:
        raise ValueError(message)


def header(stream):
    version = np.lib.format.read_magic(stream)
    require(version in ((1, 0), (2, 0)), 'unsupported NPY version')
    shape, fortran, dtype = (np.lib.format.read_array_header_1_0(stream)
                            if version == (1, 0) else np.lib.format.read_array_header_2_0(stream))
    require(not fortran and not dtype.hasobject and dtype.kind in 'biuf'
            and dtype.itemsize in (1, 2, 4, 8) and len(shape) >= 1
            and all(isinstance(d, int) and 0 < d <= 1_000_000 for d in shape)
            and math.prod(shape)*dtype.itemsize <= 256*1024*1024,
            'unsupported cache array shape/dtype/order')
    return shape, dtype


def selected_rows(stream, shape, dtype, keep):
    """Decode selected C-order rows only, including no TEST label conversion."""
    require(shape[0] == len(keep), 'cache row alignment differs')
    width = math.prod(shape[1:])*dtype.itemsize
    result = np.empty((int(keep.sum()), *shape[1:]), dtype=dtype)
    out = 0
    for active in keep:
        raw = stream.read(width)
        require(len(raw) == width, 'truncated cache row')
        if active:
            result[out] = np.frombuffer(raw, dtype=dtype).reshape(shape[1:])
            out += 1
    require(not stream.read(1), 'trailing cache bytes')
    return result


def sanitize(path, expected_fields):
    """Use metadata to exclude split 2 before decoding any label member."""
    with zipfile.ZipFile(path) as archive:
        require(len(archive.namelist()) == len(expected_fields)
                and set(archive.namelist()) == {k+'.npy' for k in expected_fields}, 'cache members differ')
        metadata = {}
        for key in ('split', 'source', 'ids'):
            with archive.open(key+'.npy') as stream:
                shape, dtype = header(stream)
                require(len(shape) == 1 and dtype.kind in 'iu', 'invalid split metadata')
                metadata[key] = selected_rows(stream, shape, dtype, np.ones(shape[0], bool))
        split, source, ids = (metadata[k] for k in ('split', 'source', 'ids'))
        require(len(split) == len(source) == len(ids) and np.isin(split, [0, 1, 2]).all()
                and np.all(ids[1:] > ids[:-1]), 'invalid row/split metadata')
        source_sets = [set(source[split == s].tolist()) for s in range(3)]
        require(all(not source_sets[a] & source_sets[b] for a, b in ((0, 1), (0, 2), (1, 2))),
                'source crosses split boundary')
        keep = split != 2
        cache = {k: v[keep] for k, v in metadata.items()}
        for key in sorted(set(expected_fields)-set(metadata)):
            with archive.open(key+'.npy') as stream:
                shape, dtype = header(stream)
                cache[key] = selected_rows(stream, shape, dtype, keep)
        require(set(cache['split']) == {0, 1}, 'missing development split')
        return cache


def selected_public_categories(path, selected_ids):
    """Read only selected public input rows; do not decode other split features."""
    with zipfile.ZipFile(path) as archive, archive.open('global_categories.npy') as stream:
        shape, dtype = header(stream)
        require(len(shape) == 2 and shape[1] == 4 and dtype.kind in 'iu'
                and len(selected_ids) > 0 and np.all(selected_ids[1:] > selected_ids[:-1]) and selected_ids[0] >= 0
                and selected_ids[-1] < shape[0], 'public category row alignment differs')
        keep = np.zeros(shape[0], bool); keep[selected_ids] = True
        return selected_rows(stream, shape, dtype, keep)
