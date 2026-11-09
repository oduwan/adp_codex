"""Deterministic stop/deadline fault injection, not an OS qualification claim."""
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adp.execution_ports import UnconfirmedValidation
from adp.execution_types import CheckCommand
from adp.guard_types import Outcome
from adp.validation_sandbox import BubblewrapValidation, UnsafeValidation, _private


class ValidationLifecycleTests(unittest.TestCase):
    def exercise(self, stop, expected):
        with tempfile.TemporaryDirectory(prefix='adp-m7b-deadline-unit-') as temporary:
            base = Path(temporary)
            port = object.__new__(BubblewrapValidation)
            port.receipts = _private(base / 'receipts')
            port.policy = SimpleNamespace(output_bytes=4096)
            port.commands = tuple(CheckCommand(name, ('/runtime/bin/python',), 2, 1) for name in ('first', 'later'))
            port._validate_policy = lambda: None
            port._source = lambda *args: ('source', 'admin')
            port._host_key = lambda: 'isolated-deadline-unit-' + temporary
            port.policy_digest = lambda: 'owned-fixture-policy'
            port.capabilities = lambda **kwargs: SimpleNamespace(supported=True)
            port._argv = lambda *args: ('owned-nonexecuted-fixture',)
            launches = []

            @contextmanager
            def supervisor(*args):
                yield ('owned-nonexecuted-supervisor',), base / 'stop.json', 'owned-subject'

            def process(*args, **kwargs):
                streams = []
                for _ in range(2):
                    read, write = os.pipe()
                    os.close(write)
                    streams.append(os.fdopen(read, 'rb'))
                launches.append(True)
                return SimpleNamespace(stdout=streams[0], stderr=streams[1], pid=123,
                    poll=lambda: 0, wait=lambda **kwargs: 0)

            observed = {'side_effect': stop} if isinstance(stop, BaseException) else {'return_value': stop}
            with patch('adp.validation_sandbox.supervised_validation', supervisor), \
                 patch('adp.validation_sandbox.subprocess.Popen', side_effect=process), \
                 patch('adp.validation_sandbox.validation_stopped', **observed), \
                 patch('adp.validation_sandbox.selectors.DefaultSelector.select',
                       side_effect=subprocess.TimeoutExpired(('owned-fixture',), 2)):
                if expected is not None:
                    with self.assertRaises(expected) as caught:
                        port.run(base / 'source', 'a' * 40, ('first', 'later'), seconds=20)
                    self.assertEqual([row.outcome for row in caught.exception.results], [Outcome.UNKNOWN, Outcome.NOTRUN])
                    self.assertEqual(len(launches), 1)
                else:
                    rows = port.run(base / 'source', 'a' * 40, ('first', 'later'), seconds=20)
                    self.assertEqual([row.outcome for row in rows], [Outcome.TIMEOUT, Outcome.TIMEOUT])
                    self.assertEqual(len(launches), 2)
            self.assertEqual((port.receipts / 'active.json').exists(), expected is UnconfirmedValidation)

    def test_confirmed_terminal_stop_wins_over_read_deadline(self):
        for status, code in (('EXITED', 159), ('TIMEOUT', 159), ('CANCELLED', -15), ('UNKNOWN', 0)):
            with self.subTest(status=status, code=code):
                self.exercise({'stopped': True, 'status': status, 'cli_exit': code}, UnsafeValidation)

    def test_normal_deadline_and_unknown_stop_keep_honest_outcomes(self):
        for status in ('EXITED', 'TIMEOUT'):
            with self.subTest(status=status):
                self.exercise({'stopped': True, 'status': status, 'cli_exit': -15}, None)
        self.exercise(UnconfirmedValidation('owned:unknown', '/tmp/owned-fixture'), UnconfirmedValidation)
