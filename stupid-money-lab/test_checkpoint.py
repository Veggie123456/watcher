import pathlib,subprocess,tempfile,unittest
from unittest.mock import patch
import watcher

class CheckpointTests(unittest.TestCase):
 def test_data_publication_preserves_concurrent_source_and_working_checkout(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);bare=root/'remote.git';runner=root/'runner';editor=root/'editor'
   def git(where,*args):
    return subprocess.check_output(['git','-c','user.name=Test','-c','user.email=test@example.invalid',*args],cwd=where,stderr=subprocess.DEVNULL).decode().strip()
   git(root,'init','--bare',str(bare));git(root,'clone',str(bare),str(runner));git(runner,'checkout','-b','main')
   lab=runner/'stupid-money-lab';lab.mkdir();(lab/'data').mkdir();(lab/'data'/'events.jsonl').write_text('{}\n');(lab/'state.json').write_text('{}');(lab/'dashboard.json').write_text('{}');(runner/'source.txt').write_text('old')
   git(runner,'add','.');git(runner,'commit','-m','initial');git(runner,'push','origin','main');git(root,'clone','-b','main',str(bare),str(editor))
   (editor/'source.txt').write_text('new independent source edit');git(editor,'add','.');git(editor,'commit','-m','source update');git(editor,'push','origin','main')
   old_head=git(runner,'rev-parse','HEAD');(lab/'state.json').write_text('{"fresh":1}');(lab/'dashboard.json').write_text('{"fresh":1}')
   with patch.object(watcher,'ROOT',lab):self.assertTrue(watcher.publish_checkpoint())
   self.assertEqual(git(runner,'rev-parse','HEAD'),old_head)
   self.assertEqual(git(bare,'show','main:source.txt'),'new independent source edit')
   self.assertEqual(git(bare,'show','main:stupid-money-lab/state.json'),'{"fresh":1}')
   self.assertFalse((runner/'.git'/'rebase-merge').exists())
   with patch.object(watcher,'ROOT',lab):self.assertTrue(watcher.publish_checkpoint())
