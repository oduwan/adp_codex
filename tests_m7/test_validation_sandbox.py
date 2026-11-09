"""Real OS boundary tests; unavailable hosts are SKIP, never qualified PASS."""
import fcntl
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch

from adp.errors import ADPError
from adp.execution_ports import SubprocessValidation, UnconfirmedValidation
from adp.execution_types import CheckCommand
from adp.guard_types import Outcome
from adp.validation_sandbox import BubblewrapValidation, UnsafeValidation, UnsupportedValidation, image_digest
from sandbox_fixtures import git, policy, project, runtime_image


def receipt(denominator=1, outcome='PASS', quarantined=0):
    return json.dumps({'denominator': denominator, 'counts': {v: denominator if v == outcome else 0 for v in Outcome}, 'quarantined': quarantined})


def command(name, source, denominator=1, seconds=2):
    return CheckCommand(name, ('/runtime/bin/python', '-I', '-B', '-c', source), seconds, denominator)


class ValidationSandboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image_temp = tempfile.TemporaryDirectory(prefix='adp-m7b-image-')
        cls.image = runtime_image(Path(cls.image_temp.name) / 'image')
        cls.policy = policy(cls.image)

    @classmethod
    def tearDownClass(cls):
        cls.image_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='adp-m7b-project-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'source'
        self.sha = project(self.root)
        self.private = self.base / 'private'
        self.private.mkdir()
        (self.private / 'synthetic-credential').write_text('owned synthetic host-only fixture')
        self.commands = (command('unit', 'print(' + repr(receipt()) + ')'),)
        self.port = self.make_port(self.commands)

    def make_port(self, commands, **changes):
        return BubblewrapValidation(tuple(commands), policy=changes.get('policy', self.policy),
                                    protected_roots=(self.private,), receipts=self.base / changes.get('name', 'receipts'))

    def supported(self, *, fresh=False):
        capability = self.port.capabilities(fresh=fresh)
        if not capability.supported:
            self.skipTest(capability.reason)
        self.assertTrue(capability.evidence.startswith('sandbox:'))

    def run_port(self, port=None, *, seconds=20):
        port = port or self.port
        return port.run(self.root, self.sha, tuple(c.name for c in port.commands), seconds=seconds)

    def test_bare_prefix_cannot_claim_production_isolation(self):
        with self.assertRaisesRegex(ADPError, 'UNSUPPORTED_VALIDATION_RUNTIME'):
            SubprocessValidation(self.commands, sandbox_prefix=('/bin/true',)).run(self.root, self.sha, ('unit',), seconds=2)

    def test_invalid_runtime_hash_refuses_before_any_product_launch(self):
        from dataclasses import replace
        with self.assertRaisesRegex(ADPError, 'Pinned validation runtime changed'):
            self.make_port(self.commands, policy=replace(self.policy, image_digest='0' * 64))
        self.assertNotEqual(self.port.policy_digest(), self.make_port(self.commands,
            policy=replace(self.policy, memory_bytes=128 * 1024 * 1024), name='different-policy').policy_digest())
        import os
        alias = self.image / 'outside-hardlink'
        os.link(self.private / 'synthetic-credential', alias)
        try:
            with self.assertRaisesRegex(ADPError, 'hard links'):
                image_digest(self.image)
        finally:
            alias.unlink()

    def test_unsupported_runtime_never_runs_the_product_command(self):
        bad = policy(self.image, binary=Path('/usr/bin/false'))
        port = self.make_port(self.commands, policy=bad)
        with self.assertRaises(UnsupportedValidation):
            self.run_port(port)

    def test_probe_stop_loss_is_not_downgraded_to_unsupported(self):
        with patch.object(self.port, '_execute', side_effect=UnconfirmedValidation('fixture:probe-stop-lost', str(self.port.receipts))):
            with self.assertRaises(UnconfirmedValidation):
                self.port.capabilities(fresh=True)

    def test_actual_readonly_network_process_capability_probes(self):
        self.supported(fresh=True)
        self.assertEqual(self.run_port()[0].outcome, Outcome.PASS)
        source = ('import resource\n'
                  'assert resource.getrlimit(resource.RLIMIT_AS)==(268435456,268435456)\n'
                  'assert resource.getrlimit(resource.RLIMIT_CPU)==(2,2)\n'
                  'assert resource.getrlimit(resource.RLIMIT_NOFILE)==(64,64)\n'
                  'assert resource.getrlimit(resource.RLIMIT_FSIZE)==(0,0)\n'
                  'assert resource.getrlimit(resource.RLIMIT_CORE)==(0,0)\n'
                  'print(' + repr(receipt()) + ')')
        bounded = self.make_port((command('actual-limits', source),), name='actual-limits')
        self.assertEqual(self.run_port(bounded)[0].outcome, Outcome.PASS)
        proofs = [json.loads(p.read_text()) for p in self.port.receipts.glob('receipt-*.json')]
        self.assertTrue(any(p['stop']['cli_exit'] in (-signal.SIGSYS, 128 + signal.SIGSYS) for p in proofs))
        self.assertTrue(all(p['stop']['stopped'] is True for p in proofs))

    def test_two_project_matrices_keep_independent_original_denominators(self):
        self.supported()
        first = self.make_port((command('first', 'print(' + repr(receipt(2)) + ')', 2),), name='matrix-one')
        second = self.make_port((command('negative', 'print(' + repr(receipt(3, 'FAIL')) + ')', 3),
                                 command('later', 'print(' + repr(receipt(1)) + ')')), name='matrix-two')
        self.assertEqual([(r.denominator, r.outcome) for r in self.run_port(first)], [(2, Outcome.PASS)])
        self.assertEqual([(r.denominator, r.outcome) for r in self.run_port(second)], [(3, Outcome.FAIL), (1, Outcome.PASS)])

    def test_writes_and_exit_zero_cannot_hide_containment_attempts(self):
        self.supported()
        before = git(self.root, 'show-ref')
        for index, path in enumerate(('/work/tracked', '/work/untracked', '/work/.git/config', '/runtime/bin/python', str(self.private / 'synthetic-credential'))):
            source = "from pathlib import Path\ntry:Path(" + repr(path) + ").write_text('unsafe')\nexcept OSError:pass\nprint(" + repr(receipt()) + ')'
            port = self.make_port((command('attack', source), self.commands[0]), name='write-' + str(index))
            with self.subTest(path=path), self.assertRaises(UnsafeValidation) as caught:
                self.run_port(port)
            self.assertEqual([r.outcome for r in caught.exception.results], [Outcome.UNKNOWN, Outcome.NOTRUN])
        self.assertEqual(git(self.root, 'show-ref'), before)
        self.assertEqual((self.root / 'tracked').read_text(), 'original')
        self.assertFalse((self.root / 'untracked').exists())

    def test_host_credentials_temp_and_controller_paths_are_absent(self):
        self.supported()
        source = 'from pathlib import Path\n'
        for path in (self.private / 'synthetic-credential', Path(__file__).resolve(), self.base / 'host-temp'):
            source += 'assert not Path(' + repr(str(path)) + ').exists()\n'
        injection = "; $(touch /work/injection); ' & deploy"
        source += 'import sys\nassert sys.argv[1]==' + repr(injection) + '\nprint(' + repr(receipt()) + ')'
        explicit = command('privacy', source)
        from dataclasses import replace
        port = self.make_port((replace(explicit, argv=explicit.argv + (injection,)),), name='privacy')
        self.assertEqual(self.run_port(port)[0].outcome, Outcome.PASS)
        self.assertFalse((self.root / 'injection').exists())

    def test_network_and_fork_double_fork_setsid_are_terminal_refusals(self):
        self.supported()
        attacks = ('import socket;socket.create_connection(("127.0.0.1",9),1)',
                   'import os;os.fork()', 'import os;os.fork();os.fork()', 'import os;os.setsid()')
        for index, source in enumerate(attacks):
            port = self.make_port((command('attack', source), self.commands[0]), name='process-' + str(index))
            with self.subTest(source=source), self.assertRaises(UnsafeValidation) as caught:
                self.run_port(port)
            self.assertEqual([r.outcome for r in caught.exception.results], [Outcome.UNKNOWN, Outcome.NOTRUN])

    def test_modern_mutators_and_read_descriptor_writes_are_terminal(self):
        self.supported()
        attacks = ['import ctypes;ctypes.CDLL(None).syscall(' + str(number) + ",-100,b'/work/tracked',0,0,0,0)" for number in (452, 463, 466, 469, 9999)]
        attacks += ["import os;fd=os.open('/work/tracked',os.O_RDONLY)\ntry:os.write(fd,b'unsafe')\nexcept OSError:pass"]
        for index, source in enumerate(attacks):
            source += '\nprint(' + repr(receipt()) + ')'
            port = self.make_port((command('modern', source), self.commands[0]), name='modern-' + str(index))
            with self.subTest(index=index), self.assertRaises(UnsafeValidation) as caught:
                self.run_port(port)
            self.assertEqual([r.outcome for r in caught.exception.results], [Outcome.UNKNOWN, Outcome.NOTRUN])

    def test_symlinks_hardlinks_traversal_and_git_filters_refuse(self):
        alias = self.base / 'source-alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ADPError, 'Symlinked paths'):
            self.port.run(alias, self.sha, ('unit',), seconds=5)
        (self.root / 'escape').symlink_to(self.private / 'synthetic-credential')
        with self.assertRaisesRegex(ADPError, 'Outside source symlink'):
            self.run_port()
        (self.root / 'escape').unlink()
        import os
        os.link(self.private / 'synthetic-credential', self.root / 'hardlink')
        with self.assertRaisesRegex(ADPError, 'hard links'):
            self.run_port()
        (self.root / 'hardlink').unlink()
        git(self.root, 'config', 'filter.malicious.smudge', 'touch ../outside')
        with self.assertRaisesRegex(ADPError, 'UNSUPPORTED_GIT_FILTER'):
            self.run_port()

    def test_timeout_reaps_before_continuing_the_finite_inventory(self):
        self.supported()
        port = self.make_port((command('timeout', 'import time;time.sleep(20)', 2, 1), self.commands[0]), name='timeout')
        results = self.run_port(port)
        self.assertEqual([(r.denominator, r.outcome) for r in results], [(2, Outcome.TIMEOUT), (1, Outcome.PASS)])
        self.assertTrue(all(json.loads(p.read_text())['stop']['stopped'] for p in port.receipts.glob('receipt-*.json')))

    def test_every_nonpass_quarantine_and_invalid_result_stays_nonpass(self):
        self.supported()
        cases = [receipt(2, outcome) for outcome in Outcome if outcome != Outcome.PASS]
        cases += [receipt(2, quarantined=1), receipt(1), '{"denominator":2}']
        for index, payload in enumerate(cases):
            port = self.make_port((command('unit', 'print(' + repr(payload) + ')', 2),), name='accounting-' + str(index))
            with self.subTest(index=index):
                result = self.run_port(port)[0]
                self.assertNotEqual(result.outcome, Outcome.PASS)
                self.assertEqual(result.denominator, 2)
                self.assertEqual(sum(c.count for c in result.counts), 2)

    def test_output_exhaustion_is_terminal_and_source_head_drift_refuses(self):
        self.supported()
        port = self.make_port((command('flood', 'print("x" * 100000)'), self.commands[0]), name='output')
        with self.assertRaises(UnsafeValidation) as caught:
            self.run_port(port)
        self.assertEqual([r.outcome for r in caught.exception.results], [Outcome.UNKNOWN, Outcome.NOTRUN])
        from dataclasses import replace
        bounds = replace(self.policy, cpu_seconds=1)
        for index, source in enumerate(('x=bytearray(2 * 1024 * 1024 * 1024)',
                                        'while True:pass',
                                        "files=[open('/work/tracked','rb') for _ in range(200)]")):
            limited = self.make_port((command('resource', source, seconds=2), self.commands[0]),
                                     name='resource-' + str(index), policy=bounds)
            results = self.run_port(limited)
            self.assertNotEqual(results[0].outcome, Outcome.PASS)
            self.assertEqual(results[1].outcome, Outcome.PASS)
        with self.assertRaisesRegex(ADPError, 'source revision drifted'):
            self.port.run(self.root, '0' * 40, ('unit',), seconds=5)

    def test_restart_and_already_running_never_blindly_execute(self):
        from adp.validation_sandbox import digest
        state = self.port.receipts / (digest(str(self.root)) + '.json')
        state.write_text(json.dumps({'status': 'RUNNING', 'subject': 'interrupted'}))
        with patch.object(self.port, '_execute') as launch, self.assertRaises(UnconfirmedValidation):
            self.run_port()
        launch.assert_not_called()
        state.unlink()
        lock_path = self.port.receipts / (digest(str(self.root)) + '.lock')
        with open(lock_path, 'a+b') as locked:
            fcntl.flock(locked, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(self.port, '_execute') as launch, self.assertRaises(UnconfirmedValidation):
                self.run_port()
            launch.assert_not_called()

    def test_missing_stop_receipt_stops_remaining_inventory(self):
        self.supported()
        port = self.make_port((self.commands[0], command('later', 'raise AssertionError("must not run")')), name='lost-stop')
        original = port.capabilities
        capability = original()
        with patch.object(port, 'capabilities', return_value=capability), patch('adp.validation_sandbox.validation_stopped', side_effect=UnconfirmedValidation('fixture:lost-stop', str(port.receipts))):
            with self.assertRaises(UnconfirmedValidation) as caught:
                self.run_port(port)
        self.assertEqual([r.outcome for r in caught.exception.results], [Outcome.UNKNOWN, Outcome.NOTRUN])
        self.assertTrue((port.receipts / 'active.json').exists())
        with self.assertRaises(UnconfirmedValidation):
            port.capabilities()
        import os
        import threading
        import time
        import subprocess
        other = self.base / 'independent-interruption'
        other.mkdir()
        other_root = other / 'source'
        other_sha = project(other_root)
        other_private = other / 'protected'
        other_private.mkdir()
        live = BubblewrapValidation((command('interrupted', "print('owned-start',flush=True);import time;time.sleep(20)", seconds=3),
                                     command('never', 'raise AssertionError("must not run")')),
                                    policy=self.policy, protected_roots=(other_private,), receipts=other / 'receipts')
        observed, timers = [], []
        original_popen = subprocess.Popen
        def snapshot(pid):
            pending, rows = [pid], []
            while pending:
                parent = pending.pop()
                try:
                    children = Path('/proc', str(parent), 'task', str(parent), 'children').read_text().split()
                except OSError:
                    children = []
                for child in children:
                    try:
                        parts = Path('/proc', child, 'stat').read_text().rsplit(')', 1)[1].split()
                        rows.append((int(child), parts[19]));pending.append(int(child))
                    except OSError:
                        pass
            return rows
        def launch(argv, *args, **kwargs):
            process = original_popen(argv, *args, **kwargs)
            if any('owned-start' in str(part) for part in argv):
                def interrupt():
                    time.sleep(0.2)
                    observed.extend(snapshot(process.pid))
                    try:os.kill(process.pid, signal.SIGKILL)
                    except ProcessLookupError:pass
                timer = threading.Thread(target=interrupt);timer.start();timers.append(timer)
            return process
        try:
            with patch('adp.validation_sandbox.subprocess.Popen', side_effect=launch), self.assertRaises(UnconfirmedValidation) as caught:
                live.run(other_root, other_sha, tuple(c.name for c in live.commands), seconds=20)
            self.assertEqual([r.outcome for r in caught.exception.results], [Outcome.UNKNOWN, Outcome.NOTRUN])
            self.assertTrue((live.receipts / 'active.json').exists())
        finally:
            for timer in timers:timer.join(timeout=3)
            # Cleanup only start-time-bound descendants of this owned supervisor.
            for pid, started in observed:
                try:
                    parts = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
                    if parts[19] == started and parts[0] != 'Z':os.kill(pid, signal.SIGKILL)
                except (OSError, ProcessLookupError):pass

    def test_capability_cache_is_fresh_bounded_and_cannot_hide_uncertainty(self):
        self.supported(fresh=True)
        known = self.port.capabilities()
        with patch.object(self.port, '_probe', side_effect=AssertionError('cached success must avoid a duplicate probe')):
            self.assertEqual(self.port.capabilities(), known)
        from dataclasses import replace
        unsupported = replace(known, supported=False, reason='fixture:unqualified')
        with patch.object(self.port, '_host_key', return_value='different-host-context'), patch.object(self.port, '_probe', return_value=unsupported) as probe:
            self.assertFalse(self.port.capabilities().supported)
            probe.assert_called_once()
        with patch('adp.validation_sandbox.time.monotonic', wraps=__import__('time').monotonic) as now:
            baseline = __import__('time').monotonic()
            now.side_effect = lambda: baseline + 301
            with patch.object(self.port, '_probe', return_value=unsupported) as probe:
                self.assertFalse(self.port.capabilities().supported)
                probe.assert_called_once()
        original = self.image / 'runtime/bin/python'
        raw = original.read_bytes()
        try:
            original.write_bytes(raw + b'changed')
            with self.assertRaisesRegex(ADPError, 'Pinned validation runtime changed'):
                self.port.capabilities()
        finally:
            original.write_bytes(raw)
        (self.port.receipts / 'active.json').write_text('{"status":"RUNNING"}')
        with self.assertRaises(UnconfirmedValidation):
            self.port.capabilities()

