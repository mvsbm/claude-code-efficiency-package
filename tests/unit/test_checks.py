import contextlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from claude_code_efficiency import checks, operations

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.diagnostic={'filename':'example.py','location':{'row':1,'column':2},'code':'F821','message':'undefined name x','end_location':{'row':1,'column':3},'fix':None}
    def test_compact_preserves_locations_messages_codes(self):
        text=checks.compact(json.dumps([self.diagnostic]),'ruff-json',1)
        self.assertIn('FAIL',text);d=json.loads(text.splitlines()[1]);self.assertEqual(d['code'],'F821');self.assertEqual(d['line'],1)
    def test_duplicate_count_explicit(self):
        text=checks.compact(json.dumps([self.diagnostic]*5),'ruff-json',1)
        self.assertIn('diagnostics=5; unique=1',text)
    def test_omission_explicit(self):
        text=checks.compact(json.dumps([dict(self.diagnostic,message=str(i)) for i in range(50)]),'ruff-json',1)
        self.assertIn('omitted=10',text)
    def test_large_diagnostic_not_silently_truncated(self):
        raw=json.dumps([dict(self.diagnostic,message='x'*10000)])
        text=checks.compact(raw,'ruff-json',1)
        self.assertLess(len(text.encode()),8192);self.assertIn('shown=0; omitted=1',text);self.assertIn('FAIL',text)
    def test_unknown_schema_or_inconsistent_status_rejected(self):
        for raw,code in [('{}',1),('[]',1),(json.dumps([self.diagnostic]),0),(json.dumps([dict(self.diagnostic,location={'row':True,'column':1})]),1)]:
            with self.assertRaises((ValueError,KeyError)):checks.compact(raw,'ruff-json',code)
    def test_pyright_messages_warning_counts(self):
        raw={'generalDiagnostics':[{'file':'x.py','range':{'start':{'line':0,'character':1}},'severity':'warning','message':'detail'}],'summary':{'errorCount':0,'warningCount':1,'informationCount':0}}
        text=checks.compact(json.dumps(raw),'pyright-json',0);self.assertIn('warning',text);self.assertIn('"line":1',text)
    def run_command(self,command,format='plain',timeout=5):
        with contextlib.redirect_stdout(io.StringIO()) as out,contextlib.redirect_stderr(io.StringIO()) as err:
            code=checks.execute(command,timeout,format,self.root)
        return code,out.getvalue(),err.getvalue()
    def test_failure_and_stderr_preserved(self):
        code,out,err=self.run_command('printf hello; printf warning >&2; exit 7')
        self.assertEqual(code,7);self.assertIn('hello',out);self.assertIn('warning',err)
    def test_pipefail(self):self.assertEqual(self.run_command('false | cat')[0],1)
    def test_unknown_json_falls_back_to_original(self):
        code,out,err=self.run_command("printf '{\"alien\":true}'; exit 1",'ruff-json')
        self.assertEqual(code,1);self.assertIn('{"alien":true}',out)
    def test_compacted_failure_keeps_edits(self):
        source=self.root/'code.py';jsonfile=self.root/'diagnostics.json';jsonfile.write_text(json.dumps([self.diagnostic]*50))
        with patch.object(operations,'CHECKS',self.root/'archive'),contextlib.redirect_stdout(io.StringIO()) as out:
            result=operations.apply({'files':[{'path':str(source),'content':'changed'}],'then_run':{'command':f'cat {shlex.quote(str(jsonfile))}; exit 1','output_format':'ruff-json'}})
        self.assertEqual(result,1);self.assertEqual(source.read_text(),'changed');self.assertIn('unique=1',out.getvalue())
    def test_timeout_archived_and_process_killed(self):
        with self.assertRaises(subprocess.TimeoutExpired):self.run_command('sleep 30',timeout=.1)
        manifest=json.loads(next(self.root.glob('*/manifest.json')).read_text());self.assertTrue(manifest['interrupted'])
    def test_byte_recall_and_corruption(self):
        self.run_command("printf '\\316\\261xyz'")
        folder=next(self.root.glob('check_*'));r=checks.recall(self.root,folder.name,offset=1,limit=2)
        import base64
        self.assertEqual(base64.b64decode(r['base64']),b'\xb1x')
        (folder/'stdout').write_bytes(b'corrupt')
        with self.assertRaises(ValueError):checks.recall(self.root,folder.name)
    def test_fallback_preserves_unicode_at_chunk_boundary(self):
        file=self.root/'unicode';file.write_text('x'*65535+'αZ')
        stream=io.StringIO();checks.emit(file,stream);self.assertEqual(stream.getvalue(),file.read_text())
    def test_recall_rejects_traversal(self):
        with self.assertRaises(ValueError):checks.recall(self.root,'../oops')
    def test_format_detection_no_arbitrary_pipeline(self):
        self.assertEqual(checks.inferred('ruff check --output-format=json .'),'ruff-json')
        self.assertEqual(checks.inferred('ruff check --output-format=json . | cat'),'plain')
        self.assertEqual(checks.inferred('pyright --outputjson'),'pyright-json')

if __name__=='__main__':unittest.main()
