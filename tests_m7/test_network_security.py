"""Additional independently requested negative proofs; original33 stay frozen."""
import tempfile
import unittest
from pathlib import Path

from adp.errors import ADPError
from adp.network_git import GitHubCAS, GitHubTarget, GitHubGitExecutionPort
from adp.network_objects import closure
from network_fixtures import ObjectServer, git_bytes, gv


class NetworkSecurityQualification(unittest.TestCase):
    def fixture(self):
        # Import the module, not its TestCase into this module's discovery scope.
        import test_network_git
        case = test_network_git.NetworkExecutionQualification(methodName="runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    def prepared(self):
        case = self.fixture(); case.prepare()
        ticket = case.port.prepare_dispatch(case.action_id, case.action)
        case.conductor.journal.change(lambda execution, state, tasks: execution["actions"][case.action_id].update(status="SUBMITTED"))
        provider, plan, auth = case.policy()
        return case, ticket, provider, plan, auth

    def test_private_claim_corruption_refuses_before_any_object_upload(self):
        f, ticket, provider, plan, auth = self.prepared()
        before = f.server.refs()
        f.port._claim_path(f.action_id).write_text('{}')
        with self.assertRaises(ADPError): f.port.submit(f.action, provider, plan, auth, dispatch=ticket)
        self.assertFalse(f.server.mutations)
        self.assertEqual(f.server.refs(), before)

    def test_symlinked_private_claim_never_follows_an_outside_file(self):
        f, ticket, provider, plan, auth = self.prepared()
        path = f.port._claim_path(f.action_id)
        outside = f.base / 'private-unrelated'; outside.write_bytes(b'unchanged outside fixture')
        path.unlink(); path.symlink_to(outside)
        with self.assertRaises(ADPError): f.port.submit(f.action, provider, plan, auth, dispatch=ticket)
        self.assertEqual(outside.read_bytes(), b'unchanged outside fixture')
        self.assertFalse(f.server.mutations)

    def test_actual_owner_credential_loss_during_upload_prevents_cas(self):
        f, ticket, provider, plan, auth = self.prepared()
        before = f.server.refs()
        f.server.after_upload = lambda: (f.memory.control / 'owner.json').unlink()
        with self.assertRaises(ADPError): f.port.submit(f.action, provider, plan, auth, dispatch=ticket)
        self.assertFalse(f.memory.inspect()['local_owner'])
        self.assertFalse(any(kind == 'ref' for kind, _ in f.server.mutations))
        self.assertEqual(f.server.refs(), before)

    def test_verified_policy_revocation_during_upload_prevents_cas(self):
        f, ticket, provider, plan, auth = self.prepared()
        before = f.server.refs()
        evidence = provider.sources[0].evidence
        f.server.after_upload = lambda: f.authority.receipts.remove((evidence, 'policy/operator'))
        with self.assertRaises(ADPError): f.port.submit(f.action, provider, plan, auth, dispatch=ticket)
        self.assertFalse(any(kind == 'ref' for kind, _ in f.server.mutations))
        self.assertEqual(f.server.refs(), before)

    def test_diverged_target_refuses_fresh_policy_and_server_force_false(self):
        f = self.fixture(); f.prepare()
        sibling = git_bytes(f.root, 'commit-tree', gv(f.root, 'rev-parse', 'HEAD^{tree}'), '-p', f.initial,
            '-F', '-', raw=b'Concurrent independent sibling\n').decode().strip()
        gv(f.product_remote, 'fetch', '--no-tags', '--no-write-fetch-head', '--no-auto-maintenance', str(f.root), sibling)
        gv(f.product_remote, 'update-ref', f.target.ref, sibling, f.initial)
        before = f.server.refs()
        with self.assertRaises(ADPError): f.submit()
        self.assertEqual(f.server.refs(), before)
        self.assertFalse(f.server.mutations)
        # Independently prove the fake provider also honors force=false.
        f.service.upload(closure(f.root, f.new, f.service.known_commit))
        with self.assertRaises(ADPError): f.service.cas(sibling, f.new, 'a' * 64)
        self.assertEqual(f.server.refs(), before)

    def test_reused_repository_path_is_denied_by_selected_id_before_object_write(self):
        with tempfile.TemporaryDirectory(prefix='adp-network-repo-scope-') as directory:
            base = Path(directory)
            source, original, replacement = (base / name for name in ('source', 'repository-a', 'repository-b'))
            for path in (source, original, replacement):
                path.mkdir(); gv(path, 'init', '--bare' if path != source else '--initial-branch=topic')
            (source / 'private-product-fixture').write_text('synthetic private bounded source\n')
            gv(source, 'add', '.'); gv(source, 'commit', '-m', 'Canonical scoped fixture')
            head = gv(source, 'rev-parse', 'HEAD')
            target = GitHubTarget('opaque-scope', 'NODE_A', 123, 'owned-disposable', 'reused-name', 'topic')
            server = ObjectServer(original, target)
            client = GitHubCAS(target, server)
            self.assertIsNone(client.inspect_ref(writable=True))
            objects = closure(source, head, client.known_commit)
            def reuse():
                server.route_database_id, server.route_root = 456, replacement
            server.before_object = reuse
            with self.assertRaises(OSError): client.upload(objects)
            self.assertEqual(server.refs(), {})
            self.assertEqual(gv(replacement, 'for-each-ref'), '')
            self.assertEqual(list((replacement / 'objects').glob('[0-9a-f][0-9a-f]/*')), [])
            self.assertFalse(server.mutations)

    def test_broad_or_wrong_repository_transport_binding_fails_before_requests(self):
        with tempfile.TemporaryDirectory(prefix='adp-network-scope-negative-') as directory:
            root = Path(directory); gv(root, 'init', '--bare')
            target = GitHubTarget('opaque-scope', 'NODE_A', 123, 'owned-disposable', 'fixture', 'topic')
            server = ObjectServer(root, target); server.scope_ids = (123, 456)
            with self.assertRaises(ADPError): GitHubCAS(target, server)
            self.assertFalse(server.calls)

    def test_changed_remote_endpoint_or_memory_identity_refuses_before_http(self):
        from dataclasses import replace
        f = self.fixture()
        before = list(f.server.calls)
        for endpoint in ('ssh://git@github.com/owned-disposable/fixture',
                         'https://github.com/owned-disposable/another-repository',
                         'https://fixture-secret@github.com/owned-disposable/fixture'):
            with self.subTest(endpoint=endpoint):
                gv(f.root, 'remote', 'set-url', 'team', endpoint)
                with self.assertRaises(ADPError):
                    GitHubGitExecutionPort(f.cfg, f.service, f.conductor.journal)
                self.assertEqual(f.server.calls, before)
        gv(f.root, 'remote', 'set-url', 'team', f.target.endpoint + '.git')
        with self.assertRaises(ADPError):
            GitHubGitExecutionPort(replace(f.cfg, identity='different-opaque-repository'), f.service, f.conductor.journal)
        self.assertEqual(f.server.calls, before)
        self.assertFalse(f.server.mutations)

    def test_unreadable_network_hazard_preserves_unknown_and_cancels_real_worker(self):
        import subprocess
        import sys
        from types import SimpleNamespace
        from adp.execution_types import RuntimeStatus
        f = self.fixture()
        outside = f.base / 'unrelated-hazard'; outside.write_bytes(b'outside remains unchanged')
        f.service._hazard_path().symlink_to(outside)
        with self.assertRaises(ADPError): f.port.unconfirmed_contexts()
        process = subprocess.Popen((sys.executable, '-I', '-B', '-c', 'import time; time.sleep(30)'),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={})
        calls = []
        def cancel(request_id):
            calls.append(request_id)
            process.terminate(); process.wait(timeout=3)
            return SimpleNamespace(status=RuntimeStatus.CANCELLED, stopped=True)
        f.conductor.runtime = SimpleNamespace(observe=lambda _: SimpleNamespace(status=RuntimeStatus.RUNNING), cancel=cancel)
        f.conductor._launched = {'owned-disposable-worker'}
        try:
            unknown = f.conductor._quiesce(())
            self.assertEqual(calls, ['owned-disposable-worker'])
            self.assertIsNotNone(process.poll())
            self.assertEqual(len(unknown), 1)
            self.assertTrue(unknown[0].startswith('git:'))
            self.assertEqual(unknown, f.conductor._quiesce(()))
            self.assertEqual(outside.read_bytes(), b'outside remains unchanged')
        finally:
            if process.poll() is None:
                process.terminate(); process.wait(timeout=3)
