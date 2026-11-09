"""Pure filter-domain and fixture regressions; not OS qualification evidence."""
import struct
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adp.validation_launcher import seccomp_program
from sandbox_fixtures import runtime_image


def decision(number, *arguments):
    data = struct.pack('iI7Q', number, 0xc000003e, 0, *arguments, *([0] * (6 - len(arguments))))
    rows = tuple(struct.iter_unpack('HBBI', seccomp_program()))
    pointer, accumulator = 0, 0
    for _ in range(4096):
        operation, yes, no, operand = rows[pointer]
        if operation == 0x20:
            accumulator = struct.unpack_from('I', data, operand)[0]
        elif operation in (0x15, 0x35, 0x45):
            condition = (accumulator == operand if operation == 0x15 else
                         accumulator >= operand if operation == 0x35 else bool(accumulator & operand))
            pointer += yes if condition else no
        elif operation == 0x06:
            return operand
        else:
            raise AssertionError('Unexpected filter operation')
        pointer += 1
    raise AssertionError('Filter did not terminate')


class ValidationProfileTests(unittest.TestCase):
    def test_shared_mappings_and_mutating_advice_are_killed(self):
        kill, allow = 0x80000000, 0x7fff0000
        for flags in (1, 3, 0, 7):
            with self.subTest(flags=flags):
                self.assertEqual(decision(9, 0, 4096, 3, flags, 3, 0), kill)
        for advice in (9, 100, 101, 9999):
            with self.subTest(advice=advice):
                self.assertEqual(decision(28, 0, 4096, advice), kill)
        self.assertEqual(decision(9, 0, 4096, 3, 0x22, 0xffffffffffffffff, 0), allow)
        self.assertEqual(decision(9, 0, 4096, 1, 2, 3, 0), allow)
        self.assertEqual(decision(28, 0, 4096, 4), allow)
        self.assertEqual(decision(452), kill)
        self.assertEqual(decision(9999), kill)

    def test_runtime_fixture_excludes_static_compilation_archives(self):
        with tempfile.TemporaryDirectory(prefix='adp-m7b-image-unit-') as temporary:
            base = Path(temporary)
            stdlib = base / 'python3.12'
            build = stdlib / 'config-3.12-platform'
            build.mkdir(parents=True)
            (build / 'libpython3.12.a').write_bytes(b'compilation-only fixture')
            (stdlib / 'runtime.py').write_text('runtime = True\n')
            executable = base / 'trusted-python'
            executable.write_bytes(b'owned non-executed runtime fixture')
            with patch('sandbox_fixtures.sys.executable', str(executable)), \
                 patch('sandbox_fixtures.sysconfig.get_path', return_value=str(stdlib)), \
                 patch('sandbox_fixtures.subprocess.run', return_value=SimpleNamespace(stdout='')):
                image = runtime_image(base / 'image')
            self.assertTrue((image / 'runtime/lib/python3.12/runtime.py').is_file())
            self.assertFalse((image / 'runtime/lib/python3.12/config-3.12-platform').exists())
