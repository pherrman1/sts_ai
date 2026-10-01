"""Synthetic A3 evaluator tests: no real corpus or model access."""
import unittest
import numpy as np
from tools.vwin_refresh_evaluation import (predictive_metrics, evaluate_predictions,
    cluster_mean, clustered_delta, resource_probes, sibling_ranking, offline_verdict)


class EvaluationTests(unittest.TestCase):
    def test_equal_mass_and_auc_ties(self):
        y = np.arange(23) % 2
        p = np.full(23, .5)
        result = predictive_metrics(y, p)
        self.assertEqual([x['n'] for x in result['reliability']], [3]*3+[2]*7)
        self.assertEqual(result['roc_auc'], .5)
        self.assertAlmostEqual(result['nll'], np.log(2))
        expected = sum(len(a)*abs(y[a].mean()-.5) for a in np.array_split(np.arange(23),10))/23
        self.assertAlmostEqual(result['ece'], expected)
        self.assertIsNone(predictive_metrics([0, 0], [.1, .2])['roc_auc'])

    def test_cluster_resamples_whole_sources_row_weighted(self):
        result = cluster_mean([0, 0, 0, 1], [7, 7, 7, 8], reps=2000)
        self.assertEqual(result['mean'], .25)
        self.assertEqual(result['source_seeds'], 2)
        self.assertEqual(result['ci95'], [0., 1.])
        self.assertIsNone(cluster_mean([0, 1], [7, 7])['ci95'])
        same = clustered_delta([0, 1], [.2, .8], [.2, .8], [1, 2])
        self.assertEqual(same['nll']['ci95'], [0., 0.])

    def test_bootstrap_matches_explicit_source_multiplicity(self):
        y = np.array([0,1,0,1,0,1,1])
        b = np.array([.2,.8,.4,.5,.3,.5,.6])
        c = np.array([.2,.6,.3,.7,.4,.7,.8])
        sources = np.array([3,3,3,8,8,9,9])
        reps, seed = 40, 11
        result = clustered_delta(y,b,c,sources,reps,seed)
        rng = np.random.default_rng(seed)
        expected = {name: [] for name in ('nll','brier','roc_auc','ece')}
        unique = np.unique(sources)
        for _ in range(reps):
            chosen = rng.integers(0,len(unique),len(unique))
            # Stable original order among repeated rows matches weighted bins.
            weights = np.array([np.sum(unique[chosen] == src) for src in sources])
            ids = np.repeat(np.arange(len(y)), weights)
            bm, cm = predictive_metrics(y[ids],b[ids]), predictive_metrics(y[ids],c[ids])
            for key in expected:
                if bm[key] is not None and cm[key] is not None:
                    expected[key].append(cm[key]-bm[key])
        for key, values in expected.items():
            np.testing.assert_allclose(result[key]['ci95'],np.quantile(values,[.025,.975]),atol=1e-14)

    def test_explicit_breakdowns(self):
        result = evaluate_predictions([0,1], [.1,.9], [dict(act=1,branchId='source'),dict(act=2,branchId='b')])
        self.assertIn('act:2', result['breakdowns'])
        self.assertEqual(result['preboss_status'], 'not_identifiable_for_all_rows')

    def test_resource_interventions(self):
        names = ['curHp','maxHp','gold','potionCount','pot0','pot1','unrelated']
        X = np.array([[5,10,10,2,1,1,37.], [6,10,40,1,0,1,37.]])
        original = X.copy()
        observed = []
        def predictor(a):
            observed.append(a.copy())
            self.assertTrue(np.all(a[:,6] == 37))
            self.assertTrue(np.all(a[:,3] == a[:,4]+a[:,5]))
            self.assertTrue(np.all(a[:,2] >= 0))
            return .01*a[:,0]+.001*a[:,1]+.001*a[:,2]+.02*a[:,3]
        meta = [dict(sourceSeed=1,act=1), dict(sourceSeed=2,act=1)]
        result = resource_probes(predictor,X,names,meta,reps=10)
        np.testing.assert_array_equal(X, original)
        self.assertEqual(result['hp_sweep_monotone_share'], 1.)
        self.assertAlmostEqual(result['feed_delta']['mean'], .011)
        self.assertAlmostEqual(result['max_hp_only_delta']['mean'], .001)
        self.assertAlmostEqual(result['by_act']['1']['held_potion_delta']['mean'], .02)
        self.assertFalse(result['resource_gate'])  # Absent acts fail closed.
        self.assertEqual(result['by_act']['2']['hp_slope']['status'], 'insufficient_independent_seeds')
        self.assertTrue(any(np.any(a[:,4] == 0) for a in observed))
        self.assertTrue(any(np.any(a[:,0] == 1) for a in observed))

    def test_win_raw_boss_hp(self):
        names = ['curHp','maxHp','gold','potionCount','pot0']
        X = np.array([[2,10,0,1,1.]])
        observed = []
        def predictor(a):
            observed.append(a.copy())
            return .02*a[:,0]+.01*a[:,3]
        result = resource_probes(predictor,X,names,[dict(sourceSeed=1,act=1,actBoss=1,postAfterBattleHp=8)],kind='WIN_RAW',reps=10)
        self.assertEqual(observed[0][0,0], 8)
        self.assertEqual(result['act_boss_hp_corrections'], 1)
        self.assertEqual(X[0,0], 2)
        with self.assertRaises(ValueError):
            resource_probes(predictor,X,names,[dict(sourceSeed=1,act=1)],kind='WIN_RAW')

    def test_invalid_potion_state(self):
        with self.assertRaisesRegex(ValueError, 'potion'):
            resource_probes(lambda x: np.zeros(len(x)),[[2,3,0,2,1]],
                            ['curHp','maxHp','gold','potionCount','pot0'],[dict(sourceSeed=1,act=1)])

    def test_sibling_explicit_join_first_map_and_tie(self):
        rows = [dict(sourceSeed=1,branchId='a',rowIdx=9),
                dict(sourceSeed=1,branchId='b',rowIdx=4),
                dict(sourceSeed=1,branchId='a',rowIdx=3)]
        branches = [dict(sourceSeed=1,decisionIdx=8,type='rest',branchId=k,won=w,valid=1)
                    for k,w in [('a',1),('b',0),('missing',0)]]
        result = sibling_ranking(rows,[.9,.5,.5],branches,reps=10)
        self.assertEqual(result['pooled']['mean'], .5)
        self.assertEqual(result['pooled']['n'], 1)
        self.assertEqual(result['branches_without_map'], 1)
        self.assertEqual(result['branches_without_map_by_type'], {'rest':1})
        self.assertEqual(result['pooled']['source_seeds'], 1)

    def test_map_skips_common_predecision_score(self):
        rows = [dict(sourceSeed=1, branchId=k, rowIdx=i)
                for k in ('winner', 'loser') for i in (0, 1, 2)]
        branches = [dict(sourceSeed=1, decisionIdx=8, type='MAP',
                         branchId=k, won=w, valid=1)
                    for k, w in [('winner', 1), ('loser', 0)]]
        result = sibling_ranking(rows, [.5, .9, .1, .5, .2, .8], branches)
        self.assertEqual(result['pooled']['mean'], 1.)
        self.assertEqual(result['pooled']['n'], 1)
        # The old minimum-row rule scored the identical row-0 values.
        old = sibling_ranking(rows, [.5, .9, .1, .5, .2, .8],
                              [dict(b, type='REST') for b in branches])
        self.assertEqual(old['pooled']['mean'], .5)

    def test_map_without_postoption_map_is_missing(self):
        rows = [dict(sourceSeed=1, branchId='a', rowIdx=0),
                dict(sourceSeed=1, branchId='b', rowIdx=1)]
        branches = [dict(sourceSeed=1, decisionIdx=8, type='MAP',
                         branchId=k, won=w, valid=1)
                    for k, w in [('a', 1), ('b', 0)]]
        result = sibling_ranking(rows, [.9, .2], branches)
        self.assertEqual(result['branches_without_map'], 1)
        self.assertEqual(result['branches_without_map_by_type'], {'MAP': 1})
        self.assertEqual(result['pooled']['n'], 0)

    def test_nonmap_uses_row_zero(self):
        for typ in ('CARD_REWARD', 'REST'):
            with self.subTest(typ=typ):
                rows = [dict(sourceSeed=1, branchId=k, rowIdx=i)
                        for k in ('a', 'b') for i in (0, 1)]
                branches = [dict(sourceSeed=1, decisionIdx=8, type=typ,
                                 branchId=k, won=w, valid=1)
                            for k, w in [('a', 1), ('b', 0)]]
                result = sibling_ranking(rows, [.9, .1, .2, .8], branches)
                self.assertEqual(result['pooled']['mean'], 1.)

    def test_sibling_duplicate_and_malformed_protection(self):
        row = dict(sourceSeed=1, branchId='a', rowIdx=0)
        branch = dict(sourceSeed=1, branchId='a', decisionIdx=1,
                      type='MAP', won=1, valid=1)
        with self.assertRaisesRegex(ValueError, 'duplicate MAP'):
            sibling_ranking([row, row], [.5, .5], [branch])
        with self.assertRaisesRegex(ValueError, 'duplicate branch'):
            sibling_ranking([row], [.5], [branch, branch])
        for ordinal in (-1, 'bad', 1.5):
            with self.subTest(ordinal=ordinal), self.assertRaises(ValueError):
                sibling_ranking([dict(row, rowIdx=ordinal)], [.5], [branch])
        with self.assertRaisesRegex(ValueError, 'invalid branch outcome'):
            sibling_ranking([row], [.5], [dict(branch, won=2)])

    def test_offline_ties_and_separate_raw_gate(self):
        arms = {name:dict(nll=nll,nll_delta_ci95=[-.03,-.01],map_resource_gate=True,win_raw_resource_gate=False)
                for name,nll in [('X1',.4),('X2',.402),('M1',.5)]}
        result = offline_verdict(arms)
        self.assertEqual(result['verdict'], 'VWIN_OFFLINE_TIE_NEEDS_SPEED')
        self.assertEqual(result['provisional_best'], 'X1')
        self.assertFalse(result['terminal_pricing_ready'])
        arms['X2']['map_resource_gate'] = False
        self.assertEqual(offline_verdict(arms)['verdict'], 'VWIN_OFFLINE_XGB')
        for arm in arms.values():
            arm['nll_delta_ci95'] = [-.02,0]
        self.assertEqual(offline_verdict(arms)['verdict'], 'VWIN_OFFLINE_NO_CANDIDATE')


if __name__ == '__main__':
    unittest.main()
