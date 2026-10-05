import json,subprocess,tempfile,unittest
from pathlib import Path
from claude_code_efficiency.completion_guard import evaluate
class CompletionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.repo=self.root/'repo';self.repo.mkdir()
  self.git('init','-q');self.git('config','user.name','Test');self.git('config','user.email','test@invalid');(self.repo/'code').write_text('base');self.git('add','.');self.git('commit','-qm','base');self.base=self.git('rev-parse','HEAD').strip();self.env={'EFFICIENCY_REQUIRE_COMMIT':'1','EFFICIENCY_BASE_COMMIT':self.base,'EFFICIENCY_STATE':str(self.root/'state')};self.event={'session_id':'test','cwd':str(self.repo),'stop_hook_active':False}
 def tearDown(self):self.tmp.cleanup()
 def git(self,*args):return subprocess.check_output(['git','-C',str(self.repo),*args],text=True,stderr=subprocess.DEVNULL)
 def test_opt_in_only(self):self.assertEqual(evaluate(self.event,{}),{})
 def test_missing_commit_read_only_and_bounded(self):
  self.assertEqual(evaluate(self.event,self.env)['decision'],'block');self.assertEqual(self.git('rev-parse','HEAD').strip(),self.base)
  self.assertEqual(evaluate({**self.event,'stop_hook_active':True},self.env)['decision'],'block');self.assertEqual(evaluate(self.event,self.env),{})
 def test_complete_commit_and_clean_tree_allows(self):
  (self.repo/'code').write_text('finished');self.git('add','.');self.git('commit','-qm','completed');self.assertEqual(evaluate(self.event,self.env),{})
 def test_committed_but_dirty_blocks_without_deleting(self):
  (self.repo/'code').write_text('finished');self.git('add','.');self.git('commit','-qm','completed');(self.repo/'scratch').write_text('review');self.assertEqual(evaluate(self.event,self.env)['decision'],'block');self.assertTrue((self.repo/'scratch').exists())
 def test_empty_commit_not_implementation(self):
  self.git('commit','--allow-empty','-qm','empty');self.assertEqual(evaluate(self.event,self.env)['decision'],'block')
 def test_missing_base_refuses_assumption(self):
  with self.assertRaises(ValueError):evaluate(self.event,{**self.env,'EFFICIENCY_BASE_COMMIT':''})
if __name__=='__main__':unittest.main()
