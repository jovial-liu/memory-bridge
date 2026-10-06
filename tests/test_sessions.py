import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sessions as s

AT = dt.datetime(2026, 10, 6, 6, tzinfo=dt.timezone.utc)

def event(ident='a'*32, project='demo', actor='person-a', **kw):
    e = dict(version=1, id=ident, created_at='2026-10-05T00:00:00Z', kind='fact',
             status='confirmed', text='Fictional preference', scope=dict(project=project, platform='app', account='demo'),
             source=dict(reference='fictional-quote', excerpt='Fictional preference'), evidence_role='user', supersedes=[])
    if actor is not None:
        e['scope']['actor_id'] = actor
    e.update(kw)
    return e


def request(events=None, session='1'*32, actor='person-a', revision=None, kind='fact', project='demo'):
    e = event(project=project, actor=actor, kind=kind)
    e.pop('id'); e.pop('created_at'); e.pop('version')
    return dict(id='f'*32, operation='write', context=dict(actor_id=actor, session_id=session, app_id='same-app',
                observed_revisions=revision or {}), event=e)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        (self.root/'memory').mkdir()
        self.policy = dict(version=1, require_context=True, actors=['person-a', 'person-b', 'unknown'], legacy_actor_bindings={})
        self.save_policy()
    def tearDown(self): self.tmp.cleanup()
    def save_policy(self): (self.root/'memory/session-policy.json').write_text(json.dumps(self.policy))
    def rev(self, events): return s.snapshot(events, self.policy, AT)['projects']
    def prepare(self, item, events=()): return s.prepare_write(self.root, item, list(events), AT)
    def error(self, item, events, code):
        with self.assertRaises(s.SessionConflict) as caught: self.prepare(item, events)
        self.assertEqual(caught.exception.code, code)
    def test_same_app_different_sessions(self):
        one=self.prepare(request(session='1'*32)); two=self.prepare(request(session='2'*32))
        self.assertNotEqual(one['event']['origin'], two['event']['origin'])
        self.assertEqual(one['event']['scope']['actor_id'], two['event']['scope']['actor_id'])
    def test_required_context(self):
        item=request(); item.pop('context'); self.error(item, [], 'session_context_required')
    def test_legacy_opt_in(self):
        self.policy['require_context']=False; self.save_policy(); item=request(); item.pop('context')
        self.assertEqual(self.prepare(item), item)
    def test_unknown_actor_not_confirmed(self): self.error(request(actor='unknown'), [], 'actor_confirmation_required')
    def test_unknown_candidate_background_allowed(self):
        item=request(actor='unknown'); item['event']['status']='candidate'; self.prepare(item)
    def test_unregistered_actor(self): self.error(request(actor='person-c'), [], 'actor_not_registered')
    def test_actor_scope_mismatch(self):
        item=request(); item['event']['scope']['actor_id']='person-b'; self.error(item, [], 'actor_context_mismatch')
    def test_cannot_spoof_origin(self):
        item=request(); item['event']['origin']={'session_id':'2'*32}; self.error(item, [], 'origin_context_mismatch')
    def test_input_unchanged(self):
        item=request(); prior=copy.deepcopy(item); self.prepare(item); self.assertEqual(item, prior)
    def test_independent_append_accepts_old_snapshot(self):
        self.prepare(request(revision={'demo':s.EMPTY_REVISION}), [event()])
    def test_state_requires_version(self): self.error(request(kind='project_state'), [], 'observed_revision_required')
    def test_empty_project_state(self): self.prepare(request(kind='project_state', revision={'demo':s.EMPTY_REVISION}))
    def test_stale_state_rejected(self):
        self.error(request(kind='project_state', revision={'demo':s.EMPTY_REVISION}), [event()], 'stale_project_revision')
    def test_unrelated_project_does_not_invalidate(self):
        self.prepare(request(kind='project_state', revision={'demo':s.EMPTY_REVISION}), [event(project='other')])
    def test_claim_is_guarded_even_when_kind_fact(self):
        item=request(); item['event']['claim']={'subject':'person-a','predicate':'goal','value':'fictional'}
        self.error(item, [], 'observed_revision_required')
    def test_two_corrections_only_first_can_apply(self):
        old=event(); item=request(kind='correction', revision=self.rev([old])); item['event']['supersedes']=[old['id']]
        self.prepare(item, [old])
        newer=event('b'*32, kind='correction', supersedes=[old['id']])
        self.error(item, [old,newer], 'stale_project_revision')
    def test_inactive_target_rejected_even_after_refresh(self):
        old=event(); new=event('b'*32, supersedes=[old['id']]); events=[old,new]
        item=request(kind='correction', revision=self.rev(events)); item['event']['supersedes']=[old['id']]
        self.error(item, events, 'inactive_replacement_target')
    def test_cross_person_correction_blocked(self):
        old=event(actor='person-b'); item=request(kind='correction', revision=self.rev([old])); item['event']['supersedes']=[old['id']]
        self.error(item, [old], 'cross_actor_replacement')
    def test_unknown_legacy_actor_not_guessed(self):
        old=event(actor=None); item=request(kind='correction', revision=self.rev([old])); item['event']['supersedes']=[old['id']]
        self.error(item, [old], 'legacy_actor_unresolved')
    def test_sourced_legacy_actor_binding(self):
        old=event(actor=None); self.policy['legacy_actor_bindings'][old['id']]={'actor_id':'person-a','source':'fictional-user-confirmation'}; self.save_policy()
        item=request(kind='correction', revision=self.rev([old])); item['event']['supersedes']=[old['id']]
        self.prepare(item, [old])
    def test_incomplete_binding_rejected(self):
        self.policy['legacy_actor_bindings']['a'*32]={'actor_id':'person-a'}; self.save_policy()
        with self.assertRaises(ValueError): s.read_policy(self.root)
    def test_missing_target(self):
        item=request(kind='correction', revision={'demo':s.EMPTY_REVISION}); item['event']['supersedes']=['a'*32]
        self.error(item, [], 'unknown_replacement_target')
    def test_forget_requires_fresh_revision(self):
        item=request(); item['operation']='forget'; self.error(item, [], 'observed_revision_required')
    def test_expiry_changes_revision_without_file_changes(self):
        e=event(expires_at='2026-10-06T07:00:00Z')
        a=s.snapshot([e], self.policy, AT); b=s.snapshot([e], self.policy, AT+dt.timedelta(hours=2))
        self.assertNotEqual(a['revision'], b['revision']); self.assertTrue(s.refresh_required(a,a,AT+dt.timedelta(hours=2)))
    def test_snapshot_does_not_change_on_clock_tick(self):
        a=s.snapshot([event()], self.policy, AT); b=s.snapshot([event()], self.policy, AT+dt.timedelta(seconds=1))
        self.assertEqual(a['revision'], b['revision']); self.assertFalse(s.refresh_required(a,b,AT))
    def test_snapshot_order_invariant(self):
        a,b=event(),event('b'*32); self.assertEqual(self.rev([a,b]),self.rev([b,a]))
    def test_snapshot_has_no_private_text(self): self.assertNotIn('Fictional preference',json.dumps(s.snapshot([event()],self.policy,AT)))
    def test_refresh_on_policy_change(self):
        a=s.snapshot([],self.policy,AT); b=copy.deepcopy(a); b['policy_revision']='b'*64
        self.assertTrue(s.refresh_required(a,b,AT))
    def test_checkpoint_separate_context(self):
        item=request(); item.update(project='demo',checkpoint=dict(task_id='same-name'))
        self.assertEqual(s.checkpoint_payload(self.root,item)['session_context']['session_id'],'1'*32)
    def test_receipt_keeps_session(self):
        self.assertEqual(s.bind_receipt({},request())['session_context']['actor_id'],'person-a')
    def test_malformed_context(self):
        for context in [None,{},dict(actor_id='../../bad',app_id='a',session_id='1'*32),dict(actor_id='a',app_id='a',session_id='short')]:
            with self.assertRaises(ValueError): s.validate_context(context)
    def test_malformed_revision(self):
        context=request()['context']; context['observed_revisions']={'demo':'not-hash'}
        with self.assertRaises(ValueError): s.validate_context(context)
    def test_retry_excludes_own_partial_event(self):
        item=request(kind='project_state',revision={'demo':s.EMPTY_REVISION})
        own=event(hashlib.sha256((item['id']+':event').encode()).hexdigest()[:32],kind='project_state')
        self.prepare(item,[own])

if __name__=='__main__': unittest.main()
