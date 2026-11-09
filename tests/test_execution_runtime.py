"""Adapter contract tests using an explicitly synthetic CLI, never real qualification."""
import json
import os
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from adp.codex_runtime import CodexExecRuntime, _group_alive, output_schema
from adp.discovery_schema import digest
from adp.errors import ADPError
from adp.execution_types import Role, RuntimeStatus, WorkerRequest, WorkerResult
from adp.storage import atomic
from adp.schema import encode


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="adp-runtime-contract-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "product"
        self.root.mkdir()
        self.command = self.base / "synthetic-codex"
        self.command.write_text("#!/usr/bin/env python3\nimport sys,json,time,os,subprocess\n"
            "if '--version' in sys.argv: print('synthetic-cli');sys.exit(0)\n"
            "if '--help' in sys.argv: print('--json --output-schema --ephemeral --ignore-user-config --sandbox');sys.exit(0)\n"
            "prompt=sys.stdin.read()\n"
            "if prompt=='startup-error': sys.exit(3)\n"
            "print(json.dumps({'type':'thread.started','thread_id':'independent:'+str(os.getpid())}),flush=True)\n"
            "if prompt=='timeout':\n subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);time.sleep(60)\n"
            "if prompt in ('detached','detached-complete'):\n child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n root=sys.argv[sys.argv.index('-C')+1]\n open(os.path.join(root,'child.pid'),'w').write(str(child.pid))\n if prompt=='detached':time.sleep(60)\n"
            "result={'outcome':'PASS','approved':False,'criteria':[],'summary':'Synthetic contract observation','forensic':None}\n"
            "print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':json.dumps(result)}}),flush=True)\n"
            "print(json.dumps({'type':'turn.completed'}),flush=True)\n")
        self.command.chmod(0o700)
        self.runtime = CodexExecRuntime(self.base / "runtime", executable=str(self.command))

    def request(self, text="normal", seconds=5):
        return WorkerRequest(digest(text), "opaque", 1, Role.DEVELOPER, "a"*40, str(self.root), text, seconds)

    def test_supported_cli_fresh_contexts_and_duplicate_request(self):
        contexts = []
        for text in ("normal", "other"):
            request = self.request(text)
            self.assertEqual(self.runtime.dispatch(request).status, RuntimeStatus.RUNNING)
            result = self.runtime.wait(request.id)
            self.assertEqual(result.status, RuntimeStatus.COMPLETED)
            self.assertEqual(result.request_digest, digest(request))
            contexts.append(result.context_id)
            self.assertEqual(self.runtime.dispatch(request), result)
        self.assertEqual(len(set(contexts)), 2)
        with self.assertRaises(ADPError):
            self.runtime.dispatch(replace(self.request(), prompt="changed"))

    def test_startup_failure_is_unsupported_not_success(self):
        request = self.request("startup-error")
        self.runtime.dispatch(request)
        self.assertEqual(self.runtime.wait(request.id).status, RuntimeStatus.UNSUPPORTED_RUNTIME)

    def test_timeout_observes_entire_group_stop(self):
        request = self.request("timeout", 1)
        self.runtime.dispatch(request)
        record = self.runtime._read(request.id)
        result = self.runtime.wait(request.id)
        self.assertEqual(result.status, RuntimeStatus.TIMEOUT)
        self.assertFalse(_group_alive(record["pid"]))

    def test_restart_observes_pending_launch_unknown_never_redispatches(self):
        request = self.request()
        record = {"host":self.runtime.host,"request_digest":digest(request),"status":"STARTING","pid":None,
                  "start_time":None,"context":None,"result":None,"elapsed":0}
        self.runtime.directory.mkdir()
        atomic(self.runtime._path(request.id), encode(record))
        self.assertEqual(self.runtime.dispatch(request).status, RuntimeStatus.UNKNOWN)

    def test_expired_deadline_and_coordination_are_not_launched(self):
        for request in (replace(self.request(), deadline=int(time.time())-1), replace(self.request(), role=Role.COORDINATION)):
            with self.assertRaises(ADPError):
                self.runtime.dispatch(request)
        self.assertFalse(self.runtime.directory.exists())

    def test_missing_runtime_fails_capability_check(self):
        runtime = CodexExecRuntime(self.base / "absent", executable=str(self.base / "missing"))
        self.assertFalse(runtime.capabilities().independent_contexts)
        self.assertEqual(runtime.dispatch(self.request()).status, RuntimeStatus.UNSUPPORTED_RUNTIME)

    def test_worker_output_schema_is_closed(self):
        schema = output_schema(WorkerResult)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(schema["properties"]))

    def test_detached_descendant_is_reaped_before_timeout_claim(self):
        request=self.request('detached',1)
        self.runtime.dispatch(request)
        result=self.runtime.wait(request.id)
        self.assertEqual(result.status,RuntimeStatus.TIMEOUT)
        self.assertIs(result.stopped,True)
        child=int((self.root/'child.pid').read_text())
        self.assertFalse(Path('/proc',str(child)).exists())

    def test_detached_descendant_is_reaped_before_completed_result(self):
        request=self.request('detached-complete',5)
        self.runtime.dispatch(request)
        result=self.runtime.wait(request.id)
        self.assertEqual(result.status,RuntimeStatus.COMPLETED)
        self.assertIs(result.stopped,True)
        child=int((self.root/'child.pid').read_text())
        self.assertFalse(Path('/proc',str(child)).exists())

    def test_failed_running_receipt_write_kills_launched_process(self):
        from unittest.mock import patch
        from adp.errors import ADPError
        original=self.runtime._save
        launched=[]
        def save(rid,record):
            if record['status']==RuntimeStatus.RUNNING:
                launched.append(record['pid'])
                raise OSError('synthetic receipt durability failure')
            return original(rid,record)
        with patch.object(self.runtime,'_save',side_effect=save):
            with self.assertRaises(OSError): self.runtime.dispatch(self.request('timeout',5))
        self.assertEqual(len(launched),1)
        self.assertFalse(_group_alive(launched[0]))
        self.assertEqual(self.runtime.observe(self.request('timeout',5).id).status,RuntimeStatus.UNKNOWN)
