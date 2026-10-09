"""#418 G14: runtime support-only output against the census digest."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools import ctm_support_census_check as check


def census(path, supported):
    digest = hashlib.sha256(''.join(f'{i}\n' for i in supported).encode()).hexdigest()
    path.write_text(json.dumps(dict(groups=dict(all=dict(counts=dict(rows=4, supported=len(supported)),
                                                          supportedIndexSha256=digest)))))


class TestSupportCensusCheck(unittest.TestCase):
    def test_match_and_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            runtime = d / 'runtime.jsonl'
            runtime.write_text(''.join(json.dumps(dict(index=i, supported=i != 2, reason='' if i != 2 else 'smoke_bomb')) + '\n'
                                       for i in range(4)))
            census(d / 'same.json', [0, 1, 3])
            result = check.check(runtime, d / 'same.json')
            self.assertTrue(result['match'])
            self.assertEqual(result['runtimeReasons'], {'smoke_bomb': 1})
            census(d / 'other.json', [0, 1, 2])
            self.assertFalse(check.check(runtime, d / 'other.json')['match'])


if __name__ == '__main__':
    unittest.main()
