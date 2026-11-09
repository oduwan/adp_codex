"""No network calls: strict product-report replay and exact PR observations."""
import copy
import unittest

from adp.discovery_github import Response
from adp.discovery_schema import digest
from adp.errors import ADPError
from adp.execution_github import GitHubForgeBackend
from adp.policy_types import Operation
from execution_fixtures import FixtureAuthority


class Transport:
    def __init__(self):
        self.calls, self.items, self.detail = [], [], None
        self.status, self.lost = 200, False
        self.pages = None

    def request(self, method, path, payload=None):
        self.calls.append((method,path,payload))
        if path == '/repos/demo/project':
            return Response(self.status, {'id':17,'full_name':'demo/project'})
        if method == 'POST':
            self.items.append({'body':payload['body'],'html_url':'https://github.com/demo/project/issues/1#issuecomment-7'})
            return Response(0 if self.lost else 201, None)
        if path.endswith('/pulls/1'):
            return Response(self.status, self.detail)
        page = int(path.rsplit('page=',1)[1])
        return Response(self.status, (self.pages.get(page, []) if self.pages is not None else self.items))


class GitHubExecutionTests(unittest.TestCase):
    def setUp(self):
        self.transport, self.authority = Transport(), FixtureAuthority()
        self.forge = GitHubForgeBackend('demo/project','17',self.transport,self.authority)
        self.key = 'a'*64
        self.payload = {'body':'A completed product result','revision':'b'*40,'target':'https://github.com/demo/project/issues/1'}

    def submit(self):
        plan = 'c'*64
        auth = self.authority.grant(purpose='execution/effect', subject=digest({'id':self.key,'plan':plan,'payload':self.payload}))
        return self.forge.submit(self.key, Operation.REPORT, self.payload, authorization=auth, plan_digest=plan)

    def test_credentials_are_not_execution_authority(self):
        with self.assertRaises(ADPError):
            self.forge.submit(self.key, Operation.REPORT, self.payload)
        self.assertEqual(self.transport.calls, [])

    def test_lost_post_response_is_reconciled_by_exact_marker_body(self):
        self.transport.lost = True
        self.assertEqual(self.submit().status, 'PRESENT')
        self.assertEqual(self.forge.observe(self.key, Operation.REPORT,self.payload,attempted=True).status,'PRESENT')
        self.assertEqual(sum(c[0]=='POST' for c in self.transport.calls),1)

    def test_absence_after_attempt_is_unknown(self):
        self.assertEqual(self.forge.observe(self.key,Operation.REPORT,self.payload).status,'ABSENT')
        self.assertEqual(self.forge.observe(self.key,Operation.REPORT,self.payload,attempted=True).status,'UNKNOWN')

    def test_permission_failure_and_changed_body_remain_unknown(self):
        self.transport.status=403
        self.assertEqual(self.forge.observe(self.key,Operation.REPORT,self.payload).status,'UNKNOWN')
        self.transport.status=200
        self.submit()
        changed={**self.payload,'body':'changed result'}
        self.assertEqual(self.forge.observe(self.key,Operation.REPORT,changed).status,'UNKNOWN')

    def test_duplicate_markers_on_later_page_are_unknown(self):
        self.submit()
        item = self.transport.items[0]
        self.transport.pages = {1:[item]+[{'body':''} for _ in range(99)],2:[item]}
        self.assertEqual(self.forge.observe(self.key,Operation.REPORT,self.payload).status,'UNKNOWN')

    def test_report_cannot_escape_repository(self):
        with self.assertRaises(ADPError):
            self.forge.observe(self.key,Operation.REPORT,{**self.payload,'target':'https://github.com/elsewhere/repo/issues/1'})

    def test_pr_head_draft_and_repository_identity_are_exact(self):
        payload={'body':'product','revision':'b'*40,'title':'Product result','draft':True,
                 'head_ref':'refs/heads/work/one','base_ref':'refs/heads/trunk'}
        repo={'id':17,'full_name':'demo/project'}
        body=payload['body']+'\n\n'+self.forge.marker(self.key)
        self.transport.items=[{'number':1,'body':body,'html_url':'https://github.com/demo/project/pull/1'}]
        detail={'body':body,'title':payload['title'],'draft':True,
                'head':{'sha':payload['revision'],'ref':'work/one','repo':repo},'base':{'ref':'trunk','repo':repo}}
        self.transport.detail=detail
        self.assertEqual(self.forge.observe(self.key,Operation.PR,payload).status,'PRESENT')
        for field, value in [('sha','d'*40),('repo',{'id':18,'full_name':'demo/project'})]:
            changed=copy.deepcopy(detail);changed['head'][field]=value
            self.transport.detail=changed
            self.assertEqual(self.forge.observe(self.key,Operation.PR,payload).status,'UNKNOWN')
        self.transport.detail={**detail,'draft':False}
        self.assertEqual(self.forge.observe(self.key,Operation.PR,payload).status,'UNKNOWN')
