"""Miðeind Málstaður backend implementation."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

from wagtail_heimdallur.backends.base import (
    BaseProofreadingBackend,
    BaseTranslationBackend,
    TextTranslationStatus,
)
from wagtail_heimdallur.exceptions import (
    AuthenticationError,
    BackendError,
    BackendRequestError,
    BackendTimeoutError,
    UnsupportedLanguageError,
    UnsupportedLanguagePairError,
)
from wagtail_heimdallur.models import DiffAnnotation, ProofreadingResult

logger = logging.getLogger(__name__)


class MideindBackend(BaseProofreadingBackend, BaseTranslationBackend):
    """Backend adapter for Miðeind's Málstaður API."""

    DEFAULT_BASE_URL = "https://api.malstadur.is"
    DEFAULT_TIMEOUT = 30
    DEFAULT_PROOFREADING_LANGUAGES = ("is",)

    def __init__(
        self,
        api_key: str = "",
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        supported_languages: list[str] | None = None,
        supported_language_pairs: list[tuple[str, str]] | None = None,
        **kwargs,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.supported_languages = list(
            supported_languages or self.DEFAULT_PROOFREADING_LANGUAGES
        )
        self.supported_language_pairs = (
            None
            if supported_language_pairs is None
            else [tuple(pair) for pair in supported_language_pairs]
        )
        self.options = kwargs

    def proofread(self, text: str, language: str) -> ProofreadingResult:
        """Send text to Málstaður grammar endpoint and parse corrections."""
        if language not in self.get_supported_languages():
            raise UnsupportedLanguageError(
                f"Miðeind backend does not support proofreading language '{language}'."
            )

        response = self._post(
            "/v1/grammar",
            json={"texts": [text]},
        )
        return self._parse_proofreading_response(response.json())

    def translate(self, text: str, source_language: str, target_language: str) -> str:
        """Translate text with Málstaður translation endpoint."""
        pair = (source_language, target_language)
        if pair not in self.get_supported_language_pairs():
            raise UnsupportedLanguagePairError(
                "Miðeind backend does not support translation pair "
                f"'{source_language}' -> '{target_language}'."
            )

        response = self._post(
            "/v1/translate",
            json={
                "text": text,
                "targetLanguage": target_language,
            },
        )
        data = response.json()
        return self._parse_translation_response(data)

    def start_text_translation(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> str:
        """Start an asynchronous text translation task."""
        pair = (source_language, target_language)
        if pair not in self.get_supported_language_pairs():
            raise UnsupportedLanguagePairError(
                "Miðeind backend does not support translation pair "
                f"'{source_language}' -> '{target_language}'."
            )

        response = self._post(
            "/v1/translate/text",
            json={
                "text": text,
                "targetLanguage": target_language,
            },
        )
        data = response.json()
        error = data.get("error")
        if error:
            raise BackendError(f"Miðeind text translation task failed: {error}")
        task_id = data.get("taskId") or data.get("id")
        if not task_id:
            raise BackendError(
                "Miðeind text translation response did not include a task id. "
                f"Response keys: {', '.join(sorted(data.keys())) or '(none)'}."
            )
        return task_id

    def get_text_translation_status(self, task_id: str) -> TextTranslationStatus:
        """Fetch status for an asynchronous text translation task."""
        response = self._get(f"/v1/translate/text/{quote(task_id)}")
        return self._parse_text_translation_status(response.json(), task_id)

    def get_supported_languages(self) -> list[str]:
        """Return proofreading languages supported by this backend."""
        return self.supported_languages

    def get_supported_language_pairs(self) -> list[tuple[str, str]]:
        """Return translation pairs supported by this backend."""
        if self.supported_language_pairs is None:
            response = self._get("/v1/translate/languages")
            self.supported_language_pairs = self._parse_language_pairs(response.json())

        return self.supported_language_pairs

    def _get(self, path: str) -> httpx.Response:
        url = f"{self.base_url}{path}"
        headers = {}
        if self.api_key:
            headers["X-API-KEY"] = self.api_key

        try:
            logger.debug("GET %s", url)
            response = httpx.get(
                url,
                headers=headers,
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise BackendTimeoutError(
                f"Miðeind request to {url} timed out."
            ) from exc
        except httpx.HTTPError as exc:
            raise BackendError(f"Miðeind request to {url} failed.") from exc

        logger.debug("GET %s returned HTTP %s", url, response.status_code)
        self._raise_for_response(response)
        return response

    def _post(self, path: str, json: dict[str, Any]) -> httpx.Response:
        url = f"{self.base_url}{path}"
        headers = {}
        if self.api_key:
            headers["X-API-KEY"] = self.api_key

        try:
            logger.debug("POST %s", url)
            response = httpx.post(
                url,
                json=json,
                headers=headers,
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise BackendTimeoutError(
                f"Miðeind request to {url} timed out."
            ) from exc
        except httpx.HTTPError as exc:
            raise BackendError(f"Miðeind request to {url} failed.") from exc

        logger.debug("POST %s returned HTTP %s", url, response.status_code)
        self._raise_for_response(response)
        return response

    def _raise_for_response(self, response: httpx.Response) -> None:
        status_code = response.status_code
        if status_code < 400:
            return

        body = response.text
        if status_code in {401, 403}:
            detail = self._error_detail(response)
            if detail:
                raise AuthenticationError(f"Miðeind authentication failed: {detail}")
            raise AuthenticationError(
                "Miðeind API credentials are invalid, missing, or exhausted."
            )
        if status_code == 504:
            raise BackendTimeoutError("Miðeind request timed out.")
        if status_code == 400:
            raise BackendRequestError(f"Miðeind rejected the request: {body}")
        if status_code >= 500:
            raise BackendError("Miðeind API returned a server-side error.")

        raise BackendError(
            f"Miðeind API returned unexpected HTTP status {status_code}: {body}"
        )

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return response.text

        detail = data.get("error") or data.get("message") or data.get("details")
        if isinstance(detail, str):
            return detail
        if detail:
            return str(detail)
        return ""

    @classmethod
    def _parse_proofreading_response(cls, data: dict[str, Any]) -> ProofreadingResult:
        """Parse a Málstaður grammar response into a ProofreadingResult."""
        if "results" in data:
            results = data.get("results") or []
            if not results:
                raise BackendError(
                    "Miðeind grammar response did not include any results."
                )
            data = results[0]

        annotations = [
            cls._parse_annotation(annotation)
            for annotation in data.get(
                "diffAnnotations",
                data.get("annotations", []),
            )
        ]
        return ProofreadingResult(
            original_text=data.get("originalText", data.get("original_text", "")),
            corrected_text=data.get("changedText", data.get("corrected_text", "")),
            annotations=annotations,
        )

    @staticmethod
    def _parse_annotation(data: dict[str, Any]) -> DiffAnnotation:
        return DiffAnnotation(
            orig_start_idx=data["origStartIdx"],
            orig_end_idx=data["origEndIdx"],
            orig_string=data["origString"],
            changed_start_idx=data["changedStartIdx"],
            changed_end_idx=data["changedEndIdx"],
            changed_string=data["changedString"],
            change_type=data["changeType"],
        )

    @staticmethod
    def _parse_translation_response(data: dict[str, Any]) -> str:
        for key in ("text", "translatedText", "translated_text", "translation"):
            if key in data:
                value = data[key]
                if isinstance(value, str):
                    return value
                raise BackendError(
                    "Miðeind translation response field "
                    f"'{key}' was not a string."
                )

        raise BackendError(
            "Miðeind translation response did not include translated text. "
            f"Response keys: {', '.join(sorted(data.keys())) or '(none)'}."
        )

    @staticmethod
    def _parse_text_translation_status(
        data: dict[str, Any],
        fallback_task_id: str,
    ) -> TextTranslationStatus:
        result = data.get("result") or {}
        text = result.get("text") if isinstance(result, dict) else None
        return TextTranslationStatus(
            task_id=data.get("taskId", fallback_task_id),
            status=data.get("status", "not_found"),
            progress=data.get("progress", 0),
            text=text,
            error=data.get("error"),
            message=data.get("message"),
        )

    @staticmethod
    def _parse_language_pairs(data: Any) -> list[tuple[str, str]]:
        raw_pairs = data
        if isinstance(data, dict):
            raw_pairs = data.get("languagePairs", data.get("language_pairs", []))

        return [
            MideindBackend._normalize_language_pair(pair)
            for pair in raw_pairs
        ]

    @staticmethod
    def _normalize_language_pair(pair: Any) -> tuple[str, str]:
        if isinstance(pair, dict):
            return (
                pair.get("sourceLanguage", pair.get("source_language")),
                pair.get("targetLanguage", pair.get("target_language")),
            )

        source_language, target_language = pair
        return (source_language, target_language)
