import json
import pathlib
import subprocess
import tempfile
import threading
import time
import unittest
import checkpoint_publisher as cp
import watcher
from unittest.mock import patch


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self.temp.name)
        self.root = self.repo / 'stupid-money-lab'
        (self.root / 'data').mkdir(parents=True)
        self.raw = self.root / 'data' / 'events.jsonl'
        self.raw.write_text('{"loss":1}\n')
        self.write(1)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, generation):
        value = json.dumps({'updatedAt': str(generation), 'balance': 1000 - generation})
        for name in ('state.json', 'dashboard.json'):
            (self.root / name).write_text(value)

    def test_prefix_excludes_later_rows_and_state_generation_is_frozen(self):
        first = cp.capture(self.root)
        self.write(2)
        with self.raw.open('a') as f:
            f.write('{"loss":2}\n')
        target = self.repo / 'frozen'
        cp.freeze_prefix(self.repo, first.prefixes[0], target)
        self.assertEqual(target.read_text(), '{"loss":1}\n')
        self.assertEqual(json.loads(first.state), json.loads(first.dashboard))
        self.assertEqual(json.loads(first.state)['updatedAt'], '1')

    def test_capture_waits_for_complete_concurrent_raw_row(self):
        entered, release = threading.Event(), threading.Event()
        def writer():
            with watcher.EVIDENCE_LOCK:
                with self.raw.open('a') as stream:
                    stream.write('{"loss":'); stream.flush(); entered.set()
                    release.wait(1)
                    stream.write('2}\n')
        thread = threading.Thread(target=writer)
        thread.start(); self.assertTrue(entered.wait(1))
        timer = threading.Timer(.02, release.set); timer.start()
        try:
            with patch.object(watcher, 'ROOT', self.root):
                snapshot = watcher.capture_checkpoint()
            target = self.repo / 'frozen'
            cp.freeze_prefix(self.repo, snapshot.prefixes[0], target)
            self.assertEqual([json.loads(row)['loss'] for row in target.read_text().splitlines()], [1, 2])
        finally:
            release.set(); thread.join(1); timer.cancel()

    def test_generation_mismatch_is_rejected(self):
        (self.root / 'dashboard.json').write_text('{"updatedAt":"other"}')
        with self.assertRaisesRegex(ValueError, 'generation mismatch'):
            cp.capture(self.root)

    def test_truncation_and_rewrite_at_boundary_are_rejected(self):
        snapshot = cp.capture(self.root)
        self.raw.write_text('')
        with self.assertRaisesRegex(ValueError, 'truncated'):
            cp.freeze_prefix(self.repo, snapshot.prefixes[0], self.repo / 'frozen')
        self.raw.write_text('{"loss":9}\n')
        with self.assertRaisesRegex(ValueError, 'boundary changed'):
            cp.freeze_prefix(self.repo, snapshot.prefixes[0], self.repo / 'frozen')

    def test_blocked_git_does_not_block_cycles_and_coalescing_retains_losses(self):
        entered, release = threading.Event(), threading.Event()
        calls, active = [], []
        def publish(snapshot, cancel):
            active.append(snapshot.generation)
            self.assertEqual(len(active), 1)
            entered.set()
            while not release.wait(.005):
                if cancel.is_set():
                    raise RuntimeError('cancelled')
            calls.append(snapshot)
            active.pop()
            return {'commit': 'test'}
        publisher = cp.BackgroundPublisher(publish)
        try:
            publisher.submit(cp.capture(self.root))
            self.assertTrue(entered.wait(1))
            book = {'time':100000,'observedAt':'1970-01-01T00:01:40+00:00',
                    'levels':[[{'px':'99.9','sz':'10'}],[{'px':'100.1','sz':'10'}]]}
            event = {'id':1,'coin':'BTC','createdAt':'1970-01-01T00:01:00+00:00',
                     'payload':{'cohort':'GENIUS','side':'LONG','wallet':'0x'+'1'*40,
                                'action':'OPENED','leverage':{'value':1,'type':'cross'}}}
            scenario = watcher.create(event, book, 5)
            quote_receipts = []
            start = time.monotonic()
            for generation in range(2, 22):
                book['time'] += 10000
                with patch.object(watcher, 'append', side_effect=lambda kind, row: quote_receipts.append((kind, row))):
                    watcher.update(scenario, book)
                self.write(generation)
                with self.raw.open('a') as f:
                    f.write(json.dumps({'loss': generation}) + '\n')
                publisher.submit(cp.capture(self.root))
            self.assertLess(time.monotonic() - start, 1)
            self.assertEqual(len(quote_receipts), 20)
            self.assertEqual(publisher.status()['pending'], '21')
            self.assertIsNone(publisher.status()['latestPublished'])
            release.set()
            publisher.close(2)
            self.assertEqual([s.generation for s in calls], ['1', '21'])
            target = self.repo / 'frozen'
            cp.freeze_prefix(self.repo, calls[-1].prefixes[0], target)
            self.assertEqual(len(target.read_text().splitlines()), 21)
            self.assertEqual(publisher.status()['latestPublished'], '21')
        finally:
            release.set()
            publisher.close(1)

    def test_failure_is_unpublished_retry_and_bounded_shutdown_retain_evidence(self):
        entered = threading.Event()
        def blocked(snapshot, cancel):
            entered.set()
            cancel.wait()
            raise RuntimeError('cancelled checkpoint')
        publisher = cp.BackgroundPublisher(blocked)
        publisher.submit(cp.capture(self.root))
        self.assertTrue(entered.wait(1))
        start = time.monotonic()
        status = publisher.close(.01)
        self.assertLess(time.monotonic() - start, 1)
        self.assertIsNone(status['latestPublished'])
        self.assertEqual(status['latestObserved'], '1')
        self.assertFalse(publisher.drain_receipts()[0]['published'])
        self.assertEqual(self.raw.read_text(), '{"loss":1}\n')
        retry = cp.BackgroundPublisher(lambda snapshot, cancel: {'commit': 'retry'})
        retry.submit(cp.capture(self.root))
        retry.close(1)
        self.assertEqual(retry.status()['latestPublished'], '1')

    def test_coalescing_rejects_missing_raw_file(self):
        entered = threading.Event()
        def blocked(snapshot, cancel):
            entered.set()
            cancel.wait()
            raise RuntimeError('cancelled')
        publisher = cp.BackgroundPublisher(blocked)
        publisher.submit(cp.capture(self.root))
        self.assertTrue(entered.wait(1))
        self.raw.unlink()
        with self.assertRaisesRegex(ValueError, 'drop raw evidence'):
            publisher.submit(cp.capture(self.root))
        publisher.close(0)

    def test_real_git_preserves_unrelated_paths_and_freezes_generation(self):
        def git(where, *args):
            return subprocess.check_output(['git', '-c', 'user.name=Test', '-c',
                'user.email=test@example.invalid', *args], cwd=where, stderr=subprocess.DEVNULL).decode().strip()
        bare = self.repo / 'remote.git'
        git(self.repo, 'init', '--bare', str(bare))
        git(self.repo, 'init', '-b', 'main')
        (self.repo / 'unrelated.txt').write_text('preserve')
        git(self.repo, 'add', 'unrelated.txt', 'stupid-money-lab')
        git(self.repo, 'commit', '-m', 'initial')
        git(self.repo, 'remote', 'add', 'origin', str(bare))
        git(self.repo, 'push', 'origin', 'main')
        original_head = git(self.repo, 'rev-parse', 'HEAD')
        snapshot = cp.capture(self.root)
        self.write(99)
        with self.raw.open('a') as f:
            f.write('{"loss":99}\n')
        result = cp.GitPublisher(self.root)(snapshot, threading.Event())
        self.assertTrue(result['commit'])
        self.assertEqual(git(bare, 'show', 'main:unrelated.txt'), 'preserve')
        self.assertEqual(json.loads(git(bare, 'show', 'main:stupid-money-lab/state.json'))['updatedAt'], '1')
        self.assertEqual(git(bare, 'show', 'main:stupid-money-lab/data/events.jsonl'), '{"loss":1}')
        self.assertEqual(git(self.repo, 'rev-parse', 'HEAD'), original_head)
        self.assertEqual(json.loads(git(bare, 'show', 'main:stupid-money-lab/checkpoint-manifest.json'))['observedGeneration'], '1')

    def test_non_fast_forward_retry_keeps_new_unrelated_commit(self):
        def git(where, *args):
            return subprocess.check_output(['git', '-c', 'user.name=Test', '-c',
                'user.email=test@example.invalid', *args], cwd=where, stderr=subprocess.DEVNULL).decode().strip()
        bare, editor = self.repo / 'remote.git', self.repo / 'editor'
        git(self.repo, 'init', '--bare', str(bare))
        git(self.repo, 'init', '-b', 'main')
        (self.repo / 'unrelated.txt').write_text('old')
        git(self.repo, 'add', 'unrelated.txt', 'stupid-money-lab')
        git(self.repo, 'commit', '-m', 'initial')
        git(self.repo, 'remote', 'add', 'origin', str(bare)); git(self.repo, 'push', 'origin', 'main')
        git(self.repo, 'clone', '-b', 'main', str(bare), str(editor))
        class ConcurrentPublisher(cp.GitPublisher):
            pushes = 0
            def run(self, args, cancel, env=None, data=None):
                if args[0] == 'push':
                    self.pushes += 1
                    if self.pushes == 1:
                        (editor / 'unrelated.txt').write_text('concurrent change')
                        git(editor, 'add', 'unrelated.txt'); git(editor, 'commit', '-m', 'concurrent')
                        git(editor, 'push', 'origin', 'main')
                return super().run(args, cancel, env, data)
        publisher = ConcurrentPublisher(self.root)
        result = publisher(cp.capture(self.root), threading.Event())
        self.assertTrue(result['commit']); self.assertEqual(publisher.pushes, 2)
        self.assertEqual(result['attemptDiagnostics'][0]['command']['stage'], 'push')
        self.assertIn('non_fast_forward', result['attemptDiagnostics'][0]['command']['stderrClasses'])
        self.assertEqual(git(bare, 'show', 'main:unrelated.txt'), 'concurrent change')
        self.assertEqual(json.loads(git(bare, 'show', 'main:stupid-money-lab/state.json'))['updatedAt'], '1')

    def test_collector_exception_closes_publisher_before_process_fallback(self):
        import ast
        import inspect
        import sys
        from unittest.mock import Mock
        # Execute the actual CLI block with a failing cycle and no network.
        main = ast.parse(inspect.getsource(watcher)).body[-1]
        code = compile(ast.Module(body=[main], type_ignores=[]), 'watcher-cli', 'exec')
        publisher, oracle = Mock(), Mock()
        publisher.drain_receipts.return_value = []
        publisher.status.return_value = {'latestPublished': None}
        publisher.close.return_value = {'latestPublished': None, 'pending': '1'}
        scope = dict(vars(watcher), __name__='__main__', ROOT=self.root,
                     cycle=Mock(side_effect=ValueError('cycle failed')), append=Mock())
        with patch.object(sys, 'argv', ['watcher.py', '--publish-every', '30']), \
             patch.object(watcher.signal, 'signal'), \
             patch.object(watcher.oracle_capture, 'BackgroundCollector', return_value=oracle), \
             patch.object(cp, 'BackgroundPublisher', return_value=publisher):
            with self.assertRaisesRegex(ValueError, 'cycle failed'):
                exec(code, scope)
        oracle.close.assert_called_once()
        publisher.close.assert_called_once_with(drain_seconds=5)
        self.assertEqual(scope['append'].call_args.args[1]['kind'], 'shutdown')
        self.assertIsNone(scope['append'].call_args.args[1]['latestPublished'])

    def test_retry_uses_fresh_private_index_after_timeout_leaves_lock(self):
        def git(where, *args):
            return subprocess.check_output(['git', '-c', 'user.name=Test', '-c',
                'user.email=test@example.invalid', *args], cwd=where, stderr=subprocess.DEVNULL).decode().strip()
        bare = self.repo / 'remote.git'
        git(self.repo, 'init', '--bare', str(bare)); git(self.repo, 'init', '-b', 'main')
        (self.repo / 'unrelated.txt').write_text('preserve')
        git(self.repo, 'add', 'unrelated.txt', 'stupid-money-lab'); git(self.repo, 'commit', '-m', 'initial')
        git(self.repo, 'remote', 'add', 'origin', str(bare)); git(self.repo, 'push', 'origin', 'main')
        checkout_index = (self.repo / '.git' / 'index').read_bytes()
        class InterruptedPublisher(cp.GitPublisher):
            reads = []
            first_lock = None
            second_read_saw_retained_lock = False
            interrupted = False
            def run(self, args, cancel, env=None, data=None):
                if args[0] == 'read-tree':
                    self.reads.append(env['GIT_INDEX_FILE'])
                    if len(self.reads) == 2:
                        self.second_read_saw_retained_lock = self.first_lock.exists()
                if args[0] == 'write-tree' and not self.interrupted:
                    self.interrupted = True
                    self.first_lock = pathlib.Path(env['GIT_INDEX_FILE'] + '.lock')
                    self.first_lock.write_text('left by interrupted private index writer')
                    raise cp.GitCommandError('write-tree timed out',
                        {'stage':'write-tree','result':'timed_out','returnCode':-9})
                return super().run(args, cancel, env, data)
        publisher = InterruptedPublisher(self.root)
        result = publisher(cp.capture(self.root), threading.Event())
        self.assertTrue(result['commit']); self.assertEqual(len(publisher.reads), 2)
        self.assertNotEqual(publisher.reads[0], publisher.reads[1])
        self.assertTrue(publisher.second_read_saw_retained_lock)
        self.assertEqual(result['attemptDiagnostics'][0]['command']['result'], 'timed_out')
        self.assertEqual((self.repo / '.git' / 'index').read_bytes(), checkout_index)
        self.assertEqual(git(bare, 'show', 'main:unrelated.txt'), 'preserve')
        self.assertEqual(json.loads(git(bare, 'show', 'main:stupid-money-lab/state.json'))['updatedAt'], '1')

    def test_git_timeout_and_cancellation_kill_child_group(self):
        # Real local Git hook stalls push, exercising cancellation below Popen.
        bare = self.repo / 'remote.git'
        subprocess.run(['git', 'init', '--bare', str(bare)], check=True, capture_output=True)
        hook = bare / 'hooks' / 'pre-receive'
        hook.write_text('#!/bin/sh\nsleep 30\n')
        hook.chmod(0o755)
        subprocess.run(['git', 'init', '-b', 'main'], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(['git', 'remote', 'add', 'origin', str(bare)], cwd=self.repo, check=True)
        # run a hung Git command directly; no remote branch/credentials required.
        cancel = threading.Event()
        timer = threading.Timer(.05, cancel.set)
        timer.start()
        start = time.monotonic()
        try:
            with self.assertRaises(RuntimeError):
                cp.GitPublisher(self.root).run(['-c', 'alias.stall=!sleep 30', 'stall'], cancel)
            self.assertLess(time.monotonic() - start, 2)
        finally:
            timer.cancel()


class CommandDiagnosticTests(unittest.TestCase):
    def test_diagnostics_do_not_persist_secret_stderr_or_arguments_and_are_bounded(self):
        secret = 'DO_NOT_SAVE_PRIVATE_TOKEN'
        stderr = ('fatal: Authentication failed for https://user:' + secret + '@example.invalid\n' +
                  'fatal: unable to read tree abc\n' + 'x' * 9000).encode()
        row = cp.command_diagnostic(['read-tree', secret], 'start', .25, 'failed', 128, stderr)
        encoded = json.dumps(row)
        self.assertNotIn(secret, encoded); self.assertNotIn('example.invalid', encoded)
        self.assertNotIn('unable to read tree abc', encoded)
        self.assertEqual(row['stderrInspectedBytes'], 8192)
        self.assertTrue(row['stderrInspectionTruncated'])
        self.assertIn('authentication_or_permission', row['stderrClasses'])
        self.assertIn('missing_or_invalid_object', row['stderrClasses'])
        self.assertLess(len(encoded), 1000)

    def test_first_timeout_and_second_read_tree_error_both_survive_in_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory) / 'stupid-money-lab'; root.mkdir()
            for name in ['state.json', 'dashboard.json']:
                (root / name).write_text('{"updatedAt":"1"}')
            publisher = cp.GitPublisher(root)
            read_count = 0
            verified = []
            def run(args, cancel, env=None, data=None):
                nonlocal read_count
                if args[0] == 'hash-object':
                    verified[:] = [(str(i + 1).zfill(40), pathlib.Path(p).stat().st_size)
                                   for i, p in enumerate(data.decode().splitlines())]
                    return '\n'.join(oid for oid, _ in verified)
                if 'cat-file' in args:
                    return '\n'.join(f'{oid} blob {size}' for oid, size in verified)
                if args[0] == 'rev-parse': return 'parent'
                if args[0] == 'read-tree':
                    read_count += 1
                    if read_count == 2:
                        raise cp.GitCommandError('read-tree failed', {'stage':'read-tree','result':'failed','returnCode':128})
                if args[0] == 'write-tree':
                    raise cp.GitCommandError('write-tree timed out', {'stage':'write-tree','result':'timed_out','returnCode':-9})
                return ''
            with patch.object(publisher, 'run', side_effect=run):
                worker = cp.BackgroundPublisher(publisher)
                worker.submit(cp.capture(root)); worker.close(1)
                receipt = worker.drain_receipts()[0]
            self.assertFalse(receipt['published']); self.assertIsNone(worker.status()['latestPublished'])
            self.assertEqual([r['command']['stage'] for r in receipt['attemptDiagnostics']], ['write-tree','read-tree'])
            self.assertEqual([r['command']['result'] for r in receipt['attemptDiagnostics']], ['timed_out','failed'])
            self.assertEqual([r['attempt'] for r in receipt['attemptDiagnostics']], [1,2])

    def test_actual_git_timeout_records_stage_and_timeout_without_raw_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory) / 'stupid-money-lab'; root.mkdir()
            with self.assertRaises(cp.GitCommandError) as caught:
                cp.GitPublisher(root, command_timeout=.01).run(
                    ['-c','alias.stall=!sleep 30','stall'], threading.Event())
            diagnostic = caught.exception.diagnostic
            self.assertEqual(diagnostic['result'], 'timed_out')
            self.assertEqual(diagnostic['stage'], 'other')
            self.assertNotIn('sleep', json.dumps(diagnostic))
            self.assertLess(diagnostic['durationSeconds'], 2)


if __name__ == '__main__':
    unittest.main()
