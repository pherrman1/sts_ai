import unittest
from tools.render_ooc_mcts import render


class RenderOocMctsTest(unittest.TestCase):
    def snapshot(self):
        return {
            'observation': {'boundary': 'ooc', 'fixture': 'map_multiple_children',
                            'session': 's', 'sequence': 4,
                            'observationHash': 'h'},
            'response': {'ready': True, 'session': 's', 'sequence': 4,
                         'observationHash': 'h', 'advisor': {'evaluators': [{
                             'id': 'live_ooc_decision_v1', 'status': 'OK',
                             'selectedSemanticKey': 'ooc-action',
                             'tree': {'accepted': True, 'rootId': 0, 'truncated': False,
                                      'nodes': [{'id': 0, 'kind': 'state', 'stateId': '0',
                                                 'visits': 2, 'depth': 0},
                                                {'id': 1, 'kind': 'chance', 'stateId': '0',
                                                 'actionId': 3, 'label': 'ooc-action',
                                                 'visits': 2, 'depth': 0, 'prior': 1.0, 'q': .7}],
                                      'edges': [{'parentId': 0, 'childId': 1,
                                                 'kind': 'action', 'visits': 2}]}}]}}
        }

    def test_standalone_html_contains_capture_and_browser_assets(self):
        html = render(self.snapshot())
        self.assertIn('OOC MCTS search', html)
        self.assertIn('ooc-action', html)
        self.assertIn('map_multiple_children', html)
        self.assertIn('TEST FIXTURE', html)
        self.assertIn('ELK', html)
        self.assertIn('d3', html)

    def test_rejects_stale_or_missing_capture(self):
        snapshot = self.snapshot()
        snapshot['response']['observationHash'] = 'stale'
        with self.assertRaisesRegex(ValueError, 'does not match'):
            render(snapshot)
        snapshot = self.snapshot()
        del snapshot['response']['advisor']['evaluators'][0]['tree']
        with self.assertRaisesRegex(ValueError, 'not captured'):
            render(snapshot)


if __name__ == '__main__':
    unittest.main()
