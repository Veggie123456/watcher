import hashlib
import json
import os
import pathlib
import subprocess
import tempfile
import threading
import unittest
import checkpoint_publisher as cp


def git(repo, *args, data=None, env=None):
    return subprocess.check_output(['git', '-c', 'user.name=Test', '-c',
        'user.email=test@example.invalid', *args], cwd=repo, input=data,
        env=env, stderr=subprocess.DEVNULL).decode().strip()


class GuardedTreeTests(unittest.TestCase):
    def test_guard_rejects_missing_nonblob_size_and_malformed_without_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = pathlib.Path(directory); root = repo / 'stupid-money-lab'; root.mkdir()
            git(repo, 'init', '-b', 'main')
            blob = git(repo, 'hash-object', '-w', '--stdin', data=b'valid')
            tree = git(repo, 'mktree', data=b'')
            publisher = cp.GitPublisher(root)
            publisher.verify_frozen_blobs([(blob, 5)], threading.Event())
            for expected in [[('f'*40, 5)], [(blob, 5), ('f'*40, 5)],
                             [(tree, 0)], [(blob, 6)], [('bad', 5)]]:
                with self.subTest(expected=expected), self.assertRaisesRegex(RuntimeError, 'Frozen blob'):
                    publisher.verify_frozen_blobs(expected, threading.Event())

    def test_cold_partial_clone_publication_preserves_unrelated_without_blob_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory); seed = base/'seed'; seed.mkdir()
            remote = base/'remote.git'; clone = base/'clone'
            git(seed, 'init', '-b', 'main')
            (seed/'unrelated.bin').write_bytes(os.urandom(2*1024*1024))
            original = (seed/'unrelated.bin').read_bytes()
            (seed/'stupid-money-lab').mkdir()
            for name in ['state.json', 'dashboard.json']:
                (seed/'stupid-money-lab'/name).write_text('{"updatedAt":"old"}')
            git(seed, 'add', '.'); git(seed, 'commit', '-m', 'seed')
            oid = git(seed, 'rev-parse', 'HEAD:unrelated.bin')
            git(base, 'clone', '--bare', str(seed), str(remote))
            git(remote, 'config', 'uploadpack.allowFilter', 'true')
            git(base, 'clone', '--filter=blob:none', '--no-checkout', '-b', 'main', remote.as_uri(), str(clone))
            def present():
                return subprocess.run(['git','--no-lazy-fetch','cat-file','-e',oid], cwd=clone,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
            self.assertFalse(present())
            root = clone/'stupid-money-lab'; root.mkdir()
            for name in ['state.json', 'dashboard.json']:
                (root/name).write_text('{"updatedAt":"new","value":123}')
            head = git(clone, 'rev-parse', 'HEAD')
            class Observed(cp.GitPublisher):
                tree_args = None
                def run(self, args, cancel, env=None, data=None):
                    result = super().run(args, cancel, env, data)
                    if args[0] == 'write-tree':
                        self.tree_args = args
                        if present(): raise AssertionError('unchanged blob fetched')
                    return result
            publisher = Observed(root)
            result = publisher(cp.capture(root), threading.Event())
            self.assertEqual(publisher.tree_args, ['write-tree','--missing-ok'])
            self.assertFalse(present())
            self.assertEqual(git(clone,'rev-parse','HEAD'), head)
            self.assertFalse((clone/'.git/index').exists())
            self.assertEqual(json.loads(git(remote,'show','main:stupid-money-lab/state.json'))['updatedAt'], 'new')
            self.assertEqual(subprocess.check_output(['git','show','main:unrelated.bin'],cwd=remote),original)
            git(remote, 'fsck', '--full')
            self.assertTrue(result['commit'])

    def test_missing_edited_blob_aborts_before_tree_or_push(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = pathlib.Path(directory); root=repo/'stupid-money-lab'; root.mkdir()
            git(repo,'init','-b','main')
            for name in ['state.json','dashboard.json']:
                (root/name).write_text('{"updatedAt":"unique-new"}')
            class Broken(cp.GitPublisher):
                stages=[]
                def run(self,args,cancel,env=None,data=None):
                    self.stages.append(args[0])
                    out=super().run(args,cancel,env,data)
                    if args[0]=='hash-object':
                        oid=out.splitlines()[0]
                        (repo/'.git/objects'/oid[:2]/oid[2:]).unlink()
                    return out
            publisher=Broken(root)
            with self.assertRaisesRegex(RuntimeError,'Frozen blob'):
                publisher(cp.capture(root),threading.Event())
            self.assertNotIn('write-tree',publisher.stages)
            self.assertNotIn('push',publisher.stages)


if __name__ == '__main__': unittest.main()
