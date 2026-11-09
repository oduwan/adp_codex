"""Explicit v2→v3 migration keeps accepted state and recovers its journal."""
from unittest.mock import patch

from adp.errors import ADPError, AuthorityError, GitError
from adp.execution_memory import ExecutionJournal
from adp.guard import ProgressGuard
from adp.guard_types import Requirement
from test_config import snapshot
from test_guard import SyntheticAuthority
from test_memory import MemoryFixture


class ExecutionMemoryTests(MemoryFixture):
    def test_upgrade_is_explicit_idempotent_and_preserves_accepted_records(self):
        self.initialize()
        envelope=self.envelope();self.memory.deliver(envelope);self.memory.accept(envelope['assignment_id'])
        self.memory.upgrade_guard(authorized=True)
        authority=SyntheticAuthority()
        guard=ProgressGuard(self.memory,authority=authority,clock=lambda:100)
        spec=Requirement('contract','gate',('criterion',))
        guard.register('issue:alpha/../Ω',spec,authority.attest(guard.admission_subject('issue:alpha/../Ω',spec),'admission'))
        before=self.memory.inspect()
        with self.assertRaises(AuthorityError): ExecutionJournal(self.memory).upgrade()
        changed=ExecutionJournal(self.memory).upgrade(authorized=True)
        self.assertEqual(changed['state']['schema_version'],3)
        self.assertEqual(changed['tasks'],before['tasks'])
        for field in ('owner','generation','assignment_sequence','progress_guard','task_keys','repository_id'):
            self.assertEqual(changed['state'][field],before['state'][field])
        filesystem=snapshot(self.base)
        self.memory.inspect();ExecutionJournal(self.memory).upgrade(authorized=True)
        self.assertEqual(snapshot(self.base),filesystem)
        self.assertEqual(self.memory.inspect()['state'],changed['state'])

    def test_interrupted_migration_recovers_v3_without_claiming_foreign_owner(self):
        self.initialize();self.memory.upgrade_guard(authorized=True)
        self.other.initialize(authorized=True)
        with patch.object(self.memory,'_push',side_effect=GitError('synthetic lost migration push')):
            with self.assertRaises(GitError): ExecutionJournal(self.memory).upgrade(authorized=True)
        self.assertEqual(self.other.inspect()['state']['schema_version'],2)
        self.memory.recover();self.other.recover()
        self.assertEqual(self.other.inspect()['state']['schema_version'],3)
        self.assertFalse(self.other.inspect()['local_owner'])
        with self.assertRaises(ADPError): ExecutionJournal(self.other).upgrade(authorized=True)
