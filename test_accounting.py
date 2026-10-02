import json
from pathlib import Path
import tempfile
import unittest
import accounting

TABLE=json.loads(Path(__file__).with_name('pricing.json').read_text())
class Tests(unittest.TestCase):
    def usage(self):return {'input_tokens':1000,'cache_read_input_tokens':10000,'cache_creation_input_tokens':3000,'cache_creation':{'ephemeral_5m_input_tokens':1000,'ephemeral_1h_input_tokens':2000},'output_tokens':1000}
    def test_cost_categories_not_double_counted(self):
        t,c=accounting.price(self.usage(),'claude-sonnet-5-5',TABLE)
        self.assertEqual(t['write_5m'],1000);self.assertAlmostEqual(sum(c.values()),.0245)
    def test_missing_ttl_and_invalid_usage_not_guessed(self):
        usage=self.usage();usage.pop('cache_creation')
        with self.assertRaises(ValueError):accounting.categories(usage)
        for invalid in (-1,True,1.5):
            usage=self.usage();usage['output_tokens']=invalid
            with self.assertRaises(ValueError):accounting.categories(usage)
    def test_unknown_model_not_aliased(self):
        with self.assertRaises(KeyError):accounting.price(self.usage(),'unknown',TABLE)
    def test_zero_writes_need_no_ttl(self):
        usage=self.usage();usage.pop('cache_creation');usage['cache_creation_input_tokens']=0
        self.assertEqual(accounting.categories(usage)['write_1h'],0)
    def test_native_index_dedup_and_orphan(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);model='claude-sonnet-5-5'
            (root/'accounting-provenance.json').write_text(json.dumps({'endpoint_host':'api.anthropic.com','synthetic':False}))
            request=root/'a.request.json';request.write_text(json.dumps({'model':model}))
            response=root/'a.response.json';response.write_text(json.dumps({'model':model,'usage':self.usage()}))
            entry={'request_id':'req1','model':model,'request_file':str(request),'response_file':str(response),'query_source':'main'}
            (root/'index.jsonl').write_text(json.dumps(entry)+'\n'+json.dumps(entry)+'\n')
            r=accounting.analyze(root,TABLE);self.assertTrue(r['cost_complete']);self.assertEqual(len(r['requests']),1)
            (root/'b.request.json').write_text('{}');r=accounting.analyze(root,TABLE);self.assertFalse(r['cost_complete']);self.assertEqual(len(r['unpaired_requests']),1)
    def test_billing_modifier_does_not_silently_use_standard_rate(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);model='claude-sonnet-5-5'
            (root/'accounting-provenance.json').write_text(json.dumps({'endpoint_host':'api.anthropic.com','synthetic':False}))
            (root/'a.request.json').write_text(json.dumps({'model':model,'speed':'fast'}))
            (root/'a.response.json').write_text(json.dumps({'model':model,'usage':self.usage()}))
            (root/'index.jsonl').write_text(json.dumps({'request_id':'req1','model':model,'request_file':'a.request.json','response_file':'a.response.json'}))
            r=accounting.analyze(root,TABLE);self.assertFalse(r['cost_complete']);self.assertEqual(r['estimated_known_usd'],0)

if __name__=='__main__':unittest.main()
