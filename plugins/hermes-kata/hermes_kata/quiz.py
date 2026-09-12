"""Job 4 continued (spec §6, §8): the team quiz — pick the daily question,
post it as `clarify` Block Kit buttons with a confidence gate, an "N of M
answered" line, and a source chip, collect responses hidden until a manual
reveal, and reveal only team-level counts (frames 06-07).

A tap rides the same `submit_review` forwarder `tools.py` already registers
under the `learning` toolset (`response={"choice": ...}`, spec's own
`response`-shape table) — this module decides *when* to call it and how to
render around it; it adds no new learning-service endpoint. `review.source`
must come back `slack_thread` for a quiz answer (spec "Decisions" table —
already a valid enum value, no contract change *to that table*). The core's
own `_SOURCE_BY_PLATFORM` (`agency-v1/learning_service/reviews.py`) has no
DM/thread split for `slack` — it maps `"slack"` unconditionally to
`"slack_dm"` — so a quiz-answer call cannot send the learner's own `"slack"`
platform and land as `slack_thread`; every quiz-answer identity instead
asserts `QUIZ_ANSWER_SOURCE_PLATFORM` (`"slack_thread"` itself), which isn't
a key in that table, so `.get(platform, platform)` passes it through
unchanged (`test_quiz_review_source.py` asserts this against the real
mapping, not a hand-rolled copy of it).

The reveal is presenter-triggered (`/kata-reveal`, AGCTM-69) — never a
timer — and states only a team-level count per option ("*n* of *m* picked
X"), one concept to schedule, and the sprint leaderboard; it never
attributes an answer to a person and never surfaces an individual's wrong
answer. This module doesn't register the `/kata-reveal` command itself
(same as `mcq.py` doesn't register `clarify`) — `handle_reveal_command`
below is the integration point a command dispatcher calls into.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .client import ActingIdentity, LearningServiceClient, LearningServiceError
from .mcq import MCQ_KIND, clarify_kwargs_for_item

CONFIDENCE_SCALE = (1, 5)

# Not a real messaging platform Hermes reports on an inbound event — chosen
# specifically because it is *not* a key in the core's `_SOURCE_BY_PLATFORM`
# (`agency-v1/learning_service/reviews.py`), so `.get(platform, platform)`
# passes it straight through as `review.source`. Every quiz-answer identity
# asserts this platform; a learner's own DM-bound `submit_review` call
# (tools.py's ordinary forwarder) keeps asserting their real platform
# (`"slack"`, ...) and lands `slack_dm` as before — this only touches the
# quiz.
QUIZ_ANSWER_SOURCE_PLATFORM = "slack_thread"


def quiz_answer_identity(external_id: str) -> ActingIdentity:
    """The acting identity a quiz-answer `submit_review` call must assert —
    never a learner's own platform (spec §6's `slack_thread` requirement;
    see the module docstring)."""
    return ActingIdentity(platform=QUIZ_ANSWER_SOURCE_PLATFORM, external_id=external_id)


# Fixed, hand-verified against `agency-v1/learning_service/main.py`'s own
# `except IdentityAlreadyLinked` handler for `POST /identities/link` — not a
# documented error *code* (it comes back generic `422 validation_error`
# alongside every other body-validation failure), so this is the one signal
# available to tell "already linked, nothing to do" apart from a real
# failure. `test_quiz_thread_identity_link.py` asserts this string against
# the real source, the same way `test_quiz_review_source.py` does for
# `_SOURCE_BY_PLATFORM`.
_ALREADY_LINKED_MESSAGE = "this platform identity is already linked"


def ensure_quiz_thread_identity(client: LearningServiceClient, external_id: str) -> None:
    """Link a `(slack_thread, external_id)` Identity to the person already
    on file under `(slack, external_id)`, so a quiz answer's grading call
    (`quiz_answer_identity` above) resolves instead of 403ing
    `unknown_identity` (AGCTM-69 fix-round 2: `platform=slack_thread` alone
    passes `review.source` through correctly, but `resolve_identity` still
    needs a matching `Identity` row, and roster import only ever creates
    one with `platform="slack"`).

    Uses the two calls already in the frozen `tools.json`
    (`POST /me/link-code` then `POST /identities/link`), keyed off the
    person's existing `slack` identity — never `alt_id`, which
    `resolve_identity` (`identity/service.py`) still filters by `platform`,
    so it cannot bridge `slack` to `slack_thread`.

    Idempotent by tolerance, not a check-first read: calling this again on
    every deploy/reload gets `IdentityAlreadyLinked` (`_ALREADY_LINKED_
    MESSAGE` above) once the link exists from a prior run — treated as
    success, not an error. Any other `LearningServiceError` still raises.
    """
    link_code = client.request(
        "POST", "/me/link-code", identity=ActingIdentity(platform="slack", external_id=external_id)
    )
    try:
        client.request(
            "POST",
            "/identities/link",
            json_body={
                "code": link_code["code"],
                "platform": QUIZ_ANSWER_SOURCE_PLATFORM,
                "external_id": external_id,
            },
        )
    except LearningServiceError as exc:
        if exc.code == "validation_error" and exc.message == _ALREADY_LINKED_MESSAGE:
            return
        raise


@dataclass(frozen=True)
class SourceChip:
    """Names the sprint artifact/thread a quiz question is drawn from
    (spec: "a source chip naming the originating thread ... wired to W3's
    excerpt view" — W3 builds the view this chip points at)."""

    label: str
    thread_ref: str


@dataclass(frozen=True)
class DailyQuestion:
    """The daily question, drawn from a sprint artifact (e.g. the
    `PAY-1863` reverted-migration thread) and backed by a real curriculum
    item — `id` is that item's id, so a tap grades through the normal
    `POST /me/reviews` path instead of a quiz-only shadow record."""

    id: str
    prompt: str
    options: Sequence[str]
    concept_id: str
    source: SourceChip
    kind: str = MCQ_KIND


@dataclass
class QuizSession:
    """One posted-and-not-yet-revealed team quiz. `answers` is `person_id
    -> option index` — read only by `build_reveal`, and only ever surfaced
    there in aggregate. Nothing in this module exposes it any other way.
    """

    question: DailyQuestion
    audience: Sequence[str]  # person_ids expected to answer
    answers: dict = field(default_factory=dict)
    revealed: bool = False

    def answered_count(self) -> int:
        return len(self.answers)

    def audience_size(self) -> int:
        return len(self.audience)


def announcement_kwargs(session: QuizSession) -> dict:
    """The `clarify(...)` call for the daily question (spec §8, via
    `mcq.py`'s own builder) plus the confidence gate the quiz adds on top."""
    kwargs = clarify_kwargs_for_item(
        {"kind": session.question.kind, "prompt": session.question.prompt, "options": session.question.options}
    )
    kwargs["confidence_scale"] = CONFIDENCE_SCALE
    return kwargs


def answered_line(session: QuizSession) -> str:
    """The "N of M answered" line (spec §6) — never who, only how many."""
    return f"{session.answered_count()} of {session.audience_size()} answered"


def source_chip_text(session: QuizSession) -> str:
    chip = session.question.source
    return f"{chip.label} · {chip.thread_ref}"


def record_answer(session: QuizSession, person_id: str, option_index: int, confidence: int) -> None:
    """Store one person's tap. Refuses a non-audience person (never grows
    the "of M" denominator by surprise), a confidence outside 1-5, and any
    tap after the reveal (the reveal is a one-way gate, not a snapshot)."""
    if session.revealed:
        raise ValueError("record_answer: this quiz has already been revealed")
    if person_id not in session.audience:
        raise ValueError(f"record_answer: {person_id!r} is not in this quiz's audience")
    lo, hi = CONFIDENCE_SCALE
    if not lo <= confidence <= hi:
        raise ValueError(f"record_answer: confidence must be {lo}-{hi}, got {confidence!r}")
    session.answers[person_id] = option_index


def submit_quiz_answer(
    client: LearningServiceClient,
    session: QuizSession,
    *,
    person_id: str,
    external_id: str,
    option_index: int,
    confidence: int,
    idempotency_key: str,
) -> dict:
    """Grade the tap through `POST /me/reviews` (the same forwarder
    `tools.py` registers under `learning`), then track it locally for the
    "N of M answered" line and the reveal. Grading happens first: a person
    who answers but whose grading call fails is not counted as answered.

    Always asserts `quiz_answer_identity(external_id)` — never the caller's
    own platform — so `review.source` lands `slack_thread` (module
    docstring); `external_id` is still that person's own chat id (their
    roster `slack_user_id`), just under `QUIZ_ANSWER_SOURCE_PLATFORM`
    instead of their real platform.
    """
    result = client.request(
        "POST",
        "/me/reviews",
        identity=quiz_answer_identity(external_id),
        json_body={
            "item_id": session.question.id,
            "idempotency_key": idempotency_key,
            "response": {"choice": option_index},
        },
    )
    record_answer(session, person_id, option_index, confidence)
    return result


@dataclass(frozen=True)
class LeaderboardEntry:
    display_name: str
    score: int


def build_reveal(
    session: QuizSession,
    *,
    concept_to_schedule: str,
    leaderboard: Sequence[LeaderboardEntry],
) -> dict:
    """The reveal payload: a team-level count per option ("*n* of *m*
    picked X"), one concept named to schedule, and the sprint leaderboard —
    never a name next to an answer, never an individual's wrong answer.
    Marks the session revealed, so no further tap or reveal can land.
    """
    counts = [0] * len(session.question.options)
    for option_index in session.answers.values():
        counts[option_index] += 1
    audience_size = session.audience_size()

    session.revealed = True
    return {
        "options": [
            {"text": text, "count": count, "line": f"{count} of {audience_size} picked {text}"}
            for text, count in zip(session.question.options, counts)
        ],
        "concept_to_schedule": concept_to_schedule,
        "leaderboard": [{"display_name": e.display_name, "score": e.score} for e in leaderboard],
    }


def handle_reveal_command(
    session: QuizSession,
    *,
    requested_by_is_manager: bool,
    concept_to_schedule: str,
    leaderboard: Sequence[LeaderboardEntry],
) -> dict:
    """`/kata-reveal` (AGCTM-69) — presenter-triggered, never a timer:
    refuses a non-manager presenter and a quiz already revealed, otherwise
    returns `build_reveal`'s payload. Wire this into Hermes's own
    slash-command dispatch for `/kata-reveal`.
    """
    if not requested_by_is_manager:
        raise PermissionError("handle_reveal_command: only a manager may trigger /kata-reveal")
    if session.revealed:
        raise ValueError("handle_reveal_command: this quiz has already been revealed")
    return build_reveal(session, concept_to_schedule=concept_to_schedule, leaderboard=leaderboard)
