import json
from pathlib import Path
import tempfile
import unittest

from claude_code_efficiency import accounting


class UsageTests(unittest.TestCase):
    def usage(self):
        return {
            'input_tokens': 1000,
            'cache_read_input_tokens': 10000,
            'cache_creation_input_tokens': 3000,
            'cache_creation': {
                'ephemeral_5m_input_tokens': 1000,
                'ephemeral_1h_input_tokens': 2000,
            },
            'output_tokens': 1000,
        }

    def test_provider_counters_and_cache_ttl_are_preserved(self):
        counters, ttl = accounting.usage_counts(self.usage())
        self.assertEqual(counters['input_tokens'], 1000)
        self.assertEqual(counters['cache_read_input_tokens'], 10000)
        self.assertEqual(counters['cache_creation_input_tokens'], 3000)
        self.assertEqual(counters['output_tokens'], 1000)
        self.assertEqual(sum(ttl.values()), counters['cache_creation_input_tokens'])

    def test_missing_ttl_breakdown_keeps_total_and_marks_split_unknown(self):
        usage = self.usage()
        usage.pop('cache_creation')
        counters, ttl = accounting.usage_counts(usage)
        self.assertEqual(counters['cache_creation_input_tokens'], 3000)
        self.assertIsNone(ttl)

    def test_invalid_usage_is_not_guessed(self):
        for invalid in (-1, True, 1.5):
            usage = self.usage()
            usage['output_tokens'] = invalid
            with self.assertRaises(ValueError):
                accounting.usage_counts(usage)

    def test_required_counter_cannot_be_silently_zeroed(self):
        usage = self.usage()
        del usage['cache_read_input_tokens']
        with self.assertRaises(KeyError):
            accounting.usage_counts(usage)

    def test_zero_cache_creation_does_not_require_ttl_breakdown(self):
        usage = self.usage()
        usage.pop('cache_creation')
        usage['cache_creation_input_tokens'] = 0
        self.assertEqual(accounting.usage_counts(usage)[1], {
            'ephemeral_5m_input_tokens': 0,
            'ephemeral_1h_input_tokens': 0,
        })

    def test_native_index_deduplicates_and_flags_orphan_requests(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = 'claude-sonnet-5-5'
            (root / 'accounting-provenance.json').write_text(json.dumps({
                'endpoint_host': 'api.anthropic.com', 'synthetic': False,
            }))
            request = root / 'a.request.json'
            request.write_text(json.dumps({'model': model}))
            response = root / 'a.response.json'
            response.write_text(json.dumps({'model': model, 'usage': self.usage()}))
            entry = {
                'request_id': 'req1', 'model': model,
                'request_file': str(request), 'response_file': str(response),
                'query_source': 'main',
            }
            (root / 'index.jsonl').write_text(json.dumps(entry) + '\n' + json.dumps(entry) + '\n')
            report = accounting.analyze(root)
            self.assertTrue(report['archive_consistent'])
            self.assertEqual(len(report['requests']), 1)
            self.assertEqual(report['captured_token_usage']['output_tokens'], 1000)
            self.assertNotIn('cost', json.dumps(report).lower())
            (root / 'b.request.json').write_text('{}')
            report = accounting.analyze(root)
            self.assertFalse(report['archive_consistent'])
            self.assertEqual(len(report['unpaired_requests']), 1)

    def test_incomplete_archive_does_not_report_zero_usage(self):
        with tempfile.TemporaryDirectory() as temp:
            report = accounting.analyze(temp)
            self.assertFalse(report['archive_consistent'])
            self.assertIsNone(report['captured_token_usage'])


if __name__ == '__main__':
    unittest.main()
