import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from claude_code_efficiency import operations
from claude_code_efficiency.patch_input import parse_patch

class PatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.env={**os.environ,'EFFICIENCY_STATE':str(self.root/'state')}
        self.file=self.root/'source.go';self.file.write_text('package test\n\nvar x = "old"\n')
    def tearDown(self):self.tmp.cleanup()
    def cli(self,*args,data=None):
        return subprocess.run([sys.executable,'-m','claude_code_efficiency.operations',*args],input=data,text=True,capture_output=True,env=self.env)
    def diff(self):return f'*** Begin Patch\n*** Update File: {self.file}\n@@\n package test\n \n-var x = "old"\n+var x = "new"\n*** End Patch\n'
    def test_plain_code_no_json_escaping_and_validation(self):
        r=self.cli('apply-patch','--patch','-','--then-run',f'grep -q new {self.file}','--timeout','5',data=self.diff())
        self.assertEqual(r.returncode,0,r.stderr);self.assertIn('validation]',r.stdout)
        self.assertEqual(self.file.read_text(),'package test\n\nvar x = "new"\n')
        self.assertEqual(len(list((self.root/'state/checks').glob('*/manifest.json'))),1)
    def test_invalid_patch_archived_no_mutation(self):
        r=self.cli('apply-patch','--patch','-',data=self.diff()+'trailing\n')
        self.assertNotEqual(r.returncode,0);self.assertIn('[input_archive]',r.stdout)
        self.assertIn('"old"',self.file.read_text())
    def test_exact_anchor_failure_skips_validation(self):
        r=self.cli('apply-patch','--patch','-','--then-run',f'touch {self.root}/witness',data=self.diff().replace('-var x = "old"','-var x = "absent"'))
        self.assertNotEqual(r.returncode,0);self.assertFalse((self.root/'witness').exists())
    def test_add_existing_refused(self):
        r=self.cli('apply-patch','--patch','-',data=f'*** Begin Patch\n*** Add File: {self.file}\n+replaced\n*** End Patch\n')
        self.assertNotEqual(r.returncode,0);self.assertIn('"old"',self.file.read_text())
    def test_add_new_unicode(self):
        dest=self.root/'new.go'
        r=self.cli('apply-patch','--patch','-',data=f'*** Begin Patch\n*** Add File: {dest}\n+var s = "é\\n"\n*** End Patch\n')
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(dest.read_text(),'var s = "é\\n"\n')
    def test_multiple_original_hunks(self):
        self.file.write_text('first\nmiddle\nlast\n')
        r=self.cli('apply-patch','--patch','-',data=f'*** Begin Patch\n*** Update File: {self.file}\n@@\n-first\n+FIRST\n@@\n-last\n+LAST\n*** End Patch\n')
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(self.file.read_text(),'FIRST\nmiddle\nLAST\n')
    def test_overlapping_context_refused(self):
        self.file.write_text('a\nb\nc\n')
        r=self.cli('apply-patch','--patch','-',data=f'*** Begin Patch\n*** Update File: {self.file}\n@@\n a\n-b\n+B\n@@\n-b\n+BB\n c\n*** End Patch\n')
        self.assertNotEqual(r.returncode,0);self.assertEqual(self.file.read_text(),'a\nb\nc\n')
    def test_no_line_numbers_or_fuzzy_matching(self):
        with self.assertRaises(ValueError):parse_patch(self.diff().replace('@@\n','@@ -1,3 +1,3 @@\n'))
    def test_empty_insertion_and_delete_markers_refused(self):
        with self.assertRaises(ValueError):parse_patch('*** Begin Patch\n*** Delete File: x\n*** End Patch\n')
        with self.assertRaises(ValueError):parse_patch('*** Begin Patch\n*** Update File: x\n@@\n+text\n*** End Patch\n')
    def test_json_repair_never_applies_source_automatically(self):
        raw=json.dumps({'files':[{'path':str(self.file),'content':'fixed\n'}]})+'EXTRA'
        r=self.cli('apply','--spec','-',data=raw);ident=re.search(r'input_[a-f0-9]{64}',r.stdout).group()
        fix=self.cli('repair-input',ident,'--old','EXTRA','--new','')
        self.assertEqual(fix.returncode,0,fix.stderr);self.assertIn('"old"',self.file.read_text())
        repaired=re.search(r'input_[a-f0-9]{64}',fix.stdout).group()
        apply=self.cli('apply','--spec',repaired);self.assertEqual(apply.returncode,0,apply.stderr)
        self.assertEqual(self.file.read_text(),'fixed\n')
    def test_corrupt_archive_and_format_mismatch_refused(self):
        r=self.cli('apply','--spec','-',data='{}');ident=re.search(r'input_[a-f0-9]{64}',r.stdout).group()
        self.assertNotEqual(self.cli('apply-patch','--patch',ident).returncode,0)
        (self.root/'state/inputs'/(ident+'.raw')).write_text('broken')
        self.assertNotEqual(self.cli('apply','--spec',ident).returncode,0)
    def test_failed_validator_keeps_edits(self):
        r=self.cli('apply-patch','--patch','-','--then-run','exit 7',data=self.diff())
        self.assertEqual(r.returncode,7);self.assertIn('"new"',self.file.read_text())
    def test_go_and_other_source_redirect_guard(self):
        for suffix in ['go','rs','c','cpp','h','tsx','toml']:
            event={'hook_event_name':'PreToolUse','tool_name':'Bash','tool_input':{'command':f'cat > /app/source.{suffix} <<EOF\nx\nEOF'}}
            with patch.dict(os.environ,{'EFFICIENCY_PROFILE':'fused'}):self.assertEqual(operations.hook(event)['hookSpecificOutput']['permissionDecision'],'deny')
    def test_patch_command_is_allowed_by_workflow_guard(self):
        event={'hook_event_name':'PreToolUse','tool_name':'Bash','tool_input':{'command':'python3 -m claude_code_efficiency.operations apply-patch --patch - --then-run "go test"'}}
        with patch.dict(os.environ,{'EFFICIENCY_PROFILE':'fused'}):self.assertEqual(operations.hook(event),{})

if __name__=='__main__':unittest.main()
