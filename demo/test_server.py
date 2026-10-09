"""HTTP-level tests for the bounded, repository-local closing demo."""
from __future__ import annotations

from http.server import ThreadingHTTPServer
import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from demo.server import DemoHandler, MAX_BODY_BYTES


class DemoHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), DemoHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def get(self, path: str) -> tuple[int, bytes]:
        try:
            with urlopen(self.base + path, timeout=20) as response:
                return response.status, response.read()
        except HTTPError as error:
            body = error.read()
            error.close()
            return error.code, body

    def post(self, payload: object, *, raw: bytes | None = None) -> tuple[int, dict]:
        body = raw if raw is not None else json.dumps(payload).encode('utf-8')
        request = Request(
            self.base + '/api/evaluate', data=body, method='POST',
            headers={'Content-Type': 'application/json'},
        )
        try:
            with urlopen(request, timeout=30) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            body = error.read()
            error.close()
            return error.code, json.loads(body)

    def test_standalone_page_embeds_recorded_fixture_data(self) -> None:
        status, body = self.get('/')
        self.assertEqual(status, 200)
        page = body.decode('utf-8')
        self.assertNotIn('__OFFLINE_EVIDENCE__', page)
        self.assertIn('orchlang-demo-offline-evidence', page)
        self.assertIn('STATIC EVIDENCE', page)

    def test_fixture_catalog_is_fixed_and_horizon_is_bounded(self) -> None:
        status, body = self.get('/api/fixtures')
        self.assertEqual(status, 200)
        catalog = json.loads(body)
        self.assertEqual(len(catalog['fixtures']), 7)
        self.assertEqual(catalog['limits']['horizon'], 8)

        status, error = self.post({'fixture': 'aggregate-order', 'options': {'horizon': 9}})
        self.assertEqual(status, 400)
        self.assertIn('horizon', error['error'])

        status, error = self.post({'fixture': '../../etc/passwd', 'options': {}})
        self.assertEqual(status, 400)
        self.assertIn('unknown fixed fixture', error['error'])

    def test_request_body_limit_is_enforced_before_analysis(self) -> None:
        status, error = self.post({}, raw=b' ' * (MAX_BODY_BYTES + 1))
        self.assertEqual(status, 413)
        self.assertIn('16 KiB', error['error'])

    def test_compiler_rejection_includes_offline_billing_witness(self) -> None:
        status, result = self.post({'fixture': 'budget-leak', 'options': {'xLength': 37, 'yLength': 61}})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['execution'], 'live localhost run')
        self.assertEqual(result['checks'][0]['status'], 'rejected')
        self.assertIn('E236', result['checks'][0]['diagnostic_codes'])
        false_run, true_run = [row['workflow'] for row in result['traces']]
        self.assertNotEqual(false_run['input_tokens'], true_run['input_tokens'])
        self.assertEqual(result['traces'][0]['bypass'], '--audit-unsafe · offline witness only')

    def test_balanced_dependent_chain_has_source_and_companion_evidence(self) -> None:
        status, result = self.post({'fixture': 'balanced-chain', 'options': {'sourceLength': 8}})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['checks'][0]['status'], 'accepted')
        self.assertTrue(result['cost_replay']['verified'])
        self.assertEqual(len(result['request_plan']), 4)
        self.assertEqual(len(result['traces']), 2)
        self.assertEqual(result['companion']['bisimulation']['status'], 'proved_equal')
        self.assertEqual(result['companion']['bisimulation']['replay']['status'], 'verified')
        self.assertEqual(result['companion']['trace_equivalence']['status'], 'proved_equal')
        self.assertEqual(result['companion']['trace_equivalence']['replay']['status'], 'verified')

    def test_productive_cycle_graph_certificate_is_replayed(self) -> None:
        status, result = self.post({'fixture': 'productive-cycle', 'options': {'query': 'hello', 'horizon': 8}})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['graph_check']['status'], 'accepted')
        self.assertEqual(result['graph_replay']['status'], 'verified')
        self.assertTrue(all(len(trace['calls']) <= 8 for trace in result['traces']))

    def test_channel_reports_replay_and_preserve_observer_difference(self) -> None:
        status, result = self.post({'fixture': 'aggregate-order', 'options': {'horizon': 2}})
        self.assertEqual(status, 200, result)
        analysis = result['analysis']
        aggregate = analysis['observers']['aggregate']['metrics']['pairwise'][0]
        ordered = analysis['observers']['trace']['metrics']['pairwise'][0]
        self.assertEqual(aggregate['total_variation'], '0')
        self.assertEqual(ordered['total_variation'], '1')
        self.assertEqual(analysis['observers']['trace']['replay']['status'], 'verified')
        self.assertEqual(analysis['bisimulation']['status'], 'inconclusive')
        self.assertEqual(analysis['bisimulation']['replay']['status'], 'verified')
        self.assertEqual(analysis['trace_equivalence']['status'], 'unequal')
        self.assertEqual(analysis['trace_equivalence']['replay']['status'], 'verified')

    def test_exact_trace_equivalence_resolves_a_bisimulation_gap(self) -> None:
        status, result = self.post({'fixture': 'bisim-gap', 'options': {'horizon': 2}})
        self.assertEqual(status, 200, result)
        analysis = result['analysis']
        self.assertEqual(analysis['observers']['trace']['metrics']['pairwise'][0]['total_variation'], '0')
        self.assertEqual(analysis['bisimulation']['status'], 'inconclusive')
        self.assertEqual(analysis['trace_equivalence']['status'], 'proved_equal')
        self.assertEqual(analysis['trace_equivalence']['replay']['status'], 'verified')


if __name__ == '__main__':
    unittest.main()
