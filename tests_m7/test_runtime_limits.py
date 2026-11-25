"""Focused resource-policy consumption on disposable data; no real GitHub/Worker."""
from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adp.errors import ADPError
from adp.network_git import GitHubCAS, GitHubTarget
from adp.network_http import Response
from adp.runtime_limits import (DEFAULTS, LEGACY, PARAMETERS, RuntimeLimits, RuntimeSettings,
    bind_consent, current_budget, load_runtime_limits, network_operation, operation_scope,
    request_allowance, work_span, consent_scope)


class Clock:
    def __init__(self): self.now = 1000.0
    def __call__(self): return self.now
    def advance(self, seconds): self.now += seconds


class Transport:
    def __init__(self, settings=None, action=None):
        self.runtime_settings = settings or RuntimeSettings()
        self.calls, self.action = [], action
    def bind_repository(self, node, database): pass
    def request(self, method, path, body, *, seconds):
        self.calls.append(seconds)
        if self.action: self.action(seconds)
        return Response(200, b'{"actual":"fixture"}')


def service(settings=None, action=None):
    transport = Transport(settings, action)
    target = GitHubTarget("disposable", "R_disposable", 17, "owned", "disposable", "work/task")
    return GitHubCAS(target, transport)


class RuntimeLimitsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "runtime.json"

    def write(self, data):
        self.path.write_text(json.dumps(data)); self.path.chmod(0o600)
        return self.path

    def test_all_minimum_default_and_maximum_values_are_loaded(self):
        for name, spec in PARAMETERS.items():
            for value in (spec.minimum, spec.default, spec.maximum):
                with self.subTest(name=name, value=value):
                    result = load_runtime_limits(self.write({name: value}))
                    self.assertEqual(result.limits.values(), {**DEFAULTS.values(), name: value})
                    self.assertEqual(result.diagnostics, ())
        self.assertEqual(len(PARAMETERS), 3)

    def test_individual_invalid_values_fall_back_without_losing_valid_parameters(self):
        for name, spec in PARAMETERS.items():
            for bad in (spec.minimum - 1, spec.maximum + 1, None, True, False,
                        str(spec.default), "1e1", "10 seconds", float(spec.default), [], {}):
                values = {key: p.maximum for key, p in PARAMETERS.items()}; values[name] = bad
                with self.subTest(name=name, value=bad):
                    result = load_runtime_limits(self.write(values))
                    self.assertEqual(result.limits.values(), {**values, name: spec.default})
                    event, = result.diagnostics
                    self.assertEqual((event.parameter, event.rejected, event.fallback), (name, repr(bad), spec.default))
                    self.assertTrue(event.reason)
        with self.assertRaises(ValueError): RuntimeLimits(request_limit=True)

    def test_missing_and_structurally_invalid_files_use_all_defaults(self):
        result = load_runtime_limits(self.path)
        self.assertEqual(result.limits, DEFAULTS)
        self.assertEqual(result.diagnostics[0].kind, "MISSING_FILE")
        for raw in ('{', 'null', '[]', '{"request_limit":64,"typo":1}',
                    '{"request_limit":64,"request_limit":128}', '{"request_limit":NaN}'):
            self.path.write_text(raw); self.path.chmod(0o600)
            with self.subTest(raw=raw):
                result = load_runtime_limits(self.path)
                self.assertEqual(result.limits, DEFAULTS)
                self.assertEqual(result.diagnostics[0].kind, "CONFIGURATION_FAILURE")
                self.assertTrue(result.diagnostics[0].error)

    def test_unreadable_unsafe_and_unexpected_loading_errors_are_diagnostic_defaults(self):
        self.write({"request_limit":64})
        for error in (PermissionError(13, "fixture unreadable"), OSError(5, "fixture I/O"), RuntimeError("fixture loader")):
            with self.subTest(error=type(error).__name__), patch("adp.config.load_json", side_effect=error):
                result = load_runtime_limits(self.path)
                self.assertEqual(result.limits, DEFAULTS)
                self.assertEqual(result.diagnostics[0].error_type, type(error).__name__)
                self.assertIn(str(error), result.diagnostics[0].error)
        self.path.chmod(0o644)
        self.assertEqual(load_runtime_limits(self.path).diagnostics[0].kind, "CONFIGURATION_FAILURE")
        self.path.unlink(); self.path.symlink_to(self.root / "other")
        self.assertEqual(load_runtime_limits(self.path).diagnostics[0].kind, "CONFIGURATION_FAILURE")
        import builtins
        original=builtins.__import__
        def unavailable(name,*a,**k):
            if name=="pwd": raise ImportError("fixture account resolver unavailable")
            return original(name,*a,**k)
        with patch.dict(os.environ,{},clear=True),patch("builtins.__import__",side_effect=unavailable):
            result=load_runtime_limits()
        self.assertEqual(result.limits,DEFAULTS)
        self.assertEqual(result.diagnostics[0].error_type,"ImportError")
        self.path.unlink()  # Remove the deliberately unsafe symlink.
        directory = self.root / "adp-codex"; directory.mkdir()
        selected = directory / "runtime-limits.json"
        selected.write_text('{"request_limit":64}'); selected.chmod(0o600)
        with patch.dict(os.environ,{"XDG_CONFIG_HOME":str(self.root)},clear=True),patch("builtins.__import__",side_effect=unavailable):
            result=load_runtime_limits()
        self.assertEqual(result.limits.request_limit,64)
        self.assertEqual(result.diagnostics,())

    def test_selection_precedence_and_immutable_client_lifetime(self):
        directory = self.root / "adp-codex"; directory.mkdir()
        implicit = directory / "runtime-limits.json"
        implicit.write_text('{"request_limit":64}'); implicit.chmod(0o600)
        explicit = self.write({"request_limit":256})
        with patch.dict(os.environ, {"XDG_CONFIG_HOME":str(self.root)}, clear=True):
            self.assertEqual(load_runtime_limits().limits.request_limit, 64)
            with patch.dict(os.environ, {"ADP_RUNTIME_LIMITS_FILE":str(explicit)}):
                self.assertEqual(load_runtime_limits().limits.request_limit, 256)
                self.assertEqual(load_runtime_limits(implicit).limits.request_limit, 64)
                one = load_runtime_limits(); client = service(one)
                self.write({"request_limit":128})
                self.assertIs(client.runtime_settings, one)
                self.assertEqual(client.limits.request_limit, 256)
                self.assertEqual(load_runtime_limits().limits.request_limit, 128)
                with self.assertRaises(FrozenInstanceError): one.limits.request_limit = 64

    def test_loading_failure_never_suppresses_product_errors_or_cancellation(self):
        with patch("adp.config.load_json", side_effect=RuntimeError("config")):
            client = service(load_runtime_limits(self.path))
        error = ValueError("unrelated product")
        class Product:
            service = client
            @network_operation("fixture.product")
            def run(self): raise error
        with self.assertRaises(ValueError) as raised: Product().run()
        self.assertIs(raised.exception, error)
        self.assertIsNone(current_budget())
        with patch("adp.config.load_json", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): load_runtime_limits(self.path)
        with self.assertRaises(KeyboardInterrupt):
            with client.bounded(): raise KeyboardInterrupt()
        self.assertIsNone(current_budget())

    def test_request_timeout_boundaries_reach_the_actual_transport(self):
        for seconds in (3, 10, 30):
            settings = load_runtime_limits(self.write({"request_timeout_seconds":seconds}))
            client = service(settings)
            clock = Clock()
            with self.subTest(seconds=seconds), patch("time.monotonic", clock):
                self.assertEqual(client.request("GET", "/fixture")["actual"], "fixture")
                self.assertEqual(client.transport.calls, [seconds])
                self.assertEqual(client.measurements[-1]["transport_calls"], 1)

    def test_operation_deadlines_and_short_remainders_are_never_renewed(self):
        for seconds in (40, 120, 300):
            settings = load_runtime_limits(self.write({"operation_timeout_seconds":seconds}))
            one, two, clock = service(settings), service(settings), Clock()
            with self.subTest(seconds=seconds), patch("time.monotonic", clock):
                with self.assertRaisesRegex(ADPError, "fixed budget"):
                    with one.bounded() as original:
                        end = original.end
                        clock.advance(seconds - .5)
                        with two.bounded() as nested:
                            self.assertIs(nested, original); self.assertEqual(nested.end, end)
                            two.request("GET", "/fixture")
                            self.assertEqual(two.transport.calls, [.5])
                        clock.advance(.5)
                        one.request("GET", "/refused")
                self.assertEqual(one.transport.calls, [])
                self.assertIsNone(current_budget())
                self.assertIsNone(one._budget.get())

    def test_request_count_boundaries_stop_actual_transport_calls(self):
        for maximum in (64, 128, 256):
            settings = load_runtime_limits(self.write({"request_limit":maximum}))
            client = service(settings)
            with self.subTest(maximum=maximum), self.assertRaisesRegex(ADPError, "fixed budget"):
                with client.bounded():
                    for _ in range(maximum + 1): client.request("GET", "/fixture")
            self.assertEqual(len(client.transport.calls), maximum)
            self.assertEqual(client.measurements[-1]["request_attempts"], maximum + 1)

    def test_late_response_cannot_be_returned_as_success_or_retried(self):
        clock = Clock(); client = service(action=lambda seconds: clock.advance(seconds))
        with patch("time.monotonic", clock):
            with self.assertRaisesRegex(ADPError, "request exhausted"):
                client.request("GET", "/fixture")
        self.assertEqual(len(client.transport.calls), 1)
        self.assertFalse(client.unconfirmed_contexts())  # Actual response/stop returned.
        self.assertEqual(client.measurements[-1]["outcome"], "ERROR")
        # A valid decode may itself use the remaining request allowance. Preserve
        # its timeout cause instead of misclassifying it as malformed JSON.
        from adp.schema import decode
        clock, client = Clock(), service()
        def late_decode(*args):
            result = decode(*args)
            clock.advance(DEFAULTS.request_timeout_seconds)
            return result
        with patch("time.monotonic", clock), patch("adp.network_git.decode", side_effect=late_decode):
            with self.assertRaisesRegex(ADPError, "request exhausted"):
                client.request("GET", "/fixture")
        self.assertEqual(len(client.transport.calls), 1)
        self.assertFalse(client.unconfirmed_contexts())

    def test_cancelled_transport_preserves_unknown_stop_and_original_exception(self):
        error = KeyboardInterrupt()
        def cancel(_): raise error
        client = service(action=cancel)
        with self.assertRaises(KeyboardInterrupt) as raised: client.request("GET", "/fixture")
        self.assertIs(raised.exception, error)
        self.assertTrue(client.unconfirmed_contexts())
        with self.assertRaises(ADPError): client.request("GET", "/never-retried")
        self.assertEqual(len(client.transport.calls), 1)
        self.assertIsNone(current_budget())

    def test_legacy_consent_and_shorter_config_only_reduce_existing_allowances(self):
        clock, client = Clock(), service()
        with patch("time.monotonic", clock), client.bounded() as budget:
            bind_consent({"expires_at":2000}, 1000)
            self.assertEqual((budget.end, budget.request_seconds, budget.maximum_calls),
                             (clock.now + LEGACY.operation_timeout_seconds, LEGACY.request_timeout_seconds, LEGACY.request_limit))
            bind_consent({"runtime_limits":DEFAULTS.values(), "expires_at":2000}, 1000)
            self.assertEqual(budget.end, clock.now + LEGACY.operation_timeout_seconds)
            with self.assertRaises(ADPError): bind_consent({"runtime_limits":None,"expires_at":2000}, 1000)

    def test_cost_accounting_is_private_bounded_and_does_not_double_count_execution(self):
        clock = Clock(); client = service(action=lambda _: clock.advance(.25))
        with patch("time.monotonic", clock), client.bounded(name="fixture.operation"):
            with work_span("fixture.repeated"):
                clock.advance(2)
                with work_span("fixture.child", execution=True):
                    with work_span("fixture.nested", execution=True): clock.advance(3)
            client.request("GET", "/private-must-not-be-recorded")
        measured = client.measurements[-1]
        self.assertEqual((measured["wall_seconds"], measured["substantive_execution_seconds"], measured["orchestration_seconds"]), (5.25,3,2.25))
        self.assertEqual(measured["request_latencies_seconds"], (.25,))
        self.assertEqual(measured["work"]["fixture.repeated"]["calls"], 1)
        self.assertNotIn("private-must-not", json.dumps(measured))
        self.assertNotIn("rejected", json.dumps(measured))
        self.assertEqual(client.measurements.maxlen, 64)

    def test_derived_allowances_keep_the_hard_ceiling_without_applying_config_minimum(self):
        for seconds in (.01, 3, 10, 30): self.assertEqual(request_allowance(seconds), seconds)
        for seconds in (0, -1, 31, True, None, "10", float("nan"), float("inf")):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError): request_allowance(seconds)

    def test_actual_personal_transport_does_not_restart_deadline_after_authorization(self):
        from adp.personal_network import PersonalGitHubTransport
        from adp.network_http import NetworkTransportError
        client = service(); transport = PersonalGitHubTransport(client.target)
        transport.bind_repository(client.target.node_id, client.target.database_id)
        clock = Clock()
        def slow(): clock.advance(2); return True
        transport.authorize_write = slow
        with patch("time.monotonic", clock), patch("adp.personal_network._supported", return_value=True), \
                patch.object(transport,"_credential") as credential, patch("adp.personal_network.supervised_output") as child:
            with self.assertRaises(NetworkTransportError):
                transport.request("POST", client.target.api + "/git/blobs", {"content":"YQ==","encoding":"base64"}, seconds=1)
            credential.assert_not_called(); child.assert_not_called()

    def test_read_only_http_ports_consume_the_same_effective_request_profile(self):
        from adp.discovery_github import GitHubHTTPTransport
        from adp.personal_github import PersonalGitHubRead
        from adp.project_validation_github import GitHubValidationHTTP
        from adp.execution_github import GitHubMutationTransport
        class Reply:
            code = 200; headers = {}
            def __enter__(self): return self
            def __exit__(self,*a): pass
            def read(self,_): return b'{}'
        settings = load_runtime_limits(self.write({"request_timeout_seconds":3}))
        for cls in (GitHubHTTPTransport,PersonalGitHubRead,GitHubValidationHTTP,GitHubMutationTransport):
            client = cls("synthetic-not-a-credential",runtime_settings=settings)
            with self.subTest(cls=cls.__name__), patch.object(client._opener,"open",return_value=Reply()) as observed:
                if cls is GitHubMutationTransport: client.request("GET","/repos/owned/disposable")
                elif cls is GitHubValidationHTTP: client.get("/repos/owned/disposable",seconds=30)
                elif cls is PersonalGitHubRead: client.get("/user")
                else: client.get("/repos/owned/disposable")
                self.assertGreater(observed.call_args.kwargs["timeout"],0)
                self.assertLessEqual(observed.call_args.kwargs["timeout"],3)

    def test_cli_read_clients_share_one_configuration_load(self):
        from adp.personal_cli import _read_transports
        from adp.config import load_json
        self.write({"request_limit":64})
        with patch.dict(os.environ,{"ADP_RUNTIME_LIMITS_FILE":str(self.path)}), \
                patch("adp.config.load_json",wraps=load_json) as loads:
            discovery, validation = _read_transports("synthetic-not-a-credential")
            self.assertIs(discovery.runtime_settings,validation.runtime_settings)
            self.assertEqual(loads.call_count,1)

    def test_concurrent_operation_contexts_do_not_share_counters(self):
        import threading
        barrier = threading.Barrier(2); records = []; errors = []
        def lane():
            try:
                client = service()
                with client.bounded() as budget:
                    barrier.wait(timeout=5)
                    client.request("GET","/fixture")
                    records.append((id(budget),budget.calls))
            except BaseException as exc: errors.append(exc)
        workers = [threading.Thread(target=lane) for _ in range(2)]
        for worker in workers: worker.start()
        for worker in workers: worker.join(timeout=10)
        self.assertFalse(errors); self.assertTrue(all(not w.is_alive() for w in workers))
        self.assertEqual(len(records),2); self.assertNotEqual(records[0][0],records[1][0])
        self.assertEqual([v for _,v in records],[1,1])

    def test_tighter_project_read_profile_persists_without_extending_aggregate_budget(self):
        from adp.personal_product_http import PersonalProjectRead
        clock=Clock(); outer_client=service(RuntimeSettings(RuntimeLimits(30,300,256)))
        inner=service(RuntimeSettings(RuntimeLimits(3,40,64)))
        def observed(_): inner.transport.last_response=(200,b'{"actual":"fixture"}',())
        inner.transport.action=observed
        with patch("time.monotonic",clock),outer_client.bounded() as outer:
            self.assertEqual(PersonalProjectRead(inner).get("/repos/owned/disposable",seconds=.1).status,200)
            self.assertEqual((outer.request_seconds,outer.maximum_calls,outer.end),(3,64,clock.now+40))
            self.assertEqual(outer.calls,1)
            def shorter(_):
                observed(None)
                bind_consent({"runtime_limits":DEFAULTS.values(),"expires_at":1002},1000)
            inner.transport.action=shorter
            PersonalProjectRead(inner).get("/repos/owned/disposable",seconds=.1)
            self.assertEqual((outer.request_seconds,outer.maximum_calls,outer.end),(3,64,clock.now+2))

    def test_resource_caps_do_not_start_a_worker_timer_or_leak_to_later_operations(self):
        clock=Clock(); client=service(RuntimeSettings(RuntimeLimits(30,300,256)))
        with patch("time.monotonic",clock):
            with consent_scope({}):
                self.assertIsNone(current_budget())
                clock.advance(600)  # No Worker is executed; unrelated lifetime is not charged.
                with client.bounded() as budget:
                    self.assertEqual((budget.request_seconds,budget.maximum_calls,budget.end),(5,128,clock.now+45))
                    client.request("GET","/fixture")
            with client.bounded() as independent:
                self.assertEqual((independent.request_seconds,independent.maximum_calls,independent.end),(30,256,clock.now+300))

    def test_standalone_upload_has_one_operation_budget_for_all_objects(self):
        clock=Clock(); client=service(RuntimeSettings(RuntimeLimits(10,40,64)))
        def native(method,path,body,*,seconds):
            client.transport.calls.append(seconds); clock.advance(9)
            return Response(200,b'{"sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}')
        client.transport.request=native
        objects=[SimpleNamespace(kind="blob",oid="a"*40,payload={"fixture":True}) for _ in range(5)]
        with patch("time.monotonic",clock),self.assertRaises(ADPError): client.upload(objects)
        self.assertEqual(len(client.transport.calls),5)
        self.assertEqual(client.transport.calls[-1],4)
        self.assertEqual(len(client.measurements),1)

    def test_standalone_legacy_forge_observation_cannot_renew_its_budget_per_request(self):
        from adp.execution_github import GitHubMutationTransport,GitHubForgeBackend
        from adp.policy_types import Operation
        clock=Clock(); settings=RuntimeSettings(RuntimeLimits(10,40,64))
        transport=GitHubMutationTransport("synthetic",runtime_settings=settings)
        key="a"*64; body="Product\n\n"+GitHubForgeBackend.marker(key)
        item={"body":body,"number":10,"html_url":"https://github.com/owned/disposable/pull/10"}
        detail={**item,"title":"Product","draft":True,
            "head":{"sha":"b"*40,"ref":"work/task","repo":{"id":17,"full_name":"owned/disposable"}},
            "base":{"ref":"trunk","repo":{"id":17,"full_name":"owned/disposable"}}}
        replies=[{"id":17,"full_name":"owned/disposable"},[{}]*100,[{}]*100,[item],detail]
        class Reply:
            code=200;headers={}
            def __init__(self,payload):self.payload=payload
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,_):return json.dumps(self.payload).encode()
        def respond(*a,**k):
            clock.advance(9);return Reply(replies.pop(0))
        forge=GitHubForgeBackend("owned/disposable","17",transport,None)
        payload={"body":"Product","revision":"b"*40,"title":"Product","draft":True,
                 "base_ref":"refs/heads/trunk","head_ref":"refs/heads/work/task"}
        with patch("time.monotonic",clock),patch.object(transport._opener,"open",side_effect=respond) as requests:
            with self.assertRaises(ADPError): forge.observe(key,Operation.PR,payload)
        self.assertEqual(requests.call_count,5)
        self.assertEqual(requests.call_args.kwargs["timeout"],4)
        self.assertEqual(forge.runtime_measurements[-1]["transport_calls"],5)
        self.assertEqual(forge.runtime_measurements[-1]["wall_seconds"],45)
