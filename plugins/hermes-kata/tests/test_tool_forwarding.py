"""KATA-24 (issue G1): a resolved `submit_review` answer to a tracked
team-quiz item is sent with `platform="slack_thread"` — already a valid
enum value in the frozen contract, so the core's own `source` fallback
writes `source = slack_thread` for it, no contract change — and every
accepted response feeds the team-quiz tally. Every other tool call, and a
`submit_review` call against a non-quiz item, is unaffected."""
from conftest import FakeSessionStore

from hermes_kata.forwarder import make_forwarder
from hermes_kata.quiz import TeamQuizItemRegistry
from hermes_kata.reveal import QuizTally, record_submit_review


class FakeSubmitReviewClient:
    def __init__(self):
        self.sent = None

    def request(self, method, path, identity, payload):
        self.sent = {"method": method, "path": path, "identity": identity, "payload": payload}

        class _Response:
            error_code = None
            data = {"grade": 1.0}

        return _Response()


def _session_store_with(person):
    store = FakeSessionStore()
    store.set("sess-1", "kata_person", person)
    return store


def test_a_quiz_item_answer_is_sent_with_platform_slack_thread():
    client = FakeSubmitReviewClient()
    registry = TeamQuizItemRegistry()
    registry.mark(["lm-1", "lm-2"])
    handler = make_forwarder(client, "POST", "/me/reviews", is_quiz_item=registry.is_quiz_item)

    handler(
        _session_store_with({"id": "person-1", "platform": "slack", "external_id": "U1"}),
        "sess-1",
        item_id="lm-1",
        idempotency_key="key-1",
        response={"choice": 2},
    )

    assert client.sent["identity"] == "slack_thread:U1"


def test_a_non_quiz_item_answer_keeps_the_learners_own_platform():
    client = FakeSubmitReviewClient()
    registry = TeamQuizItemRegistry()
    registry.mark(["lm-1", "lm-2"])
    handler = make_forwarder(client, "POST", "/me/reviews", is_quiz_item=registry.is_quiz_item)

    handler(
        _session_store_with({"id": "person-1", "platform": "slack", "external_id": "U1"}),
        "sess-1",
        item_id="some-other-item",
        idempotency_key="key-2",
        response={"choice": 1},
    )

    assert client.sent["identity"] == "slack:U1"


def test_other_tools_are_unaffected_by_is_quiz_item():
    client = FakeSubmitReviewClient()
    registry = TeamQuizItemRegistry()
    registry.mark(["lm-1"])
    handler = make_forwarder(client, "GET", "/me/next", is_quiz_item=registry.is_quiz_item)

    handler(_session_store_with({"id": "person-1", "platform": "slack", "external_id": "U1"}), "sess-1", limit=5)

    assert client.sent["identity"] == "slack:U1"


def test_on_review_feeds_an_accepted_response_into_the_tally():
    client = FakeSubmitReviewClient()
    tally = QuizTally()
    seen = []

    def on_review(item_id, response, *, person_name=None):
        seen.append((item_id, response, person_name))
        record_submit_review(tally, item_id, response)

    handler = make_forwarder(client, "POST", "/me/reviews", on_review=on_review)

    handler(
        _session_store_with({"id": "person-1", "display_name": "Hugo", "platform": "slack", "external_id": "U1"}),
        "sess-1",
        item_id="lm-1",
        idempotency_key="key-1",
        response={"choice": 2},
    )

    assert seen == [("lm-1", {"choice": 2}, "Hugo")]
    assert tally.counts_for("lm-1") == {2: 1}


def test_on_review_is_not_called_when_the_core_rejects_the_submission():
    class RejectingClient(FakeSubmitReviewClient):
        def request(self, method, path, identity, payload):
            class _Response:
                error_code = "not_a_manager"
                data = None

            return _Response()

    calls = []
    handler = make_forwarder(RejectingClient(), "POST", "/me/reviews", on_review=lambda *a, **k: calls.append(a))

    handler(
        _session_store_with({"id": "person-1", "platform": "slack", "external_id": "U1"}),
        "sess-1",
        item_id="lm-1",
        idempotency_key="key-1",
        response={"choice": 2},
    )

    assert calls == []
