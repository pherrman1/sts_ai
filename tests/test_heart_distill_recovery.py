import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from recover_heart_distill_test import check_repair, selection_for_recovery


class RecoveryTest(unittest.TestCase):
    def test_only_custody_references_change(self):
        old={'variant':'counts','init':0,'epoch':22,'weight':.5,'key':[.02,.01,12],
             'validation':{'mse':.1},'baseline':{'mse':.2},'checkpointSha256':'weights',
             'vocabularySha256':'vocab','freezeSha256':'old','toolSha256':'oldtool'}
        snapshot=copy.deepcopy(old)
        recovered=selection_for_recovery(old,'new','newtool')
        self.assertEqual(old,snapshot)
        changed={k for k in recovered if recovered[k]!=old[k]}
        self.assertEqual(changed,{'freezeSha256','toolSha256'})
        recovered['validation']['mse']=9
        self.assertEqual(old,snapshot)

    def test_exact_merged_repair_matches_original(self):
        import subprocess
        repo=Path(__file__).resolve().parents[1]
        original=subprocess.check_output(['git','show','cbded890a06f4ec76ad72c8333d07df25ad54e5f:tools/heart_rollout_distill.py'],cwd=repo,text=True)
        fixed=(repo/'tools/heart_rollout_distill.py').read_text()
        check_repair(original,fixed)
        with self.assertRaises(ValueError):check_repair(original,fixed.replace('speedup>=4','speedup>=2'))
        with self.assertRaises(ValueError):check_repair(original,original)


if __name__=='__main__':unittest.main()
