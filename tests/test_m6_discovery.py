"""Q03: one realistic graph plus a separately incomplete repository inventory."""
import unittest
from dataclasses import replace

from adp.discovery import DependencyPlanner
from adp.discovery_github import Response
from adp.discovery_types import Status
from discovery_fixtures import Authority,assessed,discover,issue,pull


class DiscoveryQualificationTests(unittest.TestCase):
    def test_mixed_graph_pagination_partial_metadata_and_stale_pr_are_honest(self):
        rows=[issue(1,state='closed'),issue(2),issue(3,body='Superseded by #2'),issue(4),issue(5),issue(6),issue(7),issue(8)]
        pr=pull()
        source={**issue(10),'node_id':pr['node_id'],'pull_request':{'url':pr['url']}}
        changes={f'/repos/alpha/product/issues/{n}/dependencies/blocked_by?per_page=2&page=1':Response(200,[issue(dep,state='closed' if dep==1 else 'open')]) for n,dep in ((2,1),(4,5),(5,4))}
        changes['/repos/alpha/product/issues/6/timeline?per_page=2&page=1']=Response(200,[{'id':'event','event':'cross-referenced','source':{'issue':source}}])
        snapshot,transport=discover(rows,prs=[pr],changed=changes,per_page=2)
        authority=Authority();reviews=list(assessed(snapshot,authority))
        for index,update in ((0,{'completed':True}),(2,{'duplicate_of':snapshot.issues[1].identity}),
                             (5,{'active_prs':(snapshot.pulls[0].identity,)}),(7,{'policy':'UNKNOWN'})):
            reviews[index]=authority.sign((snapshot,),replace(reviews[index],evidence=None,**update))
        reviews.pop(6)  # No independent specification exists; never invent one.
        planner=DependencyPlanner(authority=authority,clock=lambda:100)
        track=planner.plan((snapshot,),reviews=tuple(reviews))
        by_number={c.issue.number:c.status for c in track.candidates}
        self.assertEqual(by_number,{1:Status.DONE,2:Status.READY,3:Status.BLOCKED_DEPENDENCY,4:Status.BLOCKED_DEPENDENCY,
                                  5:Status.BLOCKED_DEPENDENCY,6:Status.IN_PROGRESS,7:Status.NEEDS_SPEC,8:Status.BLOCKED_OPERATOR})
        self.assertEqual(len(track.cycles),1)
        self.assertEqual(track.execution_authority,'UNKNOWN')
        drift=replace(snapshot,pulls=(replace(snapshot.pulls[0],head_sha='d'*40),))
        refreshed=planner.plan((drift,),previous=track)
        changed=next(c for c in refreshed.candidates if c.issue.number==6)
        self.assertEqual(changed.status,Status.UNKNOWN)
        self.assertEqual({sha for _,sha in changed.head_history},{'a'*40,'d'*40})
        route='/repos/boreal/product/issues?state=all&sort=created&direction=asc&per_page=2&page=2'
        incomplete,_=discover([issue(i,name='boreal/product') for i in (1,2,3)],name='boreal/product',rid='opaque-boreal',
            per_page=2,changed={route:Response(403,None,(('retry-after','1'),))})
        partial=planner.plan((incomplete,),reviews=assessed(incomplete,authority))
        self.assertTrue(partial.candidates)
        self.assertTrue(all(c.status==Status.UNKNOWN for c in partial.candidates))
        self.assertEqual(partial.execution_authority,'UNKNOWN')
