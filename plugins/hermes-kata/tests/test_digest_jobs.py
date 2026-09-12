"""Spec §6: "one `cron.jobs.create_job` per digest kind per recipient" — and
this issue's own done check: after a golden-scenario roster import, exactly
ten due-rep jobs, one team-quiz job, one teach-back job exist, each with the
recipient's correct chat ID and no toolset beyond `learning`.
"""

from __future__ import annotations

import json

import pytest
from fakes import FakeCron

from hermes_kata.digest import (
    DigestRecipient,
    create_digest_jobs,
    due_rep_job_name,
    load_digest_roster,
    team_quiz_job_name,
    teach_back_job_name,
    team_recipient_from_env,
)
from hermes_kata.tools import TOOLSET, JobIdentityRegistry

# The golden scenario's ten-person roster (Ferry): Quinn plus nine reports.
ROSTER = [DigestRecipient(person_id=f"p{i}", platform="slack", external_id=f"U0FERRY{i:02d}") for i in range(1, 11)]
TEAM_RECIPIENT = DigestRecipient(person_id="team", platform="slack", external_id="C0FERRYTEAM")


def test_exactly_ten_due_rep_one_team_quiz_one_teach_back_job_are_created():
    cron = FakeCron()
    job_identities = JobIdentityRegistry()

    names = create_digest_jobs(cron, job_identities, learners=ROSTER, team_recipient=TEAM_RECIPIENT)

    due_rep_names = [n for n in names if n.startswith("kata-due-rep:")]
    assert len(due_rep_names) == 10
    assert names.count(team_quiz_job_name()) == 1
    assert names.count(teach_back_job_name()) == 1
    assert len(names) == 12
    assert len(cron.jobs.jobs) == 12


def test_each_due_rep_job_carries_its_own_recipients_chat_id():
    cron = FakeCron()
    create_digest_jobs(cron, JobIdentityRegistry(), learners=ROSTER, team_recipient=TEAM_RECIPIENT)

    for learner in ROSTER:
        job = cron.jobs.jobs[due_rep_job_name(learner.person_id)]
        assert job["recipient"] == {"platform": "slack", "external_id": learner.external_id}


def test_team_quiz_and_teach_back_jobs_carry_the_team_recipients_chat_id():
    cron = FakeCron()
    create_digest_jobs(cron, JobIdentityRegistry(), learners=ROSTER, team_recipient=TEAM_RECIPIENT)

    for name in (team_quiz_job_name(), teach_back_job_name()):
        assert cron.jobs.jobs[name]["recipient"] == {"platform": "slack", "external_id": "C0FERRYTEAM"}


def test_no_job_carries_a_toolset_beyond_learning():
    cron = FakeCron()
    create_digest_jobs(cron, JobIdentityRegistry(), learners=ROSTER, team_recipient=TEAM_RECIPIENT)

    for job in cron.jobs.jobs.values():
        assert job["toolset"] == TOOLSET == "learning"


def test_calling_create_digest_jobs_twice_is_idempotent_on_name():
    # A second deploy/reload calls create_job again for every job (this
    # module never checks-then-creates), but `name` is unchanged each time
    # — the same twelve names, no duplicate entries in the fake registry.
    cron = FakeCron()
    job_identities = JobIdentityRegistry()
    create_digest_jobs(cron, job_identities, learners=ROSTER, team_recipient=TEAM_RECIPIENT)
    create_digest_jobs(cron, job_identities, learners=ROSTER, team_recipient=TEAM_RECIPIENT)

    assert len(cron.jobs.jobs) == 12
    assert len(cron.jobs.calls) == 24


def test_every_created_job_gets_its_identity_registered_for_a_cron_triggered_tool_call():
    cron = FakeCron()
    job_identities = JobIdentityRegistry()
    create_digest_jobs(cron, job_identities, learners=ROSTER, team_recipient=TEAM_RECIPIENT)

    for learner in ROSTER:
        identity = job_identities.get(due_rep_job_name(learner.person_id))
        assert identity is not None
        assert identity.platform == "slack"
        assert identity.external_id == learner.external_id

    team_identity = job_identities.get(team_quiz_job_name())
    assert team_identity is not None
    assert team_identity.external_id == "C0FERRYTEAM"


def test_load_digest_roster_parses_the_deploy_written_file(tmp_path):
    path = tmp_path / "roster.json"
    path.write_text(
        json.dumps(
            [
                {"person_id": "p1", "platform": "slack", "external_id": "U0FERRY01"},
                {"person_id": "p2", "platform": "slack", "external_id": "U0FERRY02"},
            ]
        ),
        encoding="utf-8",
    )

    recipients = load_digest_roster(path)

    assert recipients == [
        DigestRecipient(person_id="p1", platform="slack", external_id="U0FERRY01"),
        DigestRecipient(person_id="p2", platform="slack", external_id="U0FERRY02"),
    ]


def test_team_recipient_from_env_is_none_when_unset(monkeypatch):
    monkeypatch.delenv("KATA_TEAM_RECIPIENT_PLATFORM", raising=False)
    monkeypatch.delenv("KATA_TEAM_RECIPIENT_EXTERNAL_ID", raising=False)

    assert team_recipient_from_env() is None


def test_team_recipient_from_env_builds_a_recipient_when_configured(monkeypatch):
    monkeypatch.setenv("KATA_TEAM_RECIPIENT_PLATFORM", "slack")
    monkeypatch.setenv("KATA_TEAM_RECIPIENT_EXTERNAL_ID", "C0FERRYTEAM")

    recipient = team_recipient_from_env()

    assert recipient == DigestRecipient(person_id="team", platform="slack", external_id="C0FERRYTEAM")
