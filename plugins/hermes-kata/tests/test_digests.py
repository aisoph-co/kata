"""Spec §6, issue G1: "after roster import against the golden scenario (ten
persons), assert exactly ten due-rep jobs, one team-quiz job, and one
teach-back job exist, each with the recipient's correct chat id and no
toolset beyond `learning` [except team_quiz, which also carries `clarify`,
KATA-24]."""
from hermes_kata.digests import (
    TEAM_QUIZ_TOOLSETS,
    create_digest_jobs,
    plan_digest_jobs,
)

TEAM_CHANNEL = "slack:C_TEAM"


def _golden_roster(n=10):
    """Ten persons, each with a resolvable slack chat id — the shape a
    caller builds by matching `POST /admin/roster/import`'s request persons
    (which know `slack_user_id`) against its response persons (which know
    `id`)."""
    return [{"id": f"person-{i}", "email": f"person{i}@example.com", "slack_user_id": f"U{i}"} for i in range(n)]


def test_exactly_ten_due_rep_jobs_one_team_quiz_one_teach_back():
    jobs = plan_digest_jobs(_golden_roster(), team_channel=TEAM_CHANNEL)

    due_rep = [j for j in jobs if j.kind == "due_rep"]
    team_quiz = [j for j in jobs if j.kind == "team_quiz"]
    teach_back = [j for j in jobs if j.kind == "teach_back"]

    assert len(due_rep) == 10
    assert len(team_quiz) == 1
    assert len(teach_back) == 1
    assert len(jobs) == 12


def test_every_job_carries_the_recipients_correct_chat_id():
    roster = _golden_roster()
    jobs = plan_digest_jobs(roster, team_channel=TEAM_CHANNEL)

    due_rep_by_name = {j.name: j for j in jobs if j.kind == "due_rep"}
    for person in roster:
        job = due_rep_by_name[f"kata-due-rep-{person['id']}"]
        assert job.deliver == f"slack:{person['slack_user_id']}"

    team_jobs = [j for j in jobs if j.kind in ("team_quiz", "teach_back")]
    assert all(j.deliver == TEAM_CHANNEL for j in team_jobs)


def test_no_toolset_beyond_learning_except_team_quiz_which_also_gets_clarify():
    jobs = plan_digest_jobs(_golden_roster(), team_channel=TEAM_CHANNEL)
    for job in jobs:
        if job.kind == "team_quiz":
            assert set(job.enabled_toolsets) == set(TEAM_QUIZ_TOOLSETS)
        else:
            assert set(job.enabled_toolsets) == {"learning"}


def test_a_person_with_no_chat_id_yet_gets_no_due_rep_job_and_is_not_fabricated():
    """Roster import hasn't recorded a chat id for everyone yet (KATA-4) —
    recipient resolution finds nothing for that person, and this never
    invents one."""
    roster = _golden_roster(3)
    roster[1] = {"id": "person-1", "email": "person1@example.com"}  # no slack_user_id

    jobs = plan_digest_jobs(roster, team_channel=TEAM_CHANNEL)

    due_rep_names = {j.name for j in jobs if j.kind == "due_rep"}
    assert due_rep_names == {"kata-due-rep-person-0", "kata-due-rep-person-2"}


def test_empty_roster_still_plans_the_two_team_jobs():
    jobs = plan_digest_jobs([], team_channel=TEAM_CHANNEL)

    assert [j.kind for j in jobs] == ["team_quiz", "teach_back"]


def test_jobs_are_created_idempotently_by_name():
    roster = _golden_roster()
    created_calls = []

    def fake_create_job(**kwargs):
        created_calls.append(kwargs)
        return {"name": kwargs["name"]}

    first = create_digest_jobs(fake_create_job, roster, team_channel=TEAM_CHANNEL)
    second = create_digest_jobs(fake_create_job, roster, team_channel=TEAM_CHANNEL)

    assert len(first) == len(second) == 12
    names_first = {call["name"] for call in created_calls[:12]}
    names_second = {call["name"] for call in created_calls[12:]}
    assert names_first == names_second  # same name = same job, re-run is idempotent
