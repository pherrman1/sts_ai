import copy
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import torch

from tools import train_silver_prior as t
from tools.silver_prior_projection import GLOBAL, PLAYER


class SilverPriorTrainingTests(unittest.TestCase):
    def observation(self):
        return {
            "schema": "silver_prior_observation_v1",
            "global": {**{k: 0 for k in GLOBAL}, "encounter": 1, "turn": 1},
            "player": {**{k: 0 for k in PLAYER}, "stance": 0, "characterClass": 0,
                       "statusPresence": [3], "justApplied": [3], "statusAmounts": [{"kind": 3, "amount": 2}],
                       "relicPresence": [5], "relicCounters": [{"counter_kind": 0, "amount": 0}],
                       "bombs": [{"timing": i, "amount": 0} for i in range(3)],
                       "orangePelletsCardTypesPlayed": [], "lastTargetedMonster": 0},
            "evaluation_context": {"effectiveGold": 0, "maxHp": 80},
            "cards": [{"card_id": 1, "zone": "hand", "segment": "observed", "specialData": 0,
                       "cost": 1, "costForTurn": 1, "position": 0, "upgraded": False,
                       "freeToPlayOnce": False, "retain": False, "ref": 0},
                      {"card_id": 2, "zone": "drawPile", "segment": "unknown", "specialData": 0,
                       "cost": 1, "costForTurn": 1, "position": None, "upgraded": False,
                       "freeToPlayOnce": False, "retain": False, "ref": 1}],
            "zones": {"hand": [0], "limbo": [], "stasisCards": []},
            "piles": {z: {"knownBottom": [], "unknown": [1] if z == "drawPile" else [],
                          "knownTop": [], "fullOrderObserved": False}
                      for z in ("drawPile", "discardPile", "exhaustPile")},
            "monsters": [{"ref": 0, "present": True, "id": 1, "curHp": 10, "maxHp": 10, "block": 0,
                          "strength": 0, "vulnerable": 0, "weak": 0, "uniquePower0": 0,
                          "uniquePower1": 0, "miscInfo": 0, "isEscapingB": False, "halfDead": False,
                          "escapeNext": False, "alive": True, "moveHistory": [1], "powers": [2],
                          "smallPowers": [{"amount": 0, "kind": str(i)} for i in range(11)]}],
            "potions": [{"slot": i, "potion_id": 1, "available": True, "empty": True} for i in range(5)],
            "miscFlags": [], "extraRollMoveSlots": [], "skipMonsterTurnSlots": [],
            "candidates": [{"type": 1, "source_zone": 1, "card_ref": 0, "target_ref": 0,
                            "potion_id": None, "potion_slot": None, "discardPotion": False,
                            "skipCardSelect": False, "cardSelectTask": 0},
                           {"type": 5, "source_zone": 0, "card_ref": None, "target_ref": None,
                            "potion_id": None, "potion_slot": None, "discardPotion": False,
                            "skipCardSelect": False, "cardSelectTask": 0}],
        }

    def model(self):
        return t.SilverPriorNetV1(len(t._numeric_fields(self.observation()))).eval()

    def row(self,obs=None,values=None,seed=1,rid="r1"):
        return (self.observation() if obs is None else obs,[1.,0.] if values is None else values,seed,rid)

    def test_candidate_and_label_permutation_invariance(self):
        x=t.collate_rows([self.row(values=[3.,0.])]);m=self.model();z=m(x);y,owner,n=t.ragged_targets(x["root_values"],1.0);loss=t.ragged_root_ce(z,y,owner,n)
        for k in ("candidate_root","candidate_card","candidate_mon","candidate_pot","candidate_features"):x[k]=x[k].flip(0)
        x["labels"]=x["labels"].flip(0)
        self.assertTrue(torch.allclose(loss,t.ragged_root_ce(m(x),y.flip(0),owner.flip(0),n),atol=1e-7))

    def test_provenance_ids_and_card_uids_do_not_change_predictions(self):
        m=self.model();a=m(t.collate_rows([self.row()]));obs=copy.deepcopy(self.observation());obs["cards"][0]["uniqueId"]=999999
        b=m(t.collate_rows([self.row(obs,seed=987654,rid="different-root")]))
        self.assertTrue(torch.equal(a,b))

    def test_unknown_pile_order_invariant_observed_order_can_change_state(self):
        m=self.model();obs=self.observation();a=m(t.collate_rows([self.row(obs)]));obs["cards"].reverse();b=m(t.collate_rows([self.row(obs)]))
        self.assertTrue(torch.allclose(a,b,atol=1e-7))
        obs=self.observation();obs["cards"][0]["position"]=2;c=m(t.collate_rows([self.row(obs)]));self.assertFalse(torch.equal(a,c))

    def test_card_occurrence_features_and_target_reference_affect_logits(self):
        m=self.model();obs=self.observation();x=t.collate_rows([self.row(obs)]);a=m(x)
        changed=copy.deepcopy(obs);changed["cards"][0]["cost"]=2;changed["cards"][0]["specialData"]=1
        b=m(t.collate_rows([self.row(changed)]));self.assertFalse(torch.equal(a,b))
        changed=copy.deepcopy(obs);changed["candidates"][0]["target_ref"]=None
        self.assertFalse(torch.equal(a,m(t.collate_rows([self.row(changed)]))))

    def test_absent_monster_is_not_present_zero_hp(self):
        m=self.model();obs=self.observation();obs["monsters"][0].update(curHp=0,alive=False);a=m(t.collate_rows([self.row(obs)]))
        obs["monsters"][0]["present"]=False;b=m(t.collate_rows([self.row(obs)]));self.assertFalse(torch.equal(a,b))

    def test_excluded_card_fails_closed(self):
        obs=self.observation();obs["cards"][0]["card_id"]=158
        with self.assertRaisesRegex(ValueError,"excluded or unmapped"):t.collate_rows([self.row(obs)])

    def test_grouped_softmax_and_root_equal_loss_weight(self):
        p=t.grouped_softmax(torch.tensor([0.,1.,*range(20)],dtype=torch.float32),[2,20]);self.assertTrue(torch.allclose(torch.stack([p[:2].sum(),p[2:].sum()]),torch.ones(2)))
        logits=torch.tensor([0.,1.,*range(20)]);owner=torch.tensor([0,0]+[1]*20);target=torch.zeros(22);target[:2]=.5;target[2:]=1/20
        loss=t.ragged_root_ce(logits,target,owner,torch.tensor([2,20]));l0=t.root_ce(logits[:2],target[:2]);l1=t.root_ce(logits[2:],target[2:])
        self.assertAlmostEqual(float(loss),float((l0+l1)/2),places=6)

    def test_train_validation_sources_are_disjoint(self):
        t.assert_disjoint_sources([self.row(seed=1)],[self.row(seed=2,rid="r2")])
        with self.assertRaisesRegex(ValueError,"overlap"):t.assert_disjoint_sources([self.row(seed=1)],[self.row(seed=1,rid="r3")])

    def test_train_loader_never_opens_locked_test_shards(self):
        roots=[{"root_id":"train","source_seed":1},{"root_id":"validation","source_seed":2},{"root_id":"test","source_seed":3}]
        entries=[{"split":s,"root":r,"judge_selected":False} for s,r in zip(("TRAIN","VALIDATION","LOCKED_TEST"),roots)]
        release={"sha256":t.RELEASE,"training_ready":True,"quarantined_roots":[],"binding_sha256":t.BINDING,"selection_sha256":t.SELECTION,"files":[]}
        binding={"sha256":t.BINDING,"plan_sha256":"p","executable_git_sha":"g"};selection={"sha256":t.SELECTION,"plan_sha256":"p","executable_git_sha":"g","pilot":False,"entries":entries};plan={"sha256":"p","vocabulary_sha256":"v"};vocab={"sha256":"v"}
        for s in ("TRAIN","VALIDATION"):release["files"].append({"path":f"shards/L/{s.lower()}.json.gz","sha256":"h"})
        def read(path):
            return {"release.json":release,"binding.json":binding,"selection.json":selection,"plan.json":plan,"vocabulary.json":vocab}.get(Path(path).name,{"replay":{"ok":1},"observation":{},"values":[1.,0.]})
        def identity(root):return root["root_id"]
        with mock.patch.object(t.dataset,"read",side_effect=read),mock.patch.object(t.dataset,"check_seal"),mock.patch.object(t.projection,"validate_vocabulary"),mock.patch.object(t.dataset,"identity_hash",side_effect=identity),mock.patch.object(t.dataset,"file_hash",return_value="h") as fh,mock.patch.object(t.dataset,"job_for",side_effect=lambda e,*a,**kw:{"split":e["split"]}),mock.patch.object(t.dataset,"shard",side_effect=lambda raw,*a,**kw:{"replay":raw,"observation":{},"values":[1.,0.]}):
            result=t.load_train_and_validation(Path(tempfile.gettempdir()))
        self.assertEqual(len(result[0]["TRAIN"]),1);self.assertEqual(len(result[0]["VALIDATION"]),1);self.assertEqual(fh.call_count,2)

    def test_feature_table_covers_representative_fixture_fields(self):
        path=Path(__file__).parents[1]/"docs/experiments/evidence/silver_prior_dataset_v1/representative-fixture.json.gz"
        shard=json.loads(gzip.open(path,"rt").read());table=t.validate_feature_table(shard["observation"])
        self.assertTrue(table);self.assertEqual(set(table.values())-{"MODEL_INPUT","RELATIONSHIP_ONLY","REDUNDANT_BY_CONSTRUCTION"},set())
        self.assertEqual(table["zones.limbo[]"],"MODEL_INPUT")
        self.assertEqual(table["zones.stasisCards[]"],"MODEL_INPUT")
        self.assertEqual(len([k for k in t._numeric_fields(shard["observation"])][-12:]),12)

    def test_pairwise_concordance_is_none_when_all_targets_tie(self):
        self.assertIsNone(t.pairwise_concordance([0.1,0.2,0.3],[4,4,4]))
        summary=t.bootstrap_summary([float("nan"),float("nan")],[1,2],n_boot=20)
        self.assertIsNone(summary["mean"])
        self.assertIsNone(summary["ci95"])

    def test_cache_content_digest_detects_tensor_mutation(self):
        cached={"metadata":{"schema":"v1"},"prepared":{"labels":torch.tensor([1.,2.])},"normalization":{"mean":torch.tensor([0.])}}
        before=t.cache_content_sha256(cached);cached["prepared"]["labels"][0]=9.
        self.assertNotEqual(before,t.cache_content_sha256(cached))

    def test_source_cluster_bootstrap_matches_root_weighted_point_estimand(self):
        summary=t.bootstrap_summary([0.,1.,1.,1.],[10,20,20,20],n_boot=2000)
        self.assertEqual(summary["mean"],.75)
        self.assertLess(summary["ci95"][0],.75)
        self.assertGreater(summary["ci95"][1],.75)

    def test_validation_j_loader_authenticates_manifests_and_never_hashes_locked_j(self):
        entries=[];files=[]
        for i in range(64):
            root={"root_id":f"v{i}","source_seed":i}
            entries.append({"split":"VALIDATION","judge_selected":True,"root":root})
            files.append({"path":f"shards/J/v{i}.json.gz","sha256":"h"})
        entries.append({"split":"LOCKED_TEST","judge_selected":True,"root":{"root_id":"locked","source_seed":999}})
        release={"sha256":t.RELEASE,"training_ready":True,"binding_sha256":t.BINDING,"selection_sha256":t.SELECTION,"quarantined_roots":[],"files":files}
        binding={"sha256":t.BINDING,"plan_sha256":"p","executable_git_sha":"g"}
        selection={"sha256":t.SELECTION,"plan_sha256":"p","executable_git_sha":"g","pilot":False,"entries":entries}
        plan={"sha256":"p","vocabulary_sha256":"v"};vocab={"sha256":"v"}
        def read(path):
            return {"release.json":release,"binding.json":binding,"selection.json":selection,"plan.json":plan,"vocabulary.json":vocab}.get(Path(path).name,{"replay":{"ok":1},"observation":{},"values":[1.,0.]})
        with mock.patch.object(t.dataset,"read",side_effect=read),mock.patch.object(t.dataset,"check_seal"),mock.patch.object(t.projection,"validate_vocabulary"),mock.patch.object(t.dataset,"identity_hash",side_effect=lambda root:root["root_id"]),mock.patch.object(t.dataset,"file_hash",return_value="h") as fh,mock.patch.object(t.dataset,"job_for",side_effect=lambda e,*a,**kw:{"split":e["split"]}),mock.patch.object(t.dataset,"shard",side_effect=lambda raw,*a,**kw:{"replay":raw,"observation":{},"values":[1.,0.]}):
            loaded=t.load_validation_j(Path(tempfile.gettempdir()),None,None,None)
            self.assertEqual(len(loaded),64)
            self.assertEqual(fh.call_count,64)
            self.assertTrue(all("locked" not in str(call.args[0]) for call in fh.call_args_list))
            selection["sha256"]="tampered"
            fh.reset_mock()
            with self.assertRaisesRegex(ValueError,"frozen binding/selection mismatch"):
                t.load_validation_j(Path(tempfile.gettempdir()),None,None,None)
            fh.assert_not_called()

    def test_batched_predictions_match_single_root_predictions(self):
        m=self.model();rows=[self.row(seed=1),self.row(seed=2,rid="r2")]
        batch=m(t.collate_rows(rows));single=torch.cat([m(t.collate_rows([r])) for r in rows])
        self.assertTrue(torch.allclose(batch,single,atol=2e-6,rtol=2e-6))

    def test_cached_ragged_gather_matches_fresh_collation(self):
        rows=[self.row(seed=i,rid=str(i)) for i in range(3)];rows[2][0]["cards"][0]["cost"]=2
        full=t.collate_rows(rows);selected=t.select_prepared(full,[2,0]);fresh=t.collate_rows([rows[0],rows[2]])
        m=self.model();self.assertTrue(torch.allclose(m(selected),m(fresh),atol=2e-6,rtol=2e-6))

    def test_model_stays_within_compact_parameter_budget(self):
        self.assertLessEqual(sum(p.numel() for p in self.model().parameters()),250_000)

    def test_tiny_synthetic_batch_overfits(self):
        torch.set_num_threads(1);m=self.model();rows=[self.row(values=[100.,0.],seed=i,rid=str(i)) for i in range(8)];x=t.collate_rows(rows);target,owner,lens=t.ragged_targets(x["root_values"],.05);opt=torch.optim.AdamW(m.parameters(),lr=.02,weight_decay=0)
        for _ in range(300):
            opt.zero_grad();loss=t.ragged_root_ce(m(x),target,owner,lens);loss.backward();opt.step()
        self.assertLess(float(t.ragged_root_ce(m(x),target,owner,lens)),.03)

    def test_no_locked_test_loader_or_generic_split_loader(self):
        self.assertFalse(any("locked_test" in name.lower() or "load_test" in name.lower() for name in dir(t)))


if __name__ == "__main__": unittest.main()
