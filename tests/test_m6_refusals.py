"""Q11: unsupported network write capability refuses before any transport."""
from unittest.mock import patch

from adp.errors import ADPError
from adp.execution_ports import GitExecutionPort
from test_config import GitFixture,run,snapshot


class UnsupportedOperationQualification(GitFixture):
    def test_network_push_has_no_fallback_or_transport(self):
        config=self.config()
        run(self.a,'remote','set-url','upstream','https://github.com/fixture-do-not-contact/not-real')
        port=GitExecutionPort(config,local_remotes=(self.remote,))
        before=snapshot(self.base)
        with patch('adp.execution_ports.git') as mutation:
            with self.assertRaisesRegex(ADPError,'UNSUPPORTED_ATOMIC_REF'):port._remote()
        mutation.assert_not_called()
        self.assertEqual(snapshot(self.base),before)
