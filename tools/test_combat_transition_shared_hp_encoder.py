import unittest
from tools import combat_transition_shared_hp_encoder as screen


class TestSharedHpEncoderScreen(unittest.TestCase):
    def test_gate_pass(self):
        a=dict(nll=2.,crps=3.,expectedMae=4.)
        b=dict(nll=2.019,crps=3.029,expectedMae=4.1)
        decision,gates=screen.classify(a,b,{})
        self.assertEqual(decision,"GO_TO_SHARED_ENCODER_NEXT_STAGE")
        self.assertAlmostEqual(gates["nllRelative"],.0095)

    def test_gate_reject(self):
        a=dict(nll=2.,crps=3.,expectedMae=4.)
        b=dict(nll=2.03,crps=3.,expectedMae=4.)
        self.assertEqual(screen.classify(a,b,{})[0],"SHARED_ENCODER_HP_REJECTED")

    def test_close_gate_is_inconclusive(self):
        a=dict(nll=2.,crps=3.,expectedMae=4.)
        b=dict(nll=2.022,crps=3.,expectedMae=4.)
        self.assertEqual(screen.classify(a,b,{})[0],"INCONCLUSIVE")

    def test_large_slice_regression_rejects(self):
        a=dict(nll=2.,crps=3.,expectedMae=4.)
        bad=dict(rows=100,nllRelative=.051,crpsRelative=0.,expectedMaeDelta=0.)
        self.assertEqual(screen.classify(a,a,{"lowHp":bad})[0],"SHARED_ENCODER_HP_REJECTED")


if __name__=="__main__":
    unittest.main()
