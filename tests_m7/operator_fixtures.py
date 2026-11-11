"""Operator-only disposable sources and signed DATA providers; no real workers."""
import copy
from dataclasses import replace
import hashlib
import hmac
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from test_config import run, snapshot
from discovery_fixtures import discover, issue
from adp.config import Config
from adp.discovery_schema import digest
from adp.discovery_types import ReadinessReview
from adp.guard_types import data
from adp.operator_authority import remote_semantics
from adp.operator_controller import READ_PERMISSIONS, InstalledProject
from adp.operator_profile import load_profile, signed_subject
from adp.operator_providers import policy_semantics, assessment_policy, ProjectProviders
from adp.operator_authority import OperatorAuthority
from adp.policy_adapters import GitPolicyAdapter, MockRepositoryAdapter
from adp.policy_types import Operation, Permission, Effect, Rules, SourceClaim, SourceKind, Protection, Ref
from adp.project_validation_types import RequiredCheck, Phase
from adp.schema import encode
from adp.ticket_types import OriginalScope, Clause, Proposal, Part


class OperatorFixture(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='adp-operator-fixture-')
        self.addCleanup(self.temporary.cleanup)
        self.base=Path(self.temporary.name)
        self.now=int(time.time())
        self.rid=getattr(self,'repository_id','17')
        self.name=getattr(self,'project_name','demo/project')
        self.node='R_'+self.rid
        self.auth=self.base/'installed';self.auth.mkdir(mode=0o700)
        self.control=self.base/'control';self.control.mkdir()
        self.bare=self.base/'coordination.git';self.bare.mkdir()
        self.product=self.base/'product';self.product.mkdir()
        for root,args in ((self.bare,('--bare',)),(self.control,()),(self.product,())):
            run(root,'init','--initial-branch=trunk',*args)
            run(root,'config','user.name','Operator Fixture')
            run(root,'config','user.email','fixture@example.invalid')
        run(self.control,'remote','add','memory',str(self.bare))
        (self.product/'AGENTS.md').write_text('Product owns all checks. Only original ticket scope.\n')
        (self.product/'answer.py').write_text('answer = '+('41' if self.rid=='17' else '19')+'\n')
        run(self.product,'add','AGENTS.md','answer.py');run(self.product,'commit','-m','fixture: original')
        self.head=run(self.product,'rev-parse','HEAD')
        run(self.product,'checkout','-b','work/one')
        run(self.product,'remote','add','origin','https://github.com/'+self.name+'.git')
        self.keys={}; principals=[]
        roles={'operator':['operator'],'automation':['automation'],'policy':['project-policy'],
            'independent':['scope-reviewer'],'project':['project-check'],'issuer':['token-issuer']}
        for name,role in roles.items():
            secret=hashlib.sha256(('only-disposable-'+name).encode()).digest();self.keys[name]=secret
            path=self.auth/(name+'.key.json');self.write(path,{'schema_version':1,'key_hex':secret.hex()})
            principals.append({'id':name,'roles':role,'repositories':[self.rid],'key_file':str(path)})
        self.trust=self.auth/'trust.json';self.write(self.trust,{'schema_version':1,'principals':principals})
        self.profile_path=self.auth/'profile.json'
        self.body={'id':'delegation-one','repository_id':self.rid,'authority':'automation',
            'repository':{'name':self.name,'node_id':self.node,'database_id':int(self.rid),'remote':'origin'},
            'memory':{'repo':str(self.control),'remote':'memory','branch':'coordination/operator',
                'storage':str(self.base/'memory'),'private_state':str(self.base/'private'),'owner':'operator-fixture'},
            'window':{'id':'7'*64,'issued_at':self.now-1,'expires_at':self.now+300,'maximum_rounds':8,'maximum_tasks':1,'maximum_parallel':1},
            'delegation':{'issues':['issue-1'],'operations':[str(o) for o in (Operation.INSPECT,Operation.EDIT,Operation.STAGE,
                Operation.COMMIT,Operation.VALIDATE,Operation.PUSH,Operation.PR,Operation.MERGE,Operation.REPORT)],
                'branches':['refs/heads/work/one'],'merge_mode':'MANUAL','merge_methods':['merge'],
                'merge_envelope':'HEAD_ATOMIC_BASE_OBSERVED','ticket_envelope':None,'allow_setup':True,'allow_claim':True,'reviews':1},
            'providers':{k:str(self.auth/(k+'.json')) for k in ('policy','assessment','decisions','revocations')},
            'tasks':[{'issue_id':'issue-1','number':1,'task_id':'issue:one','slug':'one','workspace':str(self.product),'expected_revision':self.head}],
            'checks':[data(RequiredCheck('unit','project','fixture:project-owned',Phase.BEFORE_PR,1))]}
        self.body['providers'].update(validation={'kind':'signed','path':str(self.auth/'results.json'),'mode':'COMMITTED',
            'maximum_age':300,'result_maximum_age':300,'maximum_observations':8},
            decision_socket=None,
            credentials={k:str(self.auth/(k+'.credential.json')) for k in ('read','cas','forge','ticket')})
        self.sign_write('revocations',{'repository_id':self.rid,'sequence':0,'revoked':[]})
        self.write(self.auth/'decisions.json',{'schema_version':1,'decisions':[]})
        from adp.network_http import GitHubHTTPTransport
        from adp.github_product import GitHubForgeHTTPTransport
        from adp.ticket_publication import GitHubTicketHTTPTransport
        for name,permissions in (('read',READ_PERMISSIONS),('cas',GitHubHTTPTransport.permissions),
            ('forge',GitHubForgeHTTPTransport.permissions),('ticket',GitHubTicketHTTPTransport.permissions)):
            token={'token':'fixture-private-'+name,'installation_id':12,'repository_ids':[int(self.rid)],'repository_node_id':self.node,
                'permissions':[list(pair) for pair in permissions],'issued_at':self.now-1,'expires_at':self.now+300,
                'issuance_request':'fixture:actual-request','issuance_response':'fixture:actual-response','kind':'installation','evidence':None}
            request={'installation_id':12,'repository_ids':[int(self.rid)],'permissions':dict(permissions)}
            response={'token_sha256':hashlib.sha256(token['token'].encode()).hexdigest(),'repository_ids':[int(self.rid)],
                'repository_node_id':self.node,'permissions':dict(permissions),'issued_at':self.now-1,'expires_at':self.now+300}
            self.write(self.auth/(name+'.credential.json'),self.signed('credential',{'repository_id':self.rid,'token':token,
                'issuance_request':request,'issuance_response':response}))
        self.refresh_profile()
        cfg=self.profile.project_config(self.profile.tasks[0])
        self.adapter=GitPolicyAdapter(cfg,governance=('AGENTS.md',),fingerprint_worktree=True)
        self.refs=(Ref('refs/heads/trunk',self.head),Ref('refs/heads/work/one',self.head))
        with patch.object(GitPolicyAdapter,'_remote_refs',return_value=self.refs): self.policy_snapshot=self.adapter.inspect()
        self.rules=Rules(tuple(Permission(o,Effect.ALLOW) for o in Operation if o not in
            (Operation.FORCE_PUSH,Operation.REWRITE,Operation.REBASE,Operation.RELEASE,Operation.DEPLOY)),
            base_branch='trunk',branch_template='work/{slug}',subject_template='change: {summary}',body_template='',
            pr_title_template='{summary}',pr_draft=True,merge_method='merge',checks=('unit',),reviews=1)
        self.install_policy()
        self.snap,self.transport=discover([issue(1,name=self.name)],rid=self.rid,name=self.name)
        # The fixture API uses its actual opaque identity; explicitly enroll it.
        self.snap=replace(self.snap,repository=replace(self.snap.repository,memory_id=self.rid,checkout_ref='refs/heads/work/one',checkout_sha=self.head),
            observed_at=self.now)
        actual=self.snap.issues[0].identity.issue_id
        self.body['tasks'][0]['issue_id']=actual;self.body['delegation']['issues']=[actual];self.refresh_profile()
        self.install_assessment()
        self.casp=patch('adp.network_git.GitHubCAS.refs',return_value=self.refs);self.casmock=self.casp.start();self.addCleanup(self.casp.stop)
        # Native GET-only discovery remains actual adapter code; fake HTTP only.
        self.discp=patch('adp.operator_controller.DiscoveryHTTP',return_value=self.transport);self.discp.start();self.addCleanup(self.discp.stop)

    def write(self,path,body):
        path.write_bytes(encode(body,1048576));path.chmod(0o600)

    def signed(self,kind,payload,signer=None,*,issued=None,expires=None):
        signer=signer or {'profile':'operator','revocations':'operator','policy':'policy','assessment':'independent',
            'project-evidence':'project','credential':'issuer','decision':'independent','operator-decision':'operator',
            'scope-addition':'operator'}[kind]
        document={'schema_version':1,'kind':kind,'signer':signer,'issued_at':self.now-2 if issued is None else issued,
            'expires_at':self.now+300 if expires is None else expires,'payload':payload,'signature':''}
        document['signature']=hmac.new(self.keys[signer],('adp/operator/v1:'+signed_subject(document)).encode(),hashlib.sha256).hexdigest()
        return document

    def sign_write(self,kind,payload,**kwargs):
        path=self.profile_path if kind=='profile' else self.auth/(kind+'.json')
        self.write(path,self.signed(kind,payload,**kwargs))

    def refresh_profile(self):
        self.sign_write('profile',self.body)
        self.profile=load_profile(self.profile_path,self.trust,clock=lambda:self.now)

    def install_policy(self):
        source=SourceClaim(SourceKind.GOVERNANCE,'AGENTS.md',self.policy_snapshot.documents[0].digest,self.rules,self.now-1,self.now+300)
        protections=[Protection(r.name,r.revision,True,True,True,('unit',),1,('merge',),(),'fixture:project-protection',
            self.now-1,self.now+300,mergeable_methods=('merge',)) for r in self.refs]
        self.sign_write('policy',{'repository_id':self.rid,'document_inventory_digest':policy_semantics(self.policy_snapshot),
            'paths':{'governance':['AGENTS.md'],'profiles':[],'contracts':[]},'sources':[data(source)],'protections':[data(p) for p in protections]})

    def install_assessment(self):
        issue=self.snap.issues[0]
        readiness=ReadinessReview(issue.identity,'Correct the existing answer',('criterion:answer',),('AGENTS.md',),
            specification='KNOWN',policy='KNOWN',observed_at=self.now-1,expires_at=self.now+300)
        scope=data(OriginalScope(None,'Correct the existing answer',(Clause('goal','OBJECTIVE','Correct the existing answer'),
            Clause('accept','ACCEPTANCE','criterion:answer')),('answer.py',),('unit',),()))
        proposal=data(Proposal(None,issue.revision,None,(Part('one',('goal','accept')),),instructions=('Use prescribed project evidence',),
            exit_conditions=('Acceptance or finite stop',)))
        self.assessment={'repository_id':self.rid,'snapshot_digest':remote_semantics((self.snap,)),
            'tasks':[{'issue_id':issue.identity.issue_id,'original_issue_digest':digest(data(issue)),
                'policy_semantics':assessment_policy(ProjectProviders(self.profile,OperatorAuthority(self.profile)).policy(
                    MockRepositoryAdapter(self.policy_snapshot)).inspect_repository()),'scope':scope,'proposal':proposal,
                'readiness':data(readiness),'preparer':'project-preparer','dependency_edits':[]}]}
        self.sign_write('assessment',self.assessment)

    def installed(self,*,mutating=False):
        return InstalledProject(self.profile,mutating=mutating)

    def serve_decision(self, responder, invoke):
        """Exactly one disposable, finite signed-data provider exchange."""
        import socket
        import threading
        path=self.auth/'decision.sock'
        self.body['providers']['decision_socket']=str(path);self.refresh_profile()
        errors=[];observed=[]
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
            server.bind(str(path));path.chmod(0o600);server.listen(1);server.settimeout(2)
            def serve():
                try:
                    connection,_=server.accept()
                    with connection:
                        connection.settimeout(2);raw=bytearray()
                        while True:
                            block=connection.recv(65536)
                            if not block: break
                            raw.extend(block)
                            if len(raw)>1048576: raise ValueError('fixture bound')
                        challenge=json.loads(raw);observed.append(challenge)
                        connection.sendall(encode(responder(challenge),1048576))
                except Exception as exc: errors.append(type(exc).__name__)
            thread=threading.Thread(target=serve);thread.start()
            try: result=invoke()
            finally: thread.join(timeout=3);path.unlink()
        if thread.is_alive() or errors: raise AssertionError('Disposable provider did not finish: '+str(errors))
        return result,observed
