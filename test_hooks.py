import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import hooks

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.file=self.root/'code.py';self.file.write_text('alpha\n')
        self.patch=patch.object(hooks,'STATE',self.root/'state');self.patch.start();self.addCleanup(self.patch.stop)
        self.event={'session_id':'session1','tool_use_id':'read1','cwd':str(self.root),'tool_name':'Read','tool_input':{'file_path':str(self.file)},'hook_event_name':'PreToolUse'}
    def read(self):
        hooks.process(self.event);done=dict(self.event,hook_event_name='PostToolUse');hooks.process(done)
    def test_duplicate_hint_not_denial_or_fake_result(self):
        self.read();hint=hooks.process(dict(self.event,tool_use_id='read2'))
        specific=hint['hookSpecificOutput'];self.assertIn('unchanged',specific['additionalContext'])
        self.assertNotIn('permissionDecision',specific);self.assertNotIn('updatedToolOutput',specific)
    def test_changed_file_invalidates_hint(self):
        self.read();self.file.write_text('beta\n');self.assertEqual(hooks.process(dict(self.event,tool_use_id='read2')), {})
    def test_different_range_not_duplicate(self):
        self.read();event=copy.deepcopy(self.event);event['tool_input']['offset']=2
        self.assertEqual(hooks.process(event),{})
    def test_failed_read_not_recorded(self):
        hooks.process(self.event);hooks.process(dict(self.event,hook_event_name='PostToolUseFailure'))
        self.assertEqual(hooks.process(dict(self.event,tool_use_id='read2')), {})
    def test_session_isolation(self):
        self.read();self.assertEqual(hooks.process(dict(self.event,session_id='other')), {})
    def test_changed_during_read_not_recorded(self):
        hooks.process(self.event);self.file.write_text('changed');hooks.process(dict(self.event,hook_event_name='PostToolUse'))
        self.assertEqual(hooks.process(dict(self.event,tool_use_id='read2')), {})
    def test_symlink_not_fingerprinted(self):
        link=self.root/'link.py';link.symlink_to(self.file);self.assertIsNone(hooks.fingerprint(link))
    def test_prompt_hint_requires_current_revision(self):
        self.read();e={'session_id':'session1','hook_event_name':'UserPromptSubmit'}
        self.assertIn('additionalContext',hooks.process(e)['hookSpecificOutput'])
        self.file.write_text('changed');self.assertEqual(hooks.process(e),{})
    def test_large_file_no_hash_hint(self):
        self.file.write_text('x'*(1024*1024+1));self.assertIsNone(hooks.fingerprint(self.file))

if __name__=='__main__':unittest.main()
