"""Issue G1's real entry points: `sync_digest_jobs`, `post_team_quiz`, and
`reveal_team_quiz` are Hermes tools (the only real extension point the
`PluginContext` offers — no command-registration hook exists on it), so a
live turn reaches `create_digest_jobs`/`run_team_quiz`/`render_reveal`
exactly the way any other registered tool is called, following the
`kata-team-quiz-commands` system-prompt instruction this module also
registers."""
import json

from conftest import FakePluginContext, FakeSessionStore

from hermes_kata.commands import (
    TEAM_QUIZ_COMMAND_INSTRUCTION,
    load_roster,
    make_post_team_quiz_handler,
    make_reveal_team_quiz_handler,
    make_sync_digest_jobs_handler,
    register_team_quiz_commands,
)
from hermes_kata.quiz import DEFAULT_TODAY_SLUGS, TeamQuizItemRegistry, TeamQuizState
from hermes_kata.reveal import CorrectAnswerers, QuizTally, record_submit_review


def _fresh_state():
    return TeamQuizState(tally=QuizTally(), registry=TeamQuizItemRegistry(), correct_answerers=CorrectAnswerers())


def test_load_roster_is_empty_by_default_never_fabricated():
    # KATA-4 (roster import) hasn't run in this environment yet — the
    # vendored roster.json says so honestly instead of inventing recipients.
    assert load_roster() == []


def test_sync_digest_jobs_tool_creates_jobs_from_an_injected_roster(tmp_path):
    roster_path = tmp_path / "roster.json"
    roster_path.write_text(json.dumps({"persons": [{"id": "p1", "slack_user_id": "U1"}]}))

    created_calls = []
    handler = make_sync_digest_jobs_handler(
        create_job_fn=lambda **kwargs: created_calls.append(kwargs), roster_path=roster_path
    )

    result = handler(FakeSessionStore(), "sess-1", team_channel="slack:C_TEAM")

    assert result == {"created": 3}  # one due-rep job + team-quiz + teach-back
    assert {c["name"] for c in created_calls} == {"kata-due-rep-p1", "kata-team-quiz-team", "kata-teach-back-team"}


def test_sync_digest_jobs_tool_with_the_default_empty_roster_still_plans_the_two_team_jobs():
    created_calls = []
    handler = make_sync_digest_jobs_handler(create_job_fn=lambda **kwargs: created_calls.append(kwargs))

    result = handler(FakeSessionStore(), "sess-1", team_channel="slack:C_TEAM")

    assert result == {"created": 2}
    assert {c["name"] for c in created_calls} == {"kata-team-quiz-team", "kata-teach-back-team"}


def test_post_team_quiz_tool_defaults_to_todays_round_and_marks_the_registry():
    state = _fresh_state()
    handler = make_post_team_quiz_handler(state)

    result = handler(FakeSessionStore(), "sess-1")

    assert [q["choices"] for q in result["question_prompts"]]  # both items posted
    assert "ledger-migrations" in result["chip"]
    assert state.registry.is_quiz_item(DEFAULT_TODAY_SLUGS[0])


def test_post_team_quiz_tool_honors_explicit_item_ids():
    state = _fresh_state()
    handler = make_post_team_quiz_handler(state)

    result = handler(FakeSessionStore(), "sess-1", item_ids=["lm-1"])

    assert len(result["question_prompts"]) == 1
    assert state.registry.is_quiz_item("lm-1")
    assert not state.registry.is_quiz_item("lm-2")


def test_reveal_team_quiz_tool_reads_the_same_state_a_prior_submit_review_updated():
    state = _fresh_state()
    record_submit_review(state.tally, "lm-1", {"choice": 2}, correct_answerers=state.correct_answerers, person_name="Hugo")
    record_submit_review(state.tally, "lm-1", {"choice": 0}, correct_answerers=state.correct_answerers, person_name="Nushka")
    handler = make_reveal_team_quiz_handler(state)

    result = handler(FakeSessionStore(), "sess-1", item_ids=["lm-1"])

    assert "Hugo" in result["text"]
    assert "Nushka" not in result["text"]


def test_register_team_quiz_commands_wires_all_three_tools_and_the_instruction():
    ctx = FakePluginContext()
    state = _fresh_state()

    register_team_quiz_commands(ctx, state)

    assert set(ctx.tools) == {"sync_digest_jobs", "post_team_quiz", "reveal_team_quiz"}
    assert ctx.prompt_sections["kata-team-quiz-commands"]["callback"](None) == TEAM_QUIZ_COMMAND_INSTRUCTION

    # The registered post_team_quiz handler updates the *same* state object
    # passed in — not a copy — so a later reveal_team_quiz call on the same
    # ctx/state sees today's marked items.
    ctx.tools["post_team_quiz"]["handler"](FakeSessionStore(), "sess-1")
    assert state.registry.is_quiz_item("lm-1")
