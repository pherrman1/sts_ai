import unittest
from tools import combat_transition_shared_encoder_distill as screen


def metrics():
    maxhp=dict(overall=dict(rows=100,nll=.1,accuracy=.95,expectedPostMaxHpMae=.2),slices={
        "zeroDelta":dict(rows=90,nll=.02,accuracy=1.,expectedPostMaxHpMae=.01),
        "nonzeroDelta":dict(rows=10,nll=.8,accuracy=.6,expectedPostMaxHpMae=1.)})
    hp_overall=dict(rows=100,nll=2.,crps=3.,expectedMae=4.)
    hp=dict(overall=hp_overall,slices={name:dict(hp_overall,rows=20) for name in ("healing","lowPreHp","damage")})
    return {"maxHP":maxhp,"HP":hp}


class TestSharedEncoderDistill(unittest.TestCase):
    def test_go(self):
        teacher=metrics();student=metrics();student["HP"]["overall"]["nll"]*=1.019;student["maxHP"]["overall"]["accuracy"]-=.0049
        self.assertEqual(screen.classify(teacher,student)[0],"SHARED_TRANSITION_ENCODER_GO")

    def test_hp_slice_reject(self):
        teacher=metrics();student=metrics();student["HP"]["slices"]["healing"]["crps"]*=1.051
        self.assertEqual(screen.classify(teacher,student)[0],"SHARED_TRANSITION_ENCODER_REJECTED")

    def test_nonzero_accuracy_reject(self):
        teacher=metrics();student=metrics();student["maxHP"]["slices"]["nonzeroDelta"]["accuracy"]-=.051
        self.assertEqual(screen.classify(teacher,student)[0],"SHARED_TRANSITION_ENCODER_REJECTED")

    def test_kl_identity(self):
        import numpy as np
        p=np.array([[.25,.75]],np.float32)
        self.assertAlmostEqual(screen.kl(p,p),0.)

    def test_epoch_twelve_narrow_miss(self):
        teacher=metrics();student=metrics();student["HP"]["overall"]["nll"]*=1.021
        decision,gates=screen.classify(teacher,student)
        self.assertEqual(decision,"SHARED_TRANSITION_ENCODER_REJECTED")
        self.assertTrue(screen.narrow_miss(gates))


if __name__ == "__main__": unittest.main()
