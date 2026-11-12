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
import re
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


class GitCommandError(RuntimeError):
    def __init__(self, message, diagnostic):
        super().__init__(message)
        self.diagnostic = diagnostic


class PublicationAttemptsError(RuntimeError):
    def __init__(self, error, attempts):
        super().__init__(str(error))
        self.attempt_diagnostics = attempts


def command_diagnostic(args, started_at, elapsed, result, returncode, stderr):
    """Persist allowlisted categories/counts only, never raw stderr/argv/URLs.

    Classification inspects at most 8192 bytes. This is intentionally lossy:
    unrecognized errors stay unknown; classifications are diagnostic hints.
    """
    allowed = {'hash-object', 'cat-file', 'fetch', 'rev-parse', 'read-tree', 'update-index',
               'write-tree', 'commit-tree', 'push'}
    stage = next((x for x in args if x in allowed), 'other')
    sample = stderr[:8192].decode('utf-8', errors='replace').lower()
    patterns = {
        'authentication_or_permission': r'authentication failed|could not read username|permission denied|access denied',
        'network_or_transport': r'could not resolve|failed to connect|connection (?:reset|refused)|remote end hung up|rpc failed|http [45][0-9][0-9]',
        'missing_or_invalid_object': r'unable to read tree|not a tree|bad object|missing (?:blob|tree|object)|invalid object|not a valid object',
        'partial_clone_object_fetch': r'promisor|could not fetch.*object',
        'index_lock': r'index.lock|another git process|unable to create.*lock',
        'index_corruption': r'index file corrupt|index file smaller|bad signature|unknown index',
        'sparse_checkout': r'sparse.checkout|sparse index',
        'non_fast_forward': r'non.fast.forward|fetch first|updates were rejected',
        'disk_or_memory': r'no space left|out of memory|cannot allocate memory',
    }
    classes = [name for name, pattern in patterns.items() if re.search(pattern, sample)]
    return {'protocol': 'git-command-diagnostic-v1', 'stage': stage,
            'startedAt': started_at, 'endedAt': stamp(),
            'durationSeconds': max(0.0, elapsed), 'result': result,
            'returnCode': returncode, 'stderrBytes': len(stderr),
            'stderrInspectedBytes': min(len(stderr), 8192),
            'stderrInspectionTruncated': len(stderr) > 8192,
            'stderrClasses': classes or ['unclassified']}

def trace_child_category(argv):
    """Return only a fixed category; no argument values leave this function."""
    allowed = {'fetch', 'fetch-pack', 'index-pack', 'remote-https', 'remote-http',
               'remote-file', 'upload-pack', 'pack-objects'}
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
        return 'other'
    executable = pathlib.PurePath(argv[0]).name.removesuffix('.exe')
    if executable == 'git':
        index = 1
        while index < len(argv) and argv[index].startswith('-'):
            index += 2 if argv[index] in {'-c', '-C', '--git-dir', '--work-tree', '--namespace'} else 1
        command = argv[index] if index < len(argv) else ''
    elif executable.startswith('git-'):
        command = executable.removeprefix('git-')
    else:
        return 'other'
    return command if command in allowed else 'other'


def summarize_trace2(path, byte_limit=262144, event_limit=2048, line_limit=8192):
    """Bounded privacy-scrubbed summary. Missing/partial counts are lower bounds."""
    result = {'protocol': 'git-trace2-summary-v1', 'status': 'missing',
              'bytesObserved': None, 'bytesInspected': 0, 'eventsInspected': 0,
              'byteLimit': byte_limit, 'eventLimit': event_limit, 'lineLimit': line_limit,
              'truncated': False, 'malformedLines': 0, 'oversizeLines': 0,
              'rootExitObserved': False, 'observedChildStarts': {},
              'countsAreLowerBounds': True, 'exactFetchChildStarts': None}
    try:
        with pathlib.Path(path).open('rb') as stream:
            result['bytesObserved'] = os.fstat(stream.fileno()).st_size
            raw = stream.read(byte_limit + 1)
    except FileNotFoundError:
        return result
    except OSError:
        result['status'] = 'unreadable'
        return result
    result['truncated'] = len(raw) > byte_limit or result['bytesObserved'] > byte_limit
    raw = raw[:byte_limit]
    result['bytesInspected'] = len(raw)
    if not raw:
        result['status'] = 'empty'
        return result
    if not raw.endswith(b'\n'):
        result['truncated'] = True
        raw = raw.rsplit(b'\n', 1)[0] if b'\n' in raw else b''
    root_sid = None
    for index, line in enumerate(raw.splitlines()):
        if index >= event_limit:
            result['truncated'] = True
            break
        if len(line) > line_limit:
            result['oversizeLines'] += 1
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError('non-object event')
        except (ValueError, UnicodeError):
            result['malformedLines'] += 1
            continue
        result['eventsInspected'] += 1
        if row.get('event') == 'start' and root_sid is None:
            root_sid = row.get('sid')
        if row.get('event') == 'exit' and root_sid is not None and row.get('sid') == root_sid:
            result['rootExitObserved'] = True
        if row.get('event') == 'child_start':
            category = trace_child_category(row.get('argv'))
            counts = result['observedChildStarts']
            counts[category] = counts.get(category, 0) + 1
    complete = (not result['truncated'] and not result['malformedLines'] and
                not result['oversizeLines'] and result['rootExitObserved'])
    result['status'] = 'complete' if complete else 'partial'
    result['countsAreLowerBounds'] = not complete
    if complete:
        result['exactFetchChildStarts'] = result['observedChildStarts'].get('fetch', 0)
    return result


class GitPublisher:
    """Git subprocesses are cancellable; no working index or checkout writes."""
    def __init__(self, root, remote='origin', branch='main', command_timeout=60):
        self.root = pathlib.Path(root)
        self.repo = self.root.parent
        self.remote, self.branch = remote, branch
        self.command_timeout = command_timeout

    def run(self, args, cancel, env=None, data=None):
        started_at, started_clock = stamp(), time.monotonic()
        trace_directory = None
        trace_path = None
        def failure(result, returncode, stderr):
            diagnostic = command_diagnostic(args, started_at, time.monotonic()-started_clock,
                                            result, returncode, stderr)
            if trace_path is not None:
                try: diagnostic['trace2'] = summarize_trace2(trace_path)
                except Exception: diagnostic['trace2'] = {'protocol':'git-trace2-summary-v1', 'status':'unreadable', 'exactFetchChildStarts':None, 'countsAreLowerBounds':True}
            return GitCommandError('Checkpoint git ' + diagnostic['stage'] + ' ' + result +
                                   (' (exit ' + str(returncode) + ')' if returncode is not None else ''), diagnostic)
        if cancel.is_set():
            raise failure('cancelled', None, b'')
        command = ['git', '-c', 'core.sparseCheckout=false', '-c', 'index.sparse=false', *args]
        command_env = env
        if args and args[0] == 'write-tree':
            trace_directory = tempfile.TemporaryDirectory(prefix='sm-write-tree-trace-')
            trace_path = pathlib.Path(trace_directory.name) / 'trace.jsonl'
            command_env = {**os.environ, **(env or {}), 'GIT_TRACE2_EVENT':str(trace_path),
                           'GIT_TRACE2_CONFIG_PARAMS':'', 'GIT_TRACE2_ENV_VARS':''}
        try:
            process = subprocess.Popen(command, cwd=self.repo, env=command_env, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        except BaseException:
            if trace_directory is not None: trace_directory.cleanup()
            raise
        deadline = time.monotonic() + self.command_timeout
        try:
            first = True
            while True:
                try:
                    out, stderr = process.communicate(input=data if first else None, timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    first = False
                    if cancel.is_set() or time.monotonic() >= deadline:
                        result = 'cancelled' if cancel.is_set() else 'timed_out'
                        os.killpg(process.pid, signal.SIGKILL)
                        _, stderr = process.communicate()
                        raise failure(result, process.returncode, stderr)
            if process.returncode:
                raise failure('failed', process.returncode, stderr)
            return out.decode().strip()
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
            if trace_directory is not None:
                trace_directory.cleanup()

    def verify_frozen_blobs(self, expected, cancel):
        """Require every edited object locally; never fetch to satisfy this guard."""
        error = 'Frozen blob verification failed; no tree publication'
        if not expected or any(not re.fullmatch(r'[0-9a-f]{40}', oid) or size < 0
                               for oid, size in expected):
            raise RuntimeError(error)
        rows = self.run(['--no-lazy-fetch', 'cat-file',
                         '--batch-check=%(objectname) %(objecttype) %(objectsize)'], cancel,
                        data=('\n'.join(oid for oid, _ in expected) + '\n').encode()).splitlines()
        if len(rows) != len(expected):
            raise RuntimeError(error)
        for row, (oid, size) in zip(rows, expected):
            if row.split() != [oid, 'blob', str(size)]:
                raise RuntimeError(error)

    def __call__(self, snapshot, cancel):
        with tempfile.TemporaryDirectory(prefix='sm-checkpoint-') as directory:
            td = pathlib.Path(directory)
            files = {'stupid-money-lab/state.json': snapshot.state,
                     'stupid-money-lab/dashboard.json': snapshot.dashboard}
            frozen = []
            manifest = {'protocol': 'immutable-checkpoint-v1', 'observedGeneration': snapshot.generation,
                        'stateHash': hashlib.sha256(snapshot.state).hexdigest(),
                        'dashboardHash': hashlib.sha256(snapshot.dashboard).hexdigest(),
                        'rawPrefixes': {p.path: p.size for p in snapshot.prefixes},
                        'treeWritePolicy': 'remote-parent+verified-frozen-blobs-v1'}
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
            self.verify_frozen_blobs([(blob, path.stat().st_size)
                                     for (_, path), blob in zip(frozen, blobs)], cancel)
            index_info = ''.join('100644 ' + blob + '\t' + name + '\n'
                                 for (name, _), blob in zip(frozen, blobs)).encode()
            last_error = None
            attempt_diagnostics = []
            for attempt in range(2):
                # A killed Git command can leave its private index.lock behind.
                # Start each retry with a different isolated index; never remove
                # a working-checkout lock or reuse an interrupted index.
                env = {**os.environ, 'GIT_INDEX_FILE': str(td / ('index-' + str(attempt + 1)))}
                try:
                    self.run(['fetch', '--depth=1', self.remote, self.branch], cancel)
                    parent = self.run(['rev-parse', 'FETCH_HEAD'], cancel)
                    self.run(['read-tree', parent], cancel, env)
                    self.run(['update-index', '--index-info'], cancel, env, index_info)
                    # Unchanged entries come from the fetched parent. All edits
                    # were frozen, hashed and verified locally above.
                    tree = self.run(['write-tree', '--missing-ok'], cancel, env)
                    if tree == self.run(['rev-parse', parent + '^{tree}'], cancel):
                        return {'commit': parent, 'unchanged': True, 'attemptDiagnostics': attempt_diagnostics}
                    commit = self.run(['-c', 'user.name=Stupid Money research collector', '-c',
                                       'user.email=41898282+github-actions[bot]@users.noreply.github.com',
                                       'commit-tree', tree, '-p', parent, '-m',
                                       'Record immutable public paper checkpoint [skip ci]'], cancel, env)
                    self.run(['push', self.remote, commit + ':refs/heads/' + self.branch], cancel)
                    return {'commit': commit, 'unchanged': False, 'attemptDiagnostics': attempt_diagnostics}
                except Exception as error:
                    last_error = error
                    attempt_diagnostics.append({'attempt': attempt + 1, 'command': getattr(error, 'diagnostic',
                                                {'protocol':'git-command-diagnostic-v1', 'stage':'unknown', 'result':'exception'})})
                    if cancel.is_set():
                        break
            raise PublicationAttemptsError(last_error, attempt_diagnostics)


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
                if hasattr(error, 'attempt_diagnostics'):
                    receipt['attemptDiagnostics'] = error.attempt_diagnostics
                elif hasattr(error, 'diagnostic'):
                    receipt['commandDiagnostic'] = error.diagnostic
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
