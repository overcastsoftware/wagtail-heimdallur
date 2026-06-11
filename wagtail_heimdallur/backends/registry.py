"""Backend registry and language routing."""

from dataclasses import dataclass
from typing import Any, Iterable

from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from wagtail_heimdallur.backends.base import (
    BaseProofreadingBackend,
    BaseTranslationBackend,
)
from wagtail_heimdallur.exceptions import (
    NoAvailableBackendError,
    UnsupportedLanguageError,
)


@dataclass(frozen=True)
class _BackendEntry:
    """A configured backend instance and routing metadata."""

    identifier: str
    backend: object
    enabled: bool


class BackendRegistry:
    """Manages backend instances and language routing."""

    def __init__(self, settings: dict):
        self._backends: dict[str, _BackendEntry] = {}
        self._routing: dict = settings.get("LANGUAGE_ROUTING", {})
        self._load_backends(settings)

    def _load_backends(self, settings: dict) -> None:
        """Dynamically import and instantiate configured backends."""
        for identifier, config in settings.get("BACKENDS", {}).items():
            class_path = config.get("CLASS")
            if not class_path:
                raise ImproperlyConfigured(
                    f"Backend '{identifier}' must define a CLASS path."
                )

            try:
                backend_class = import_string(class_path)
            except ImportError as exc:
                raise ImproperlyConfigured(
                    f"Could not import backend class '{class_path}' "
                    f"for backend '{identifier}'."
                ) from exc

            options = config.get("OPTIONS", {})
            backend = backend_class(**options)
            self._backends[identifier] = _BackendEntry(
                identifier=identifier,
                backend=backend,
                enabled=config.get("enabled", True),
            )

    def get_backend_for_proofreading(self, language: str) -> BaseProofreadingBackend:
        """Resolve a proofreading backend for the requested language."""
        routed_backend_id = self._routing.get("proofreading", {}).get(language)
        routed_entry = self._get_routed_entry(routed_backend_id)

        if routed_entry and self._entry_supports_proofreading(routed_entry, language):
            if routed_entry.enabled:
                return routed_entry.backend
            return self._fallback_or_raise_for_proofreading(language)

        return self._fallback_or_raise_for_proofreading(language)

    def get_backend_for_translation(
        self, source_language: str, target_language: str
    ) -> BaseTranslationBackend:
        """Resolve a translation backend for the requested language pair."""
        pair = (source_language, target_language)
        routed_backend_id = self._get_translation_route(source_language, target_language)
        routed_entry = self._get_routed_entry(routed_backend_id)

        if routed_entry and self._entry_supports_translation(routed_entry, pair):
            if routed_entry.enabled:
                return routed_entry.backend
            return self._fallback_or_raise_for_translation(pair)

        return self._fallback_or_raise_for_translation(pair)

    def _get_routed_entry(self, backend_id: str | None) -> _BackendEntry | None:
        if backend_id is None:
            return None

        try:
            return self._backends[backend_id]
        except KeyError as exc:
            raise ImproperlyConfigured(
                f"Language routing references unknown backend '{backend_id}'."
            ) from exc

    def _get_translation_route(
        self, source_language: str, target_language: str
    ) -> str | None:
        routes = self._routing.get("translation", {})
        route_keys: Iterable[Any] = (
            (source_language, target_language),
            f"{source_language}:{target_language}",
            f"{source_language}->{target_language}",
        )
        for key in route_keys:
            if key in routes:
                return routes[key]
        return None

    def _fallback_or_raise_for_proofreading(
        self, language: str
    ) -> BaseProofreadingBackend:
        for entry in self._backends.values():
            if entry.enabled and self._entry_supports_proofreading(entry, language):
                return entry.backend

        if any(
            self._entry_supports_proofreading(entry, language)
            for entry in self._backends.values()
        ):
            raise NoAvailableBackendError(
                f"All proofreading backends supporting language '{language}' "
                "are disabled."
            )

        raise UnsupportedLanguageError(
            f"No proofreading backend supports language '{language}'."
        )

    def _fallback_or_raise_for_translation(
        self, pair: tuple[str, str]
    ) -> BaseTranslationBackend:
        source_language, target_language = pair
        for entry in self._backends.values():
            if entry.enabled and self._entry_supports_translation(entry, pair):
                return entry.backend

        if any(
            self._entry_supports_translation(entry, pair)
            for entry in self._backends.values()
        ):
            raise NoAvailableBackendError(
                "All translation backends supporting language pair "
                f"'{source_language}' -> '{target_language}' are disabled."
            )

        raise UnsupportedLanguageError(
            "No translation backend supports language pair "
            f"'{source_language}' -> '{target_language}'."
        )

    def _entry_supports_proofreading(
        self, entry: _BackendEntry, language: str
    ) -> bool:
        backend = entry.backend
        return (
            isinstance(backend, BaseProofreadingBackend)
            and language in backend.get_supported_languages()
        )

    def _entry_supports_translation(
        self, entry: _BackendEntry, pair: tuple[str, str]
    ) -> bool:
        backend = entry.backend
        if not isinstance(backend, BaseTranslationBackend):
            return False

        supported_pairs = {
            tuple(supported_pair)
            for supported_pair in backend.get_supported_language_pairs()
        }
        return pair in supported_pairs
