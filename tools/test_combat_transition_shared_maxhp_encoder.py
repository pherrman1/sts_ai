import unittest
from tools import combat_transition_shared_maxhp_encoder as screen


class TestSharedMaxHpEncoderScreen(unittest.TestCase):
    def test_pass(self):
        a=dict(nll=.1,accuracy=.95,expectedPostMaxHpMae=.2);b=dict(nll=.1009,accuracy=.946,expectedPostMaxHpMae=.29)
        self.assertEqual(screen.classify(a,b)[0],'GO_TO_SHARED_HP_ENCODER_POTION_STAGE')

    def test_reject(self):
        a=dict(nll=.1,accuracy=.95,expectedPostMaxHpMae=.2);b=dict(nll=.102,accuracy=.95,expectedPostMaxHpMae=.2)
        self.assertEqual(screen.classify(a,b)[0],'SHARED_HP_ENCODER_MAXHP_REJECTED')

    def test_close_is_inconclusive(self):
        a=dict(nll=.1,accuracy=.95,expectedPostMaxHpMae=.2);b=dict(nll=.1011,accuracy=.95,expectedPostMaxHpMae=.2)
        self.assertEqual(screen.classify(a,b)[0],'INCONCLUSIVE')


if __name__=='__main__':unittest.main()
