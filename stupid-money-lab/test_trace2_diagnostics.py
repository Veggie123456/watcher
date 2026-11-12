import json
import os
import pathlib
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
import checkpoint_publisher as cp


def git(where, *args, data=None):
    return subprocess.check_output(['git','-c','user.name=Trace test','-c',
        'user.email=trace@example.invalid',*args], cwd=where, input=data,
        stderr=subprocess.DEVNULL, timeout=10).decode().strip()


class TraceSummaryTests(unittest.TestCase):
    def test_complete_summary_counts_commands_without_any_private_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/'trace'
            secret='DO_NOT_SAVE_SECRET'
            rows=[{'event':'start','sid':secret,'argv':['git','write-tree',secret]},
                  {'event':'child_start','sid':secret,'argv':['git','-c','http.extraheader='+secret,'fetch','https://user:'+secret+'@example.invalid']},
                  {'event':'child_start','argv':['git','show','fetch']},
                  {'event':'child_start','argv':['https://example.invalid/fetch']},
                  {'event':'child_start','argv':['/usr/lib/git-core/git-index-pack','--stdin',secret]},
                  {'event':'exit','sid':secret}]
            path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            result=cp.summarize_trace2(path)
            self.assertEqual(result['status'],'complete')
            self.assertEqual(result['exactFetchChildStarts'],1)
            self.assertEqual(result['observedChildStarts'],{'fetch':1,'other':2,'index-pack':1})
            self.assertNotIn(secret,json.dumps(result));self.assertNotIn('example.invalid',json.dumps(result))
            self.assertNotIn('http.extraheader',json.dumps(result))

    def test_missing_empty_malformed_truncated_and_unfinished_are_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/'trace'
            self.assertIsNone(cp.summarize_trace2(path)['exactFetchChildStarts'])
            path.write_bytes(b'');self.assertEqual(cp.summarize_trace2(path)['status'],'empty')
            for raw,kwargs in [(b'{bad}\n',{}),
                               (b'{"event":"start","sid":"root"}\n',{}),
                               (b'x'*100+b'\n',{'byte_limit':32}),
                               (b'x'*100+b'\n',{'line_limit':32}),
                               (b'{}\n{}\n',{'event_limit':1})]:
                path.write_bytes(raw);result=cp.summarize_trace2(path,**kwargs)
                self.assertEqual(result['status'],'partial')
                self.assertTrue(result['countsAreLowerBounds'])
                self.assertIsNone(result['exactFetchChildStarts'])
                self.assertLessEqual(result['bytesInspected'],kwargs.get('byte_limit',262144))

    def run_and_record_trace(self, root, operation):
        paths=[];real_popen=subprocess.Popen
        def popen(*args,**kwargs):
            env=kwargs.get('env') or {}
            if 'GIT_TRACE2_EVENT' in env:paths.append(pathlib.Path(env['GIT_TRACE2_EVENT']))
            self.assertEqual(env.get('GIT_TRACE2_CONFIG_PARAMS'),'')
            self.assertEqual(env.get('GIT_TRACE2_ENV_VARS'),'')
            return real_popen(*args,**kwargs)
        with patch.object(cp.subprocess,'Popen',side_effect=popen):
            result=operation()
        self.assertEqual(len(paths),1);self.assertFalse(paths[0].exists())
        return result

    def test_actual_failure_keeps_diagnostic_and_deletes_raw_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            repo=pathlib.Path(directory);root=repo/'stupid-money-lab';root.mkdir();git(repo,'init')
            bad_index=repo/'bad-index';bad_index.write_bytes(b'bad')
            def operation():
                with self.assertRaises(cp.GitCommandError) as caught:
                    cp.GitPublisher(root).run(['write-tree'],threading.Event(),
                        {**os.environ,'GIT_INDEX_FILE':str(bad_index)})
                return caught.exception.diagnostic
            result=self.run_and_record_trace(root,operation)
            self.assertEqual(result['stage'],'write-tree');self.assertEqual(result['result'],'failed')
            self.assertIn(result['trace2']['status'],['complete','partial'])
            self.assertGreater(result['trace2']['eventsInspected'],0)
            self.assertNotIn(str(repo),json.dumps(result))

    def test_success_preserves_tree_result_and_deletes_raw_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            repo=pathlib.Path(directory);root=repo/'stupid-money-lab';root.mkdir();git(repo,'init');git(repo,'read-tree','--empty')
            result=self.run_and_record_trace(root,lambda:cp.GitPublisher(root).run(['write-tree'],threading.Event()))
            self.assertEqual(result,'4b825dc642cb6eb9a060e54bf8d69288fbee4904')

    def test_real_partial_clone_fetch_is_visible_during_cancelled_tree_write(self):
        with tempfile.TemporaryDirectory() as directory:
            base=pathlib.Path(directory);bare=base/'remote.git';seed=base/'seed';seed.mkdir()
            git(base,'init','--bare',str(bare));git(bare,'config','uploadpack.allowFilter','true')
            git(seed,'init','-b','main');(seed/'unrelated').write_bytes(os.urandom(4096));(seed/'state').write_text('old')
            git(seed,'add','.');git(seed,'commit','-m','seed');git(seed,'remote','add','origin',str(bare));git(seed,'push','origin','main')
            repo=base/'runner';git(base,'clone','--filter=blob:none','--no-checkout','--branch','main',bare.as_uri(),str(repo))
            root=repo/'stupid-money-lab';root.mkdir();index=base/'private-index';env={**os.environ,'GIT_INDEX_FILE':str(index)}
            subprocess.check_call(['git','read-tree','HEAD'],cwd=repo,env=env)
            blob=git(repo,'hash-object','-w','--stdin',data=b'new')
            subprocess.run(['git','update-index','--index-info'],cwd=repo,env=env,
                           input=('100644 '+blob+'\tstate\n').encode(),check=True)
            blocker=base/'slow-upload-pack'
            blocker.write_text('#!/bin/sh\nsleep 30\nexec git-upload-pack "$@"\n');blocker.chmod(0o755)
            git(repo,'config','remote.origin.uploadpack',str(blocker))
            def operation():
                with self.assertRaises(cp.GitCommandError) as caught:
                    cp.GitPublisher(root,command_timeout=.1).run(['write-tree'],threading.Event(),env)
                return caught.exception.diagnostic
            result=self.run_and_record_trace(root,operation)
            self.assertEqual(result['result'],'timed_out')
            self.assertGreaterEqual(result['trace2']['observedChildStarts'].get('fetch',0),1)
            self.assertTrue(result['trace2']['countsAreLowerBounds'])
            self.assertIsNone(result['trace2']['exactFetchChildStarts'])
            self.assertNotIn(str(base),json.dumps(result))


if __name__=='__main__':unittest.main()
