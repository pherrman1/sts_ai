"""Mixed-cache label isolation and selected public-input extraction; no fit."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import ctm_development_cache as diagnostic


FIELDS = {'ids', 'win', 'split', 'source', 'target', 'mask', 'features', 'preHp',
          'preMax', 'trueHp', 'trueMax', 'potions', 'capacity', 'candidates',
          'legal', 'z', 'pDelta', 'potionZ'}

POISON = np.int64(0x0102030405060708)


def mixed_cache():
    arrays = {key: np.array([10, 20, POISON], dtype=np.int64) for key in FIELDS}
    arrays.update(split=np.array([0, 1, 2]), source=np.array([100, 200, 300]),
                  ids=np.array([1, 4, 8]))
    return arrays


def npy(array):
    out = io.BytesIO(); np.save(out, array, allow_pickle=True)
    return out.getvalue()


class DevelopmentCacheTest(unittest.TestCase):
    def test_unsigned_descending_ids_cannot_wrap_into_increasing_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'descending.npz'; arrays = mixed_cache()
            arrays['ids'] = np.array([8, 4, 1], dtype=np.uint64)
            np.savez_compressed(path, **arrays)
            with self.assertRaisesRegex(ValueError, 'row/split'): diagnostic.sanitize(path, FIELDS)
            public = Path(directory)/'public.npz'; np.savez_compressed(public, global_categories=np.ones((10, 4), np.int64))
            with self.assertRaisesRegex(ValueError, 'alignment'):
                diagnostic.selected_public_categories(public, np.array([8, 4, 1], dtype=np.uint64))

    def test_mixed_labels_are_never_decoded_and_test_poison_never_escapes(self):
        # Every non-metadata member has TEST poison. An eager NPZ load or a
        # numerical decode before row selection fails this tripwire.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'mixed.npz'; np.savez_compressed(path, **mixed_cache())
            real_decode = np.frombuffer
            decoded = []
            def protected(raw, *args, **kwargs):
                self.assertNotIn(POISON.tobytes(), raw, 'TEST label reached numerical decoder')
                decoded.append(len(raw))
                return real_decode(raw, *args, **kwargs)
            with patch.object(np, 'frombuffer', side_effect=protected):
                cache = diagnostic.sanitize(path, FIELDS)
            self.assertTrue(decoded)
            self.assertEqual(cache['split'].tolist(), [0, 1])
            self.assertEqual(cache['target'].tolist(), [10, 20])
            for array in cache.values():
                self.assertEqual(len(array), 2)
                self.assertFalse(np.any(array == POISON))

    def test_source_overlap_is_refused_before_label_decode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'overlap.npz'; arrays = mixed_cache()
            arrays['source'][2] = arrays['source'][0]; np.savez_compressed(path, **arrays)
            real = diagnostic.selected_rows
            calls = []
            def read(*args):
                calls.append(1); return real(*args)
            with patch.object(diagnostic, 'selected_rows', side_effect=read):
                with self.assertRaisesRegex(ValueError, 'source crosses'):
                    diagnostic.sanitize(path, FIELDS)
            self.assertEqual(len(calls), 3)  # Only split/source/ids were decoded.

    def test_public_features_decode_only_selected_development_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'public.npz'
            public = np.full((10, 4), POISON, dtype=np.int64)
            public[1] = [0, 49, 1, 2]; public[4] = [0, 2, 1, 2]
            np.savez_compressed(path, global_categories=public,
                                y_post_hp=np.full(10, POISON, dtype=np.int64))
            real = np.frombuffer
            def protected(raw, *args, **kwargs):
                self.assertNotIn(POISON.tobytes(), raw)
                return real(raw, *args, **kwargs)
            with patch.object(np, 'frombuffer', side_effect=protected):
                self.assertEqual(diagnostic.selected_public_categories(path, np.array([1, 4]))[:, 1].tolist(), [49, 2])

    def test_extractor_rejects_object_fortran_truncated_or_trailing_arrays(self):
        for array in (np.array([object()], dtype=object), np.asfortranarray(np.ones((2, 2)))):
            with self.assertRaisesRegex(ValueError, 'shape/dtype/order'):
                diagnostic.header(io.BytesIO(npy(array)))
        for raw, message in ((b'\0'*7, 'truncated'), (b'\0'*9, 'trailing')):
            with self.assertRaisesRegex(ValueError, message):
                diagnostic.selected_rows(io.BytesIO(raw), (1,), np.dtype('int64'), np.array([True]))

    def test_extractor_rejects_duplicate_archive_members_and_row_disagreement(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'duplicate.npz'
            with zipfile.ZipFile(path, 'w') as archive:
                for key, value in mixed_cache().items(): archive.writestr(key+'.npy', npy(value))
                archive.writestr('target.npy', npy(np.array([0])))
            with self.assertRaisesRegex(ValueError, 'members differ'): diagnostic.sanitize(path, FIELDS)
            path = Path(directory)/'misaligned.npz'; arrays = mixed_cache(); arrays['target'] = np.array([0, 1])
            np.savez_compressed(path, **arrays)
            with self.assertRaisesRegex(ValueError, 'alignment'): diagnostic.sanitize(path, FIELDS)







if __name__ == '__main__':
    unittest.main()
