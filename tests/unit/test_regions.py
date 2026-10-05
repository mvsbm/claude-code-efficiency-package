import json,os,re,subprocess,sys,tempfile,unittest
from pathlib import Path
from claude_code_efficiency import operations
class RegionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.file=self.root/'code.go';self.file.write_bytes('same\né\nsame\nlast'.encode());self.env={**os.environ,'EFFICIENCY_STATE':str(self.root/'state')}
 def tearDown(self):self.tmp.cleanup()
 def cli(self,*args,data=None):return subprocess.run([sys.executable,'-m','claude_code_efficiency.operations',*args],input=data,text=True,capture_output=True,env=self.env)
 def read(self,start,end):
  r=self.cli('region-read','--file',str(self.file),'--start',str(start),'--end',str(end));self.assertEqual(r.returncode,0,r.stderr);return re.search(r'region_[a-f0-9]{24}',r.stdout).group()
 def replace(self,id,text,*args):return self.cli('region-replace',id,'--replacement','-',*args,data=text)
 def test_repeated_text_position_not_unique_anchor(self):
  id=self.read(3,3);r=self.replace(id,'changed\n');self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(self.file.read_text(),'same\né\nchanged\nlast')
 def test_first_last_and_no_trailing_newline(self):
  self.assertEqual(self.replace(self.read(4,4),'fin').returncode,0);self.assertTrue(self.file.read_bytes().endswith(b'fin'))
  self.assertEqual(self.replace(self.read(1,1),'first\n').returncode,0)
 def test_stale_anywhere_no_validation(self):
  id=self.read(1,1);self.file.write_text('same\nchanged elsewhere\nsame\nlast');w=self.root/'w'
  r=self.replace(id,'new\n','--then-run',f'touch {w}');self.assertNotEqual(r.returncode,0);self.assertIn('Stale region',r.stderr);self.assertFalse(w.exists())
 def test_original_source_archived_and_replacement_archived(self):
  id=self.read(2,2);original=self.file.read_bytes();r=self.replace(id,'λ\n');self.assertEqual(r.returncode,0,r.stderr)
  self.assertEqual((self.root/'state/regions'/(id+'.source')).read_bytes(),original);self.assertEqual(len(list((self.root/'state/inputs').glob('*.raw'))),1)
 def test_validation_failure_retains_edit(self):
  r=self.replace(self.read(2,2),'λ\n','--then-run','exit 7');self.assertEqual(r.returncode,7);self.assertIn('λ',self.file.read_text())
 def test_symlink_target_and_archive_refused(self):
  link=self.root/'link';link.symlink_to(self.file);self.assertNotEqual(self.cli('region-read','--file',str(link),'--start','1','--end','1').returncode,0)
  id=self.read(1,1);snapshot=self.root/'state/regions'/(id+'.source');snapshot.unlink();snapshot.symlink_to(self.file);self.assertNotEqual(self.replace(id,'x').returncode,0)
 def test_corrupt_metadata_and_snapshot(self):
  id=self.read(1,1);p=self.root/'state/regions'/(id+'.json');p.write_text('{}');self.assertNotEqual(self.replace(id,'x').returncode,0)
  id2=self.read(2,2);(self.root/'state/regions'/(id2+'.source')).write_text('wrong');self.assertNotEqual(self.replace(id2,'x').returncode,0)
 def test_invalid_range_and_id(self):
  for start,end in [(0,1),(3,2),(1,5)]:self.assertNotEqual(self.cli('region-read','--file',str(self.file),'--start',str(start),'--end',str(end)).returncode,0)
  self.assertNotEqual(self.replace('../outside','x').returncode,0)
 def test_non_utf8_refused(self):
  self.file.write_bytes(b'\xff');self.assertNotEqual(self.cli('region-read','--file',str(self.file),'--start','1','--end','1').returncode,0)
 def test_whole_file_and_crlf_preserved(self):
  self.file.write_bytes(b'a\r\nb\r\nc');r=self.replace(self.read(2,2),'B\r\n');self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(self.file.read_bytes(),b'a\r\nB\r\nc')
if __name__=='__main__':unittest.main()
