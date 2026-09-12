"""`register(ctx)` (`plugins/hermes-kata/__init__.py`) is the one thing no
other test file exercises directly — every other test imports a constituent
function instead. This loads it the same way Hermes's plugin loader does —
an explicit `submodule_search_locations` import, per `__init__.py`'s own
docstring — and drives the identity hook end to end, standing in only for the
learning-service core's own HTTP calls (`LearningServiceClient.
resolve_identity`/`.request`, monkeypatched at the class level so the
plugin's own real client instance picks them up)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fakes import FakeGateway, FakeMessageEvent, FakePluginContext, FakeSessionStore, FakeSource

PLUGIN_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def plugin_module(monkeypatch, tmp_path):
    monkeypatch.setenv("LEARNING_SERVICE_URL", "https://learning.example")
    monkeypatch.setenv("LEARNING_SERVICE_TOKEN", "test-token")

    catalog = tmp_path / "tools.json"
    catalog.write_text(
        '{"tools": [{"name": "submit_review", "endpoint": {"method": "POST", "path": "/me/reviews"}, '
        '"parameters": {"type": "object", "properties": {}}}]}'
    )
    monkeypatch.setenv("KATA_TOOLS_JSON", str(catalog))

    spec = importlib.util.spec_from_file_location(
        "hermes_kata_plugin_under_test", PLUGIN_DIR / "__init__.py", submodule_search_locations=[str(PLUGIN_DIR)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def test_register_wires_the_tool_catalog_identity_hook_and_mcq_section(plugin_module):
    from hermes_kata.mcq import SECTION_ID

    ctx = FakePluginContext()
    plugin_module.register(ctx)

    assert "submit_review" in ctx.tools
    assert ctx.tools["submit_review"]["toolset"] == "learning"
    assert "pre_gateway_dispatch" in ctx.hooks
    assert SECTION_ID in ctx.system_prompt_sections


def test_register_wires_the_socratic_guardrails_section_and_skill(plugin_module):
    from hermes_kata.guardrails import SECTION_ID, SKILL_ID, SKILL_PATH, SYSTEM_PROMPT_GUARDRAILS

    ctx = FakePluginContext()
    plugin_module.register(ctx)

    assert ctx.system_prompt_sections[SECTION_ID]["content"] == SYSTEM_PROMPT_GUARDRAILS
    assert ctx.skills[SKILL_ID] == SKILL_PATH


def test_register_tolerates_a_ctx_with_no_register_skill_at_all(plugin_module, monkeypatch, tmp_path):
    """`register_skill` is unverified against the real Hermes plugin API
    (review round on this issue) — a `ctx` that simply doesn't expose it
    (an older Hermes, or a test double that hasn't caught up) must not stop
    the rest of `register()`, digest jobs included."""
    _stub_link_calls(monkeypatch, plugin_module.LearningServiceClient)
    roster_path = tmp_path / "roster.json"
    roster_path.write_text('[{"person_id": "p1", "platform": "slack", "external_id": "U01"}]')
    monkeypatch.setenv("KATA_DIGEST_ROSTER", str(roster_path))
    monkeypatch.setenv("KATA_TEAM_RECIPIENT_PLATFORM", "slack")
    monkeypatch.setenv("KATA_TEAM_RECIPIENT_EXTERNAL_ID", "C0TEAM")

    ctx = FakePluginContext()
    monkeypatch.delattr(FakePluginContext, "register_skill")

    plugin_module.register(ctx)  # must not raise

    from hermes_kata.digest import due_rep_job_name

    assert due_rep_job_name("p1") in ctx.cron.jobs.jobs


def test_register_tolerates_a_register_skill_that_raises(plugin_module, monkeypatch, tmp_path):
    """A real Hermes with a different `register_skill` signature — or any
    other failure inside it — must not take down the identity hook, tool
    catalog, mcq section, or digest jobs registered ahead of it."""
    _stub_link_calls(monkeypatch, plugin_module.LearningServiceClient)
    roster_path = tmp_path / "roster.json"
    roster_path.write_text('[{"person_id": "p1", "platform": "slack", "external_id": "U01"}]')
    monkeypatch.setenv("KATA_DIGEST_ROSTER", str(roster_path))
    monkeypatch.setenv("KATA_TEAM_RECIPIENT_PLATFORM", "slack")
    monkeypatch.setenv("KATA_TEAM_RECIPIENT_EXTERNAL_ID", "C0TEAM")

    ctx = FakePluginContext()

    def broken_register_skill(name, content):
        raise TypeError("simulated real-Hermes signature mismatch")

    monkeypatch.setattr(ctx, "register_skill", broken_register_skill)

    plugin_module.register(ctx)  # must not raise

    from hermes_kata.digest import due_rep_job_name

    assert due_rep_job_name("p1") in ctx.cron.jobs.jobs
    assert ctx.skills == {}


def test_register_binds_a_known_identity_before_a_tool_call(plugin_module, monkeypatch):
    LearningServiceClient = plugin_module.LearningServiceClient

    monkeypatch.setattr(
        LearningServiceClient,
        "resolve_identity",
        lambda self, platform, external_id, alt_id=None: {"id": "p1", "display_name": "Hugo Marchetti"},
    )
    monkeypatch.setattr(LearningServiceClient, "is_manager", lambda self, identity: False)

    def fake_request(self, method, path, *, identity=None, params=None, json_body=None):
        if method == "POST" and path == "/me/reviews":
            return {"grade": 1.0, "correct": True}
        raise AssertionError(f"unexpected request: {method} {path}")

    monkeypatch.setattr(LearningServiceClient, "request", fake_request)

    ctx = FakePluginContext()
    plugin_module.register(ctx)

    store = FakeSessionStore()
    gateway = FakeGateway()
    event = FakeMessageEvent(source=FakeSource(platform="slack", user_id="U123"))
    bind_identity = ctx.hooks["pre_gateway_dispatch"][0]
    result = bind_identity(event, gateway, store)
    assert result == {"action": "allow"}
    store.link_session_id("sess-1", "slack:U123")

    submit_review = ctx.tools["submit_review"]["handler"]
    reply = submit_review(
        {"item_id": "lm-1", "idempotency_key": "k1", "response": {"choice": 1}}, session_id="sess-1"
    )
    assert reply == '{"grade": 1.0, "correct": true}'


def test_register_creates_no_digest_jobs_when_the_roster_env_var_is_unset(plugin_module, monkeypatch):
    monkeypatch.delenv("KATA_DIGEST_ROSTER", raising=False)

    ctx = FakePluginContext()
    plugin_module.register(ctx)

    assert ctx.cron.jobs.jobs == {}


def _stub_link_calls(monkeypatch, LearningServiceClient) -> list[dict]:
    """`_register_digest_jobs` now links a `slack_thread` quiz-answer
    identity per learner (AGCTM-69 fix-round 2) — stub the two calls that
    takes (`POST /me/link-code`, `POST /identities/link`) so these tests
    don't reach a real `https://learning.example`."""
    calls: list[dict] = []

    def fake_request(self, method, path, *, identity=None, params=None, json_body=None):
        calls.append({"method": method, "path": path, "identity": identity, "json_body": json_body})
        if method == "POST" and path == "/me/link-code":
            return {"code": f"code-{identity.external_id}"}
        if method == "POST" and path == "/identities/link":
            return None
        raise AssertionError(f"unexpected request: {method} {path}")

    monkeypatch.setattr(LearningServiceClient, "request", fake_request)
    return calls


def test_register_creates_no_digest_jobs_when_the_team_recipient_env_is_unset(plugin_module, monkeypatch, tmp_path):
    _stub_link_calls(monkeypatch, plugin_module.LearningServiceClient)
    roster_path = tmp_path / "roster.json"
    roster_path.write_text('[{"person_id": "p1", "platform": "slack", "external_id": "U01"}]')
    monkeypatch.setenv("KATA_DIGEST_ROSTER", str(roster_path))
    monkeypatch.delenv("KATA_TEAM_RECIPIENT_PLATFORM", raising=False)
    monkeypatch.delenv("KATA_TEAM_RECIPIENT_EXTERNAL_ID", raising=False)

    ctx = FakePluginContext()
    plugin_module.register(ctx)

    assert ctx.cron.jobs.jobs == {}


def test_register_links_a_quiz_thread_identity_for_every_learner_in_the_roster(plugin_module, monkeypatch, tmp_path):
    calls = _stub_link_calls(monkeypatch, plugin_module.LearningServiceClient)
    roster_path = tmp_path / "roster.json"
    roster_path.write_text(
        '[{"person_id": "p1", "platform": "slack", "external_id": "U01"}, '
        '{"person_id": "p2", "platform": "slack", "external_id": "U02"}]'
    )
    monkeypatch.setenv("KATA_DIGEST_ROSTER", str(roster_path))
    monkeypatch.delenv("KATA_TEAM_RECIPIENT_PLATFORM", raising=False)
    monkeypatch.delenv("KATA_TEAM_RECIPIENT_EXTERNAL_ID", raising=False)

    ctx = FakePluginContext()
    plugin_module.register(ctx)

    link_code_calls = [c for c in calls if c["path"] == "/me/link-code"]
    link_calls = [c for c in calls if c["path"] == "/identities/link"]
    assert {c["identity"].external_id for c in link_code_calls} == {"U01", "U02"}
    assert {c["json_body"]["external_id"] for c in link_calls} == {"U01", "U02"}
    assert all(c["json_body"]["platform"] == "slack_thread" for c in link_calls)


def test_register_creates_digest_jobs_when_fully_configured(plugin_module, monkeypatch, tmp_path):
    _stub_link_calls(monkeypatch, plugin_module.LearningServiceClient)
    roster_path = tmp_path / "roster.json"
    roster_path.write_text(
        '[{"person_id": "p1", "platform": "slack", "external_id": "U01"}, '
        '{"person_id": "p2", "platform": "slack", "external_id": "U02"}]'
    )
    monkeypatch.setenv("KATA_DIGEST_ROSTER", str(roster_path))
    monkeypatch.setenv("KATA_TEAM_RECIPIENT_PLATFORM", "slack")
    monkeypatch.setenv("KATA_TEAM_RECIPIENT_EXTERNAL_ID", "C0TEAM")

    ctx = FakePluginContext()
    plugin_module.register(ctx)

    from hermes_kata.digest import due_rep_job_name, team_quiz_job_name, teach_back_job_name

    assert set(ctx.cron.jobs.jobs) == {
        due_rep_job_name("p1"),
        due_rep_job_name("p2"),
        team_quiz_job_name(),
        teach_back_job_name(),
    }
    for job in ctx.cron.jobs.jobs.values():
        assert job["toolset"] == "learning"


def test_a_cron_triggered_tool_call_resolves_via_kata_job_identities_env(plugin_module, monkeypatch):
    """KATA-24 fix round 2: the reported job (`kata-demo-quiz-B-
    C0BVDPW43PE`, created directly against Hermes's cron API, never through
    `/kata-sync-digests`) previously had nothing to resolve identity from —
    a tool call carrying only its `job_name` (no session, the cron-triggered
    shape) raised `no bound identity for this tool call`. `KATA_JOB_IDENTITIES`
    set before `register(ctx)` must let that exact call through instead."""
    monkeypatch.setenv("KATA_JOB_IDENTITIES", '{"kata-demo-quiz-B-C0BVDPW43PE": "slack:C0BVDPW43PE"}')

    LearningServiceClient = plugin_module.LearningServiceClient
    seen = []

    def fake_request(self, method, path, *, identity=None, params=None, json_body=None):
        seen.append({"method": method, "path": path, "identity": identity})
        return {"grade": 1.0, "correct": True}

    monkeypatch.setattr(LearningServiceClient, "request", fake_request)

    ctx = FakePluginContext()
    plugin_module.register(ctx)

    submit_review = ctx.tools["submit_review"]["handler"]
    submit_review(
        {"item_id": "lm-1", "idempotency_key": "k1", "response": {"choice": 1}},
        session_id=None,
        job_name="kata-demo-quiz-B-C0BVDPW43PE",
    )

    assert len(seen) == 1
    assert seen[0]["identity"].platform == "slack"
    assert seen[0]["identity"].external_id == "C0BVDPW43PE"


def test_a_cron_triggered_tool_call_resolves_from_the_jobs_own_cron_recipient(plugin_module, monkeypatch):
    """KATA-24 fix round 3: a job neither planned by `/kata-sync-digests`
    nor named in `KATA_JOB_IDENTITIES` (made directly against Hermes's cron
    API — the reported `kata-demo-quiz-B-*` shape) still resolves, from its
    own durably recorded `recipient`, once one exists in `ctx.cron.jobs`."""
    LearningServiceClient = plugin_module.LearningServiceClient
    seen = []

    def fake_request(self, method, path, *, identity=None, params=None, json_body=None):
        seen.append({"method": method, "path": path, "identity": identity})
        return {"grade": 1.0, "correct": True}

    monkeypatch.setattr(LearningServiceClient, "request", fake_request)

    ctx = FakePluginContext()
    # Simulates a job created directly against Hermes's cron API, outside
    # this plugin entirely — `register(ctx)` never ran `create_digest_jobs`
    # for it, and no env config names it either.
    ctx.cron.jobs.create_job(
        name="kata-demo-quiz-B-C0C10B1KHHP",
        schedule="0 0 1 1 *",
        recipient={"platform": "slack", "external_id": "C0C10B1KHHP"},
    )

    plugin_module.register(ctx)

    submit_review = ctx.tools["submit_review"]["handler"]
    submit_review(
        {"item_id": "lm-1", "idempotency_key": "k1", "response": {"choice": 1}},
        session_id=None,
        job_name="kata-demo-quiz-B-C0C10B1KHHP",
    )

    assert len(seen) == 1
    assert seen[0]["identity"].platform == "slack"
    assert seen[0]["identity"].external_id == "C0C10B1KHHP"


def test_register_refuses_an_unknown_identity_before_any_tool_call(plugin_module, monkeypatch):
    LearningServiceClient = plugin_module.LearningServiceClient
    monkeypatch.setattr(
        LearningServiceClient, "resolve_identity", lambda self, platform, external_id, alt_id=None: None
    )

    ctx = FakePluginContext()
    plugin_module.register(ctx)

    gateway = FakeGateway()
    event = FakeMessageEvent(source=FakeSource(platform="slack", user_id="U999"))
    bind_identity = ctx.hooks["pre_gateway_dispatch"][0]
    result = bind_identity(event, gateway, FakeSessionStore())

    assert result == {"action": "skip", "reason": "unknown_identity"}
    assert len(gateway.replies) == 1
