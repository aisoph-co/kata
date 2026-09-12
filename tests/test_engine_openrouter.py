"""Unit tests for `OpenRouterClient`'s request/response contract, using
`httpx.MockTransport` so no network call is made (spec §Learning engine,
"short_answer graded via OpenRouter")."""

import json

import httpx
import pytest

from learning_service.engine.openrouter import DEFAULT_MODEL, GradingError, OpenRouterClient

_RealAsyncClient = httpx.AsyncClient


def _mock_async_client(handler):
    def factory(**kwargs):
        kwargs.pop("transport", None)
        return _RealAsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


async def test_missing_api_key_raises_grading_error():
    client = OpenRouterClient(api_key="")
    with pytest.raises(GradingError):
        await client.grade(prompt="p", reference="r", rubric="ru", response_text="t")


def test_default_model_unchanged_without_env(monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    client = OpenRouterClient(api_key="k")
    assert client._model == DEFAULT_MODEL == "openai/gpt-4o-mini"


def test_openrouter_model_env_is_respected(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-5.6-luna")
    client = OpenRouterClient(api_key="k")
    assert client._model == "openai/gpt-5.6-luna"


def test_explicit_model_argument_wins_over_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-5.6-luna")
    client = OpenRouterClient(api_key="k", model="explicit/model")
    assert client._model == "explicit/model"


async def test_grade_parses_json_content_and_clamps_to_unit_interval(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body["messages"][1]["content"].startswith("Question: ")
        content = json.dumps({"grade": 1.5, "explanation": "over full credit, clamps to 1.0"})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(httpx, "AsyncClient", _mock_async_client(handler))

    client = OpenRouterClient(api_key="test-key")
    grade, explanation = await client.grade(prompt="p", reference="r", rubric="ru", response_text="t")
    assert grade == 1.0
    assert explanation == "over full credit, clamps to 1.0"


async def test_grade_raises_grading_error_on_unparseable_content(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

    monkeypatch.setattr(httpx, "AsyncClient", _mock_async_client(handler))

    client = OpenRouterClient(api_key="test-key")
    with pytest.raises(GradingError):
        await client.grade(prompt="p", reference="r", rubric="ru", response_text="t")
