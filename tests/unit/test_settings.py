import copy,json,tempfile,unittest
from pathlib import Path
from claude_code_efficiency import settings

class SettingsTests(unittest.TestCase):
 def load(self,value):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'config.json';p.write_text(json.dumps(value));return settings.load(p)
 def test_partial_merge(self):
  config=self.load({'checks':{'max_bytes':1024},'regions':{'enabled':False}})
  self.assertEqual(config['checks']['max_bytes'],1024);self.assertFalse(config['regions']['enabled']);self.assertEqual(config['checks']['max_diagnostics'],40)
 def test_unknown_or_retired_keys_rejected(self):
  for value in [{'ignore_permissions':True},{'documents':{}},{'workflow':{'structured':True}},{'benchmark':{}},{'objective':{}},{'checks':{'hide_exit_code':True}}]:
   with self.subTest(value=value),self.assertRaises(ValueError):self.load(value)
 def test_types_and_bounds(self):
  for value in [{'version':True},{'version':2},{'regions':{'enabled':1}},{'checks':{'max_bytes':0}},{'completion':{'max_reminders':4}},{'profile':'bypass'},{'checks':None}]:
   with self.subTest(value=value),self.assertRaises(ValueError):self.load(value)
 def test_identity_stable(self):
  a=self.load({});b=copy.deepcopy(a);self.assertEqual(settings.identity(a),settings.identity(b));b['regions']['enabled']=False;self.assertNotEqual(settings.identity(a),settings.identity(b))
 def test_defaults_not_mutated(self):
  a=self.load({});a['checks']['max_bytes']=512;self.assertEqual(self.load({})['checks']['max_bytes'],7680)
 def test_exports(self):
  result=settings.exports(self.load({'regions':{'enabled':False},'completion':{'require_commit':True}}))
  self.assertEqual(result['EFFICIENCY_REGIONS'],'0');self.assertEqual(result['EFFICIENCY_REQUIRE_COMMIT'],'1');self.assertNotIn('EFFICIENCY_STRUCTURED_WORKFLOW',result)
if __name__=='__main__':unittest.main()
