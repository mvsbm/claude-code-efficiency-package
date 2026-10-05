import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class ConfigLauncherTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.bin=self.root/'bin'
  subprocess.run([sys.executable,str(ROOT/'scripts'/'install.py'),'--data-home',str(self.root/'data'),'--bin-dir',str(self.bin)],check=True,capture_output=True)
  self.config=self.root/'config.json';self.config.write_text(json.dumps({'regions':{'enabled':False},'profile':'native'}));self.result=self.root/'result.json'
  self.spy=self.root/'spy';self.spy.write_text('#!'+sys.executable+'\nimport json,os,sys\nfrom pathlib import Path\nPath(os.environ["SPY_OUT"]).write_text(json.dumps({"argv":sys.argv,"profile":os.environ.get("EFFICIENCY_PROFILE"),"regions":os.environ.get("EFFICIENCY_REGIONS"),"config":os.environ.get("EFFICIENCY_CONFIG")}))\n');self.spy.chmod(0o755)
  self.env={k:v for k,v in os.environ.items() if not k.startswith(('EFFICIENCY_','CLAUDE_CODE_','SOL_'))};self.env.update(EFFICIENCY_CONFIG=str(self.config),EFFICIENCY_STATE=str(self.root/'state'),EFFICIENCY_CLAUDE_BIN=str(self.spy),SPY_OUT=str(self.result))
 def tearDown(self):self.tmp.cleanup()
 def run_launch(self):return subprocess.run([str(self.bin/'claude-code-efficiency'),'--','test'],env=self.env,capture_output=True,text=True)
 def test_snapshot_config_and_native_prompt(self):
  r=self.run_launch();self.assertEqual(r.returncode,0,r.stderr);value=json.loads(self.result.read_text());self.assertEqual(value['profile'],'native');self.assertEqual(value['regions'],'0');self.assertNotIn('Lightweight problem-solving checkpoints',value['argv'][-3]);self.assertIn('Native Write/Edit are available',value['argv'][-3]);snapshot=Path(value['config']);self.assertNotEqual(snapshot,self.config);self.assertEqual(snapshot.stat().st_mode&0o077,0);self.config.write_text('{}');self.assertFalse(json.loads(snapshot.read_text())['regions']['enabled'])
  installed=self.root/'data'/'claude-code-efficiency-package';self.assertTrue((installed/'claude_code_efficiency'/'operations.py').is_file());self.assertFalse((installed/'simulated_cost.py').exists())
 def test_explicit_environment_override(self):
  self.env['EFFICIENCY_REGIONS']='1';self.assertEqual(self.run_launch().returncode,0);self.assertEqual(json.loads(self.result.read_text())['regions'],'1')
 def test_unknown_setting_rejected_before_claude(self):
  self.config.write_text('{"skip_permissions":true}');self.assertNotEqual(self.run_launch().returncode,0);self.assertFalse(self.result.exists())
 def test_required_commit_needs_explicit_base(self):
  self.config.write_text('{"completion":{"require_commit":true}}');self.assertNotEqual(self.run_launch().returncode,0);self.assertFalse(self.result.exists())
if __name__=='__main__':unittest.main()
