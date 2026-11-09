"""Explicit controller selection cannot import untrusted project code."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from adp.cli import parser
from adp.errors import ADPError, AuthorityError
from adp.execution_cli import load_controller, run


class ExecutionCLITests(unittest.TestCase):
    def test_execution_authority_is_checked_before_loading_operator_code(self):
        for command in ('run','resume','handoff'):
            with self.subTest(command=command):
                with self.assertRaises(AuthorityError): run(SimpleNamespace(command=command,authorize_execution=False))

    def test_controller_in_target_or_memory_is_never_imported(self):
        with tempfile.TemporaryDirectory(prefix='adp-controller-contract-') as directory:
            base=Path(directory)
            config=SimpleNamespace(root=base/'product',storage=base/'memory')
            for root in (config.root,config.storage):
                root.mkdir()
                marker=base/'executed'
                module=root/'controller.py'
                module.write_text('from pathlib import Path\nPath('+repr(str(marker))+').touch()\n')
                with self.assertRaises(ADPError): load_controller(module,config)
                self.assertFalse(marker.exists())

    def test_parser_exposes_finite_commands_and_explicit_migration(self):
        for command in ('run','resume'):
            args=parser().parse_args([command,'--controller','/operator/controller.py','--authorize-execution','--rounds','2'])
            self.assertTrue(args.authorize_execution)
            self.assertEqual(args.rounds,2)
        args=parser().parse_args(['execution-upgrade','--authorize-memory-write'])
        self.assertTrue(args.authorize_memory_write)
