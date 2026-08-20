"""Tests for the Miðeind Málstaður backend."""

import json

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from wagtail_heimdallur.backends.mideind import MideindBackend
from wagtail_heimdallur.exceptions import (
    AuthenticationError,
    BackendError,
    BackendRequestError,
    BackendTimeoutError,
    RateLimitError,
    UnsupportedLanguagePairError,
)


BASE_URL = "https://malstadur.test"


def mideind_backend(**kwargs):
    return MideindBackend(
        api_key="test-key",
        base_url=BASE_URL,
        supported_language_pairs=[("is", "en")],
        **kwargs,
    )


camel_annotation_strategy = st.fixed_dictionaries(
    {
        "origStartIdx": st.integers(min_value=0, max_value=1000),
        "origEndIdx": st.integers(min_value=0, max_value=1200),
        "origString": st.text(max_size=50),
        "changedStartIdx": st.integers(min_value=0, max_value=1000),
        "changedEndIdx": st.integers(min_value=0, max_value=1200),
        "changedString": st.text(max_size=50),
        "changeType": st.sampled_from(
            ["spelling", "grammar", "style", "punctuation"]
        ),
    }
).filter(
    lambda annotation: annotation["origStartIdx"] <= annotation["origEndIdx"]
    and annotation["changedStartIdx"] <= annotation["changedEndIdx"]
)


@given(
    original_text=st.text(max_size=200),
    changed_text=st.text(max_size=200),
    annotations=st.lists(camel_annotation_strategy, max_size=20),
)
@settings(max_examples=50)
def test_malstadur_response_parsing_preserves_all_annotations(
    original_text,
    changed_text,
    annotations,
):
    """Property 11: Málstaður response parsing preserves all annotations."""
    result = MideindBackend._parse_proofreading_response(
        {
            "results": [
                {
                    "originalText": original_text,
                    "changedText": changed_text,
                    "diffAnnotations": annotations,
                }
            ],
        }
    )

    assert result.original_text == original_text
    assert result.corrected_text == changed_text
    assert len(result.annotations) == len(annotations)

    for parsed, raw in zip(result.annotations, annotations):
        assert parsed.orig_start_idx == raw["origStartIdx"]
        assert parsed.orig_end_idx == raw["origEndIdx"]
        assert parsed.orig_string == raw["origString"]
        assert parsed.changed_start_idx == raw["changedStartIdx"]
        assert parsed.changed_end_idx == raw["changedEndIdx"]
        assert parsed.changed_string == raw["changedString"]
        assert parsed.change_type == raw["changeType"]


def test_proofread_posts_to_grammar_endpoint_with_api_key(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/grammar",
        json={
            "results": [
                {
                    "originalText": "halló heimur",
                    "changedText": "halló heimur",
                    "diffAnnotations": [],
                }
            ],
        },
    )

    result = mideind_backend().proofread("halló heimur", "is")
    request = httpx_mock.get_request()

    assert result.original_text == "halló heimur"
    assert request.headers["X-API-KEY"] == "test-key"
    assert request.url == f"{BASE_URL}/v1/grammar"
    assert json.loads(request.content) == {"texts": ["halló heimur"]}


def test_malstadur_legacy_proofreading_response_shape_still_parses():
    result = MideindBackend._parse_proofreading_response(
        {
            "originalText": "halló",
            "changedText": "Halló",
            "annotations": [
                {
                    "origStartIdx": 0,
                    "origEndIdx": 1,
                    "origString": "h",
                    "changedStartIdx": 0,
                    "changedEndIdx": 1,
                    "changedString": "H",
                    "changeType": "capitalization",
                }
            ],
        }
    )

    assert result.corrected_text == "Halló"
    assert result.annotations[0].changed_string == "H"


def test_translate_posts_to_translate_endpoint(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/translate",
        json={"translatedText": "hello"},
    )

    result = mideind_backend().translate("halló", "is", "en")
    request = httpx_mock.get_request()

    assert result == "hello"
    assert request.headers["X-API-KEY"] == "test-key"
    assert request.url == f"{BASE_URL}/v1/translate"
    assert json.loads(request.content) == {
        "text": "halló",
        "targetLanguage": "en",
    }


def test_translate_accepts_empty_translated_text(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/translate",
        json={"translatedText": ""},
    )

    assert mideind_backend().translate("halló", "is", "en") == ""


def test_translate_rejects_unexpected_response_shape(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/translate",
        json={"taskId": "abc123"},
    )

    with pytest.raises(BackendError, match="taskId"):
        mideind_backend().translate("halló", "is", "en")


def test_start_text_translation_posts_text_and_returns_task_id(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/translate/text",
        status_code=201,
        json={
            "taskId": "task-123",
            "error": None,
            "estimatedUsage": {
                "units": 5,
                "unitType": "characters",
                "cost": 1,
            },
        },
    )

    task_id = mideind_backend().start_text_translation(
        "halló",
        "is",
        "en",
    )
    request = httpx_mock.get_request()

    assert task_id == "task-123"
    assert request.url == f"{BASE_URL}/v1/translate/text"
    assert json.loads(request.content) == {
        "text": "halló",
        "targetLanguage": "en",
    }


def test_get_text_translation_status_parses_completed_text(httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/translate/text/task-123",
        json={
            "taskId": "task-123",
            "status": "completed",
            "progress": 100,
            "error": None,
            "message": None,
            "result": {
                "text": "hello",
                "targetLanguage": "en",
            },
        },
    )

    status = mideind_backend().get_text_translation_status("task-123")

    assert status.task_id == "task-123"
    assert status.status == "completed"
    assert status.text == "hello"


def test_get_supported_language_pairs_queries_api_when_not_configured(httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/v1/translate/languages",
        json={
            "languagePairs": [
                {
                    "sourceLanguage": "is",
                    "targetLanguage": "en",
                },
                {
                    "sourceLanguage": "en",
                    "targetLanguage": "is",
                },
            ],
        },
    )
    backend = MideindBackend(api_key="test-key", base_url=BASE_URL)

    assert backend.get_supported_language_pairs() == [("is", "en"), ("en", "is")]
    assert backend.get_supported_language_pairs() == [("is", "en"), ("en", "is")]
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.parametrize("status_code", [401, 403])
def test_authentication_errors_raise_authentication_error(httpx_mock, status_code):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/grammar",
        status_code=status_code,
    )

    with pytest.raises(AuthenticationError):
        mideind_backend().proofread("text", "is")


def test_authentication_errors_include_api_error_detail(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/grammar",
        status_code=403,
        json={"error": "Insufficient permissions"},
    )

    with pytest.raises(AuthenticationError, match="Insufficient permissions"):
        mideind_backend().proofread("text", "is")


def test_504_raises_backend_timeout_error(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/grammar",
        status_code=504,
    )

    with pytest.raises(BackendTimeoutError):
        mideind_backend().proofread("text", "is")


def test_request_timeout_raises_backend_timeout_error(httpx_mock):
    httpx_mock.add_exception(
        httpx.TimeoutException("timed out"),
        method="POST",
        url=f"{BASE_URL}/v1/grammar",
    )

    with pytest.raises(BackendTimeoutError):
        mideind_backend(timeout=0.01).proofread("text", "is")


def test_429_raises_rate_limit_error_when_retries_exhausted(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/grammar",
        status_code=429,
    )

    with pytest.raises(RateLimitError):
        mideind_backend(rate_limit_retries=0).proofread("text", "is")


def test_429_retries_then_succeeds(httpx_mock):
    # Retry-After: 0 keeps the retry instant.
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/translate/text",
        status_code=429,
        headers={"Retry-After": "0"},
    )
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/translate/text",
        status_code=201,
        json={"taskId": "task-1"},
    )

    backend = mideind_backend(rate_limit_retries=2)
    task_id = backend.start_text_translation("halló", "is", "en")

    assert task_id == "task-1"
    assert len(httpx_mock.get_requests()) == 2


def test_400_raises_backend_request_error(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/grammar",
        status_code=400,
        text="bad request",
    )

    with pytest.raises(BackendRequestError):
        mideind_backend().proofread("text", "is")


def test_500_raises_backend_error_with_status_url_and_body(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/grammar",
        status_code=503,
        text="upstream translation engine unavailable",
    )

    with pytest.raises(BackendError) as excinfo:
        mideind_backend().proofread("text", "is")

    message = str(excinfo.value)
    assert "HTTP 503" in message
    assert "/v1/grammar" in message
    assert "upstream translation engine unavailable" in message


def test_500_with_empty_body_still_reports_status(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/v1/grammar",
        status_code=500,
    )

    with pytest.raises(BackendError, match="HTTP 500"):
        mideind_backend().proofread("text", "is")


def test_unsupported_language_pair_raises_without_http_request(httpx_mock):
    with pytest.raises(UnsupportedLanguagePairError):
        mideind_backend().translate("halló", "is", "de")

    assert not httpx_mock.get_requests()
