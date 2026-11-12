"""Bounded immutable checkpoint publishing. No source/quote/ledger operations.

The collector is the sole writer: state/dashboard are frozen together at a
cycle boundary; raw JSONL files are append-only and snapshots name exact byte
prefixes. One worker owns Git; pending generations may only grow raw prefixes.
"""
from dataclasses import dataclass
import datetime as dt
import hashlib
import json
import os
import pathlib
import signal
import subprocess
import tempfile
import threading
import time


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


@dataclass(frozen=True)
class Prefix:
    path: str
    size: int
    device: int
    inode: int
    tail: bytes


@dataclass(frozen=True)
class Snapshot:
    generation: str
    state: bytes
    dashboard: bytes
    prefixes: tuple

    def contains(self, older):
        current = {p.path: p for p in self.prefixes}
        return all(p.path in current and current[p.path].size >= p.size
                   and (current[p.path].device, current[p.path].inode) == (p.device, p.inode)
                   for p in older.prefixes)


def capture(root):
    """Only called between cycles, never concurrently with ledger serialization."""
    root = pathlib.Path(root)
    state = (root / 'state.json').read_bytes()
    dashboard = (root / 'dashboard.json').read_bytes()
    generation = json.loads(state).get('updatedAt')
    if generation != json.loads(dashboard).get('updatedAt'):
        raise ValueError('State/dashboard generation mismatch')
    prefixes = []
    for path in sorted((root / 'data').rglob('*')):
        if not path.is_file():
            continue
        if path.is_symlink():
            raise ValueError('Raw evidence symlink rejected')
        with path.open('rb') as f:
            st = os.fstat(f.fileno())
            f.seek(max(0, st.st_size - 64))
            tail = f.read(st.st_size - f.tell())
        relative = str(path.relative_to(root.parent))
        if '\n' in relative or '\t' in relative:
            raise ValueError('Unsupported raw evidence path')
        prefixes.append(Prefix(relative, st.st_size, st.st_dev, st.st_ino, tail))
    return Snapshot(generation, state, dashboard, tuple(prefixes))


def freeze_prefix(repo, prefix, destination, cancel=None):
    """Copy only the captured append-only prefix, never subsequent live rows."""
    with (repo / prefix.path).open('rb') as source:
        st = os.fstat(source.fileno())
        if (st.st_dev, st.st_ino) != (prefix.device, prefix.inode) or st.st_size < prefix.size:
            raise ValueError('Raw evidence replaced or truncated: ' + prefix.path)
        source.seek(max(0, prefix.size - 64))
        if source.read(len(prefix.tail)) != prefix.tail:
            raise ValueError('Raw evidence prefix boundary changed: ' + prefix.path)
        source.seek(0)
        remaining = prefix.size
        with destination.open('wb') as out:
            while remaining:
                if cancel is not None and cancel.is_set():
                    raise RuntimeError('Checkpoint cancelled during raw freeze')
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError('Raw evidence truncated during freeze')
                out.write(chunk)
                remaining -= len(chunk)
        # Check again after copying. Append-only is a writer contract; this is
        # not a claim to detect arbitrary adversarial in-place prefix rewrites.
        source.seek(max(0, prefix.size - 64))
        if source.read(len(prefix.tail)) != prefix.tail or os.fstat(source.fileno()).st_size < prefix.size:
            raise ValueError('Raw evidence changed during freeze')


class GitPublisher:
    """Git subprocesses are cancellable; no working index or checkout writes."""
    def __init__(self, root, remote='origin', branch='main', command_timeout=60):
        self.root = pathlib.Path(root)
        self.repo = self.root.parent
        self.remote, self.branch = remote, branch
        self.command_timeout = command_timeout

    def run(self, args, cancel, env=None, data=None):
        if cancel.is_set():
            raise RuntimeError('Checkpoint cancelled; local evidence retained')
        command = ['git', '-c', 'core.sparseCheckout=false', '-c', 'index.sparse=false', *args]
        process = subprocess.Popen(command, cwd=self.repo, env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        deadline = time.monotonic() + self.command_timeout
        try:
            first = True
            while True:
                try:
                    out, _ = process.communicate(input=data if first else None, timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    first = False
                    if cancel.is_set() or time.monotonic() >= deadline:
                        raise RuntimeError('Checkpoint git ' + args[0] + ' cancelled or timed out')
            if process.returncode:
                raise RuntimeError('Checkpoint git ' + args[0] + ' failed (exit ' + str(process.returncode) + ')')
            return out.decode().strip()
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()

    def __call__(self, snapshot, cancel):
        with tempfile.TemporaryDirectory(prefix='sm-checkpoint-') as directory:
            td = pathlib.Path(directory)
            files = {'stupid-money-lab/state.json': snapshot.state,
                     'stupid-money-lab/dashboard.json': snapshot.dashboard}
            frozen = []
            manifest = {'protocol': 'immutable-checkpoint-v1', 'observedGeneration': snapshot.generation,
                        'stateHash': hashlib.sha256(snapshot.state).hexdigest(),
                        'dashboardHash': hashlib.sha256(snapshot.dashboard).hexdigest(),
                        'rawPrefixes': {p.path: p.size for p in snapshot.prefixes}}
            files['stupid-money-lab/checkpoint-manifest.json'] = json.dumps(manifest, separators=(',', ':')).encode()
            for name, content in files.items():
                path = td / ('frozen-' + str(len(frozen)))
                path.write_bytes(content)
                frozen.append((name, path))
            for prefix in snapshot.prefixes:
                if cancel.is_set():
                    raise RuntimeError('Checkpoint cancelled during freeze')
                path = td / ('frozen-' + str(len(frozen)))
                freeze_prefix(self.repo, prefix, path, cancel)
                frozen.append((prefix.path, path))
            # Hash frozen files once. Retries reuse identical bytes, not live files.
            blobs = self.run(['hash-object', '-w', '--stdin-paths'], cancel,
                             data=('\n'.join(str(p) for _, p in frozen) + '\n').encode()).splitlines()
            if len(blobs) != len(frozen):
                raise RuntimeError('Incomplete frozen blob set')
            index_info = ''.join('100644 ' + blob + '\t' + name + '\n'
                                 for (name, _), blob in zip(frozen, blobs)).encode()
            env = {**os.environ, 'GIT_INDEX_FILE': str(td / 'index')}
            last_error = None
            for _ in range(2):
                try:
                    self.run(['fetch', '--depth=1', self.remote, self.branch], cancel)
                    parent = self.run(['rev-parse', 'FETCH_HEAD'], cancel)
                    self.run(['read-tree', parent], cancel, env)
                    self.run(['update-index', '--index-info'], cancel, env, index_info)
                    tree = self.run(['write-tree'], cancel, env)
                    if tree == self.run(['rev-parse', parent + '^{tree}'], cancel):
                        return {'commit': parent, 'unchanged': True}
                    commit = self.run(['-c', 'user.name=Stupid Money research collector', '-c',
                                       'user.email=41898282+github-actions[bot]@users.noreply.github.com',
                                       'commit-tree', tree, '-p', parent, '-m',
                                       'Record immutable public paper checkpoint [skip ci]'], cancel, env)
                    self.run(['push', self.remote, commit + ':refs/heads/' + self.branch], cancel)
                    return {'commit': commit, 'unchanged': False}
                except Exception as error:
                    last_error = error
                    if cancel.is_set():
                        break
            raise last_error


class BackgroundPublisher:
    """One in-flight + one latest pending snapshot, with explicit receipts."""
    def __init__(self, publish):
        self.publish = publish
        self.condition = threading.Condition()
        self.cancel = threading.Event()
        self.pending = None
        self.inflight = None
        self.receipts = []
        self.latest_observed = None
        self.latest_published = None
        self.closing = False
        self.thread = threading.Thread(target=self._work, name='immutable-checkpoint', daemon=True)
        self.thread.start()

    def submit(self, snapshot):
        with self.condition:
            if self.closing:
                raise RuntimeError('Publisher is closing')
            previous = self.pending or self.inflight
            if previous and not snapshot.contains(previous):
                raise ValueError('New snapshot would drop raw evidence prefixes')
            self.pending = snapshot
            self.latest_observed = snapshot.generation
            self.condition.notify_all()

    def drain_receipts(self):
        with self.condition:
            result, self.receipts = self.receipts, []
            return result

    def status(self):
        with self.condition:
            return {'protocol': 'immutable-checkpoint-v1', 'latestObserved': self.latest_observed,
                    'latestPublished': self.latest_published,
                    'inflight': self.inflight.generation if self.inflight else None,
                    'pending': self.pending.generation if self.pending else None}

    def _work(self):
        while True:
            with self.condition:
                while self.pending is None and not self.closing:
                    self.condition.wait()
                if self.cancel.is_set() or (self.pending is None and self.closing):
                    return
                snapshot, self.pending = self.pending, None
                self.inflight = snapshot
            started, clock = stamp(), time.monotonic()
            receipt = {'protocol': 'immutable-checkpoint-v1', 'generation': snapshot.generation,
                       'startedAt': started, 'published': False}
            try:
                receipt.update(self.publish(snapshot, self.cancel))
                receipt['published'] = True
            except Exception as error:
                receipt['error'] = str(error)
            receipt.update(endedAt=stamp(), durationSeconds=time.monotonic() - clock)
            with self.condition:
                if receipt['published']:
                    self.latest_published = snapshot.generation
                self.receipts.append(receipt)
                self.inflight = None
                self.condition.notify_all()

    def close(self, drain_seconds=5):
        with self.condition:
            self.closing = True
            self.condition.notify_all()
        self.thread.join(max(0, drain_seconds))
        if self.thread.is_alive():
            self.cancel.set()
            with self.condition:
                self.condition.notify_all()
            self.thread.join(2)
        if self.thread.is_alive():
            raise RuntimeError('Publisher did not stop; do not start overlapping Git')
        return self.status()
