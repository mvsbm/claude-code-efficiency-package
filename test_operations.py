import io,json,os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch
import operations as sol

class MutationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  self.file=self.root/'code.txt';self.file.write_text('alpha beta gamma\n')
 def tearDown(self):self.temp.cleanup()
 def apply(self,spec):
  with redirect_stdout(io.StringIO()):return sol.apply(spec)
 def test_multi_edit_against_original(self):
  self.apply({'files':[{'path':str(self.file),'edits':[{'oldText':'alpha','newText':'longer first word'},{'oldText':'gamma','newText':'G'}]}]})
  self.assertEqual(self.file.read_text(),'longer first word beta G\n')
 def test_invalid_edits_skip_all_files_and_validation(self):
  witness=self.root/'witness'
  with self.assertRaises(ValueError):self.apply({'files':[{'path':str(self.root/'new'),'content':'not written'},{'path':str(self.file),'edits':[{'oldText':'missing','newText':'X'}]}],'then_run':f'touch {witness}'})
  self.assertFalse(witness.exists());self.assertFalse((self.root/'new').exists())
 def test_overlap_refused(self):
  with self.assertRaises(ValueError):self.apply({'files':[{'path':str(self.file),'edits':[{'oldText':'alpha beta','newText':'X'},{'oldText':'beta','newText':'Y'}]}]})
 def test_duplicate_targets_refused(self):
  with self.assertRaises(ValueError):self.apply({'files':[{'path':str(self.file),'content':'X'},{'path':str(self.file),'content':'Y'}]})
 def test_validation_succeeds(self):
  witness=self.root/'witness'
  self.assertEqual(self.apply({'files':[{'path':str(self.file),'content':'new'}],'then_run':f'cp {self.file} {witness}'}),0)
  self.assertEqual(witness.read_text(),'new')
 def test_validation_failure_keeps_edit_and_stops_sequence(self):
  witness=self.root/'witness'
  self.assertEqual(self.apply({'files':[{'path':str(self.file),'content':'new'}],'then_run':['exit 7',f'touch {witness}']}),7)
  self.assertEqual(self.file.read_text(),'new');self.assertFalse(witness.exists())
 def test_timeout_kills_validation_group(self):
  with self.assertRaises(subprocess.TimeoutExpired):self.apply({'files':[{'path':str(self.file),'content':'new'}],'then_run':{'command':'sleep 10','timeout':0.2}})
  self.assertEqual(self.file.read_text(),'new')
 def test_fused_profile_blocks_direct_python_write(self):
  event={'hook_event_name':'PreToolUse','tool_name':'Bash','tool_input':{'command':'python3 -c "from pathlib import Path; Path(\'code.py\').write_text(\'x\')"'}}
  with patch.dict(os.environ,{'EFFICIENCY_PROFILE':'fused'}):self.assertEqual(sol.hook(event)['hookSpecificOutput']['permissionDecision'],'deny')
 def test_fused_profile_allows_helper(self):
  event={'hook_event_name':'PreToolUse','tool_name':'Bash','tool_input':{'command':f'python3 {sol.__file__} apply --spec -'}}
  with patch.dict(os.environ,{'EFFICIENCY_PROFILE':'fused'}):self.assertEqual(sol.hook(event),{})
 def test_fused_profile_allows_readonly_source_search(self):
  event={'hook_event_name':'PreToolUse','tool_name':'Bash','tool_input':{'command':"rg '.write_text(' code.py"}}
  with patch.dict(os.environ,{'EFFICIENCY_PROFILE':'fused'}):self.assertEqual(sol.hook(event),{})
 def test_fused_profile_preserves_log_capture(self):
  event={'hook_event_name':'PreToolUse','tool_name':'Bash','tool_input':{'command':'PYTHONPATH=. python3 tools/audit.py > audit.log 2>&1; cat audit.log'}}
  with patch.dict(os.environ,{'EFFICIENCY_PROFILE':'fused'}):self.assertEqual(sol.hook(event),{})
 def test_other_profiles_do_not_apply_write_guard(self):
  event={'hook_event_name':'PreToolUse','tool_name':'Bash','tool_input':{'command':"python3 -c \"open('code.py','w').write('x')\""}}
  with patch.dict(os.environ,{'EFFICIENCY_PROFILE':'native'}):self.assertEqual(sol.hook(event),{})
 def test_concurrent_mutations_serialized_through_validation(self):
  a={'files':[{'path':str(self.file),'content':'A'}],'then_run':f'sleep 0.5; test "$(cat {self.file})" = A'}
  b={'files':[{'path':str(self.file),'content':'B'}],'then_run':f'test "$(cat {self.file})" = B'}
  cmd=[sys.executable,sol.__file__,'apply','--spec','-']
  first=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  first.stdin.write(json.dumps(a));first.stdin.close()
  for _ in range(100):
   if self.file.read_text()=='A':break
   time.sleep(0.01)
  second=subprocess.run(cmd,input=json.dumps(b),capture_output=True,text=True,timeout=5)
  first.wait(timeout=5);first.stdout.close();first.stderr.close()
  self.assertEqual(first.returncode,0);self.assertEqual(second.returncode,0);self.assertEqual(self.file.read_text(),'B')
if __name__=='__main__':unittest.main()
