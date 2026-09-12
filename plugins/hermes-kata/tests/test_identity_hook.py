"""Spec §2: "an unresolved `(platform, external_id)` never reaches a tool
call or the model — assert the mock LLM client receives zero requests for
such an event, and the reply string is exactly the fixed message."

Also covers session binding against a real-shaped `SessionStore`/
`MessageEvent`/tool-call `session_id`: the hook must not raise on
`set_session_metadata`, must derive the session key via
`gateway._session_key_for_source` (no `event.session_key`), and a tool call's
bare `session_id` must resolve back through `lookup_by_session_id`.
"""

from __future__ import annotations

import pytest
from fakes import FakeGateway, FakeLearningServiceClient, FakeMessageEvent, FakeSessionStore, FakeSource

from hermes_kata.identity import (
    UNKNOWN_IDENTITY_MESSAGE,
    SessionIdentityCache,
    SessionStoreHandle,
    make_bind_identity,
)
from hermes_kata.client import ActingIdentity
from hermes_kata.tools import (
    JobIdentityRegistry,
    cron_job_deliver_lookup,
    cron_job_id_from_session_id,
    job_identities_from_env,
    make_identity_resolver,
)


def _event(platform="slack", user_id="U42"):
    return FakeMessageEvent(source=FakeSource(platform=platform, user_id=user_id))


def _session_key(event: FakeMessageEvent, gateway: FakeGateway) -> str:
    return gateway._session_key_for_source(event.source)


def test_unknown_identity_is_refused_never_auto_created():
    client = FakeLearningServiceClient(person=None)
    cache = SessionIdentityCache()
    gateway = FakeGateway()
    session_store = FakeSessionStore()
    bind_identity = make_bind_identity(client, cache, SessionStoreHandle())

    event = _event()
    result = bind_identity(event, gateway, session_store)
    session_key = _session_key(event, gateway)

    assert result == {"action": "skip", "reason": "unknown_identity"}
    assert gateway.replies == [(event, UNKNOWN_IDENTITY_MESSAGE)]
    # Nothing was stashed for a tool call to read later.
    assert cache.get(session_key) is None
    assert session_store.get_session_metadata(session_key, "kata_person") is None


def test_unknown_identity_reply_is_exactly_the_fixed_message_no_model_call():
    client = FakeLearningServiceClient(person=None)
    cache = SessionIdentityCache()
    gateway = FakeGateway()
    bind_identity = make_bind_identity(client, cache, SessionStoreHandle())

    bind_identity(_event(), gateway, FakeSessionStore())

    assert len(gateway.replies) == 1
    _, message = gateway.replies[0]
    assert message == UNKNOWN_IDENTITY_MESSAGE


def test_hook_does_not_raise_against_the_real_session_store_shape():
    # Regression: an earlier hook calling `session_store.set(...)` would
    # raise `AttributeError` — the real `gateway.session.SessionStore` only
    # has `set_session_metadata`. `FakeSessionStore` has no `.set` at all,
    # so this call would raise if the bug came back.
    person_payload = {"id": "p1", "display_name": "Hugo Marchetti", "email": "hugo@kata.example", "is_operator": False}
    client = FakeLearningServiceClient(person=person_payload, manager=False)
    cache = SessionIdentityCache()
    gateway = FakeGateway()
    session_store = FakeSessionStore()
    bind_identity = make_bind_identity(client, cache, SessionStoreHandle())

    event = _event(user_id="U0BV21HFZ47")
    result = bind_identity(event, gateway, session_store)

    assert result == {"action": "allow"}
    session_key = _session_key(event, gateway)
    assert session_store.get_session_metadata(session_key, "kata_person")["id"] == "p1"


def test_known_identity_is_bound_before_any_tool_call():
    person_payload = {"id": "p1", "display_name": "Dee Learner", "email": "dee@kata.example", "is_operator": False}
    client = FakeLearningServiceClient(person=person_payload, manager=False)
    cache = SessionIdentityCache()
    gateway = FakeGateway()
    session_store = FakeSessionStore()
    bind_identity = make_bind_identity(client, cache, SessionStoreHandle())

    event = _event(user_id="U000")
    result = bind_identity(event, gateway, session_store)
    session_key = _session_key(event, gateway)

    assert result == {"action": "allow"}
    assert gateway.replies == []

    bound = cache.get(session_key)
    assert bound is not None
    assert bound.id == "p1"
    assert bound.identity.platform == "slack"
    assert bound.identity.external_id == "U000"
    assert bound.is_manager is False

    # Hermes's own session_store carries the same fact, JSON-serializable
    # (spec §2 pseudocode; not a dataclass).
    stored = session_store.get_session_metadata(session_key, "kata_person")
    assert stored == {
        "id": "p1",
        "display_name": "Dee Learner",
        "is_manager": False,
        "platform": "slack",
        "external_id": "U000",
        "alt_id": None,
    }


def test_is_manager_flag_reflects_team_overview_access():
    person_payload = {"id": "p0", "display_name": "Ada Manager", "email": "ada@kata.example", "is_operator": True}
    client = FakeLearningServiceClient(person=person_payload, manager=True)
    cache = SessionIdentityCache()
    gateway = FakeGateway()
    bind_identity = make_bind_identity(client, cache, SessionStoreHandle())

    event = _event(user_id="U000")
    bind_identity(event, gateway, FakeSessionStore())

    assert cache.get(_session_key(event, gateway)).is_manager is True


def test_relink_mid_session_takes_effect_on_the_next_message_not_a_restart():
    # First message: unknown. Second message, same session: now known. The
    # cache re-resolves every message rather than trusting a stale bind.
    cache = SessionIdentityCache()
    gateway = FakeGateway()
    session_store = FakeSessionStore()

    unknown_client = FakeLearningServiceClient(person=None)
    bind_identity = make_bind_identity(unknown_client, cache, SessionStoreHandle())
    event = _event(user_id="U777")
    bind_identity(event, gateway, session_store)
    session_key = _session_key(event, gateway)
    assert cache.get(session_key) is None

    known_client = FakeLearningServiceClient(
        person={"id": "p1", "display_name": "Dee", "email": "d@kata.example", "is_operator": False}
    )
    bind_identity = make_bind_identity(known_client, cache, SessionStoreHandle())
    result = bind_identity(_event(user_id="U777"), gateway, session_store)

    assert result == {"action": "allow"}
    assert cache.get(session_key) is not None


def test_hook_then_tool_call_resolves_identity_when_session_id_differs_from_session_key():
    # The gateway hands the hook a session *key* (derived from the platform
    # source) but hands tool-call handlers a session *id*
    # (`SessionEntry.session_id`) — a different value. Resolution must map
    # id -> key via `lookup_by_session_id` before it can hit the cache.
    person_payload = {"id": "p1", "display_name": "Hugo Marchetti", "email": "hugo@kata.example", "is_operator": False}
    client = FakeLearningServiceClient(person=person_payload)
    cache = SessionIdentityCache()
    gateway = FakeGateway()
    session_store = FakeSessionStore()
    store_handle = SessionStoreHandle()
    bind_identity = make_bind_identity(client, cache, store_handle)

    event = _event(platform="slack", user_id="U0BV21HFZ47")
    result = bind_identity(event, gateway, session_store)
    assert result == {"action": "allow"}

    session_key = _session_key(event, gateway)
    session_store.link_session_id("session-id-abc", session_key)

    resolver = make_identity_resolver(cache, JobIdentityRegistry(), store_handle)
    identity = resolver(session_id="session-id-abc")

    assert identity.platform == "slack"
    assert identity.external_id == "U0BV21HFZ47"

    # A session reset re-issues `session_id` but keeps `session_key` — still
    # resolves off the same cache entry.
    session_store.link_session_id("session-id-after-reset", session_key)
    identity_after_reset = resolver(session_id="session-id-after-reset")
    assert identity_after_reset.external_id == "U0BV21HFZ47"


def test_store_handle_is_not_clobbered_by_a_later_none_session_store():
    # Hermes passes `session_store=getattr(self, "session_store", None)` on
    # every hook call — a later call with no session_store (e.g. an edge
    # case before one exists) must not blow away a handle that already
    # points at a working store.
    person_payload = {"id": "p1", "display_name": "Hugo", "email": "hugo@kata.example", "is_operator": False}
    client = FakeLearningServiceClient(person=person_payload)
    cache = SessionIdentityCache()
    gateway = FakeGateway()
    session_store = FakeSessionStore()
    store_handle = SessionStoreHandle()
    bind_identity = make_bind_identity(client, cache, store_handle)

    bind_identity(_event(user_id="U0BV21HFZ47"), gateway, session_store)
    assert store_handle.store is session_store

    bind_identity(_event(user_id="U0BV21HFZ47"), gateway, None)
    assert store_handle.store is session_store


def test_unlinked_user_tool_call_raises_not_a_tool_error_reply():
    # The hook already refused (spec §2 — no tool call is even reached for
    # an unlinked user in the real gateway), but if one somehow arrived, the
    # resolver must still fail closed with the documented LookupError rather
    # than silently mis-attributing the call.
    cache = SessionIdentityCache()
    store_handle = SessionStoreHandle()
    resolver = make_identity_resolver(cache, JobIdentityRegistry(), store_handle)

    with pytest.raises(LookupError):
        resolver(session_id="some-session-id")


# --- KATA-24 fix round 2: job_identities_from_env (durable binding for a --
# --- cron job this plugin never itself created) --------------------------


def test_job_identities_from_env_parses_the_reported_demo_job():
    raw = '{"kata-demo-quiz-B-C0BVDPW43PE": "slack:C0BVDPW43PE"}'
    assert job_identities_from_env(raw) == {
        "kata-demo-quiz-B-C0BVDPW43PE": ActingIdentity(platform="slack", external_id="C0BVDPW43PE")
    }


def test_job_identities_from_env_is_a_no_op_when_unset_or_blank():
    assert job_identities_from_env(None) == {}
    assert job_identities_from_env("") == {}
    assert job_identities_from_env("   ") == {}


def test_job_identities_from_env_skips_malformed_json_rather_than_raising():
    assert job_identities_from_env("not json") == {}
    assert job_identities_from_env("[1, 2, 3]") == {}


def test_job_identities_from_env_skips_only_the_one_bad_entry():
    raw = '{"good-job": "slack:C1", "bad-job": "no-colon-here", "other-good-job": "telegram:T1"}'
    assert job_identities_from_env(raw) == {
        "good-job": ActingIdentity(platform="slack", external_id="C1"),
        "other-good-job": ActingIdentity(platform="telegram", external_id="T1"),
    }


def test_job_identities_from_env_feeds_the_registry_the_resolver_reads():
    # End to end: the exact wiring `register(ctx)` does (env -> registry ->
    # resolver), against the exact job name reported in KATA-24.
    registry = JobIdentityRegistry()
    for name, identity in job_identities_from_env(
        '{"kata-demo-quiz-B-C0BVDPW43PE": "slack:C0BVDPW43PE"}'
    ).items():
        registry.set(name, identity)

    resolver = make_identity_resolver(SessionIdentityCache(), registry, SessionStoreHandle())
    identity = resolver(session_id=None, job_name="kata-demo-quiz-B-C0BVDPW43PE")

    assert identity == ActingIdentity(platform="slack", external_id="C0BVDPW43PE")


# --- KATA-24 fix round 4: job_name never reaches a plugin tool handler in --
# --- production (Hermes's tool dispatch only ever forwards task_id/       --
# --- session_id) — recover the job's own id from the cron session id      --
# --- instead, and read its `deliver` target back from the cron job store. -


def test_cron_job_id_from_session_id_parses_the_scheduler_shape():
    # cron/scheduler.py: f"cron_{job_id}_{timestamp:%Y%m%d_%H%M%S}" —
    # confirmed live against hermes-day's agent.log.
    assert cron_job_id_from_session_id("cron_0e771dbadf60_20260912_083307") == "0e771dbadf60"
    assert cron_job_id_from_session_id("cron_c8b27bbaf683_20260912_083318") == "c8b27bbaf683"


def test_cron_job_id_from_session_id_is_none_for_anything_else():
    assert cron_job_id_from_session_id(None) is None
    assert cron_job_id_from_session_id("") is None
    assert cron_job_id_from_session_id("not-a-cron-session") is None
    # A live/interactive session id must never be misread as a job id.
    assert cron_job_id_from_session_id("slack:C0C10B1KHHP:1699999999.000100") is None


def test_cron_job_deliver_lookup_resolves_from_the_jobs_own_deliver_field():
    fake_jobs = {"0e771dbadf60": {"id": "0e771dbadf60", "deliver": "slack:C0C10B1KHHP"}}
    lookup = cron_job_deliver_lookup(get_job=fake_jobs.get)

    assert lookup("0e771dbadf60") == {"platform": "slack", "external_id": "C0C10B1KHHP"}


def test_cron_job_deliver_lookup_degrades_to_none_rather_than_raising():
    def _boom(job_id):
        raise RuntimeError("cron.jobs not importable in this environment")

    assert cron_job_deliver_lookup(get_job=_boom)("anything") is None
    assert cron_job_deliver_lookup(get_job=lambda job_id: None)("missing") is None
    assert cron_job_deliver_lookup(get_job=lambda job_id: {"deliver": "local"})("x") is None
    assert cron_job_deliver_lookup(get_job=lambda job_id: {"deliver": ""})("x") is None
    assert cron_job_deliver_lookup(get_job=lambda job_id: {})("x") is None


def test_resolver_falls_back_to_deliver_lookup_via_job_id_from_session_id():
    # End to end, against the exact live-reported shape (KATA-24): a job
    # neither `JobIdentityRegistry` nor `KATA_JOB_IDENTITIES` ever named,
    # with no `job_name` reaching the handler (production reality) but a
    # real cron-scheduler session id.
    fake_jobs = {"0e771dbadf60": {"id": "0e771dbadf60", "deliver": "slack:C0C10B1KHHP"}}
    resolver = make_identity_resolver(
        SessionIdentityCache(),
        JobIdentityRegistry(),
        SessionStoreHandle(),
        job_deliver_lookup=cron_job_deliver_lookup(get_job=fake_jobs.get),
    )

    identity = resolver(session_id="cron_0e771dbadf60_20260912_083307", job_name=None)

    assert identity == ActingIdentity(platform="slack", external_id="C0C10B1KHHP")


def test_resolver_caches_the_deliver_lookup_hit_so_only_the_first_call_pays():
    calls = []

    def _get_job(job_id):
        calls.append(job_id)
        return {"deliver": "slack:C0C10B1KHHP"}

    registry = JobIdentityRegistry()
    resolver = make_identity_resolver(
        SessionIdentityCache(), registry, SessionStoreHandle(),
        job_deliver_lookup=cron_job_deliver_lookup(get_job=_get_job),
    )
    session_id = "cron_0e771dbadf60_20260912_083307"

    first = resolver(session_id=session_id, job_name=None)
    second = resolver(session_id=session_id, job_name=None)

    assert first == second == ActingIdentity(platform="slack", external_id="C0C10B1KHHP")
    assert calls == ["0e771dbadf60"]  # only the first call actually looked it up
    assert registry.get("0e771dbadf60") == ActingIdentity(platform="slack", external_id="C0C10B1KHHP")


def test_resolver_still_raises_when_neither_job_name_nor_session_id_resolve():
    resolver = make_identity_resolver(
        SessionIdentityCache(), JobIdentityRegistry(), SessionStoreHandle(),
        job_deliver_lookup=cron_job_deliver_lookup(get_job=lambda job_id: None),
    )

    with pytest.raises(LookupError):
        resolver(session_id="cron_deadbeef0000_20260912_083307", job_name=None)
