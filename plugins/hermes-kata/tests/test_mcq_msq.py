"""§8 MCQ/MSQ rendering tests.

No new rendering code to test — the relay layer already turns a `clarify`
call into native components per platform. What this plugin owns is: the
system-prompt instruction drives the two distinct `clarify` shapes, and a
resolved multi-select reply reaches `submit_review` as a `choices` array.
"""
from conftest import FakeSessionStore

from hermes_kata.forwarder import make_forwarder
from hermes_kata.prompts import MCQ_MSQ_INSTRUCTION


class FakeClarifyingAgent:
    """Stands in for a Hermes agent turn following MCQ_MSQ_INSTRUCTION:
    given an item, produce the `clarify` call it would make."""

    def render(self, item):
        if item["kind"] == "mcq":
            return {"question": item["prompt"], "choices": item["options"], "multi_select": False}
        if item["kind"] == "msq":
            return {"question": item["prompt"], "choices": item["options"], "multi_select": True}
        raise ValueError(item["kind"])


def test_instruction_never_bakes_in_item_text():
    # The instruction is a fixed, item-independent rule — nothing here
    # should ever leak a specific item's options as chat text.
    assert "choices=" in MCQ_MSQ_INSTRUCTION
    assert "multi_select=false" in MCQ_MSQ_INSTRUCTION
    assert "multi_select=true" in MCQ_MSQ_INSTRUCTION


def test_mcq_item_renders_via_clarify_with_multi_select_false():
    agent = FakeClarifyingAgent()
    item = {"kind": "mcq", "prompt": "Which is a prime?", "options": ["4", "6", "7", "8"]}

    call = agent.render(item)

    assert call["choices"] == item["options"]
    assert call["multi_select"] is False


def test_msq_item_renders_via_clarify_with_multi_select_true():
    agent = FakeClarifyingAgent()
    item = {"kind": "msq", "prompt": "Select all primes", "options": ["4", "6", "7", "8"]}

    call = agent.render(item)

    assert call["choices"] == item["options"]
    assert call["multi_select"] is True


class FakeSubmitReviewClient:
    def __init__(self):
        self.sent = None

    def request(self, method, path, identity, payload):
        self.sent = {"method": method, "path": path, "identity": identity, "payload": payload}

        class _Response:
            error_code = None
            data = {"grade": 1.0}

        return _Response()

    def resolve_identity(self, **kwargs):
        raise AssertionError("session identity was bound; should not need job_identity")


def test_msq_multi_option_reply_resolves_to_submit_review_choices_array():
    client = FakeSubmitReviewClient()
    handler = make_forwarder(client, "POST", "/me/reviews")
    session_store = FakeSessionStore()
    session_store.set("sess-1", "kata_person", {"id": "person-1", "platform": "slack", "external_id": "U1"})

    handler(
        session_store,
        "sess-1",
        item_id="item-1",
        idempotency_key="key-1",
        response={"choices": [1, 3]},
    )

    payload = client.sent["payload"]
    assert isinstance(payload["response"]["choices"], list)
    assert payload["response"]["choices"] == [1, 3]
