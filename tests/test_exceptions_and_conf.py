"""Unit tests for exception hierarchy and conf module.

Validates:
- Requirement 8.1: THE Plugin SHALL define a base BackendError exception class
  from which all backend-specific exceptions inherit
- Requirement 1.9: WHEN a Feature_Toggle is not explicitly set in the
  Settings_Dictionary, THE Plugin SHALL default that feature to enabled
"""

import pytest

from wagtail_heimdallur.exceptions import (
    AuthenticationError,
    BackendError,
    BackendRequestError,
    BackendTimeoutError,
    NoAvailableBackendError,
    UnsupportedLanguageError,
    UnsupportedLanguagePairError,
)


# ---------------------------------------------------------------------------
# Requirement 8.1: Exception hierarchy — all exceptions inherit from BackendError
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    """All backend-specific exceptions must inherit from BackendError."""

    @pytest.mark.parametrize(
        "exc_class",
        [
            AuthenticationError,
            BackendTimeoutError,
            BackendRequestError,
            UnsupportedLanguageError,
            UnsupportedLanguagePairError,
            NoAvailableBackendError,
        ],
    )
    def test_inherits_from_backend_error(self, exc_class):
        assert issubclass(exc_class, BackendError)

    @pytest.mark.parametrize(
        "exc_class",
        [
            AuthenticationError,
            BackendTimeoutError,
            BackendRequestError,
            UnsupportedLanguageError,
            UnsupportedLanguagePairError,
            NoAvailableBackendError,
        ],
    )
    def test_instance_is_backend_error(self, exc_class):
        instance = exc_class("test message")
        assert isinstance(instance, BackendError)

    def test_unsupported_language_pair_inherits_from_unsupported_language(self):
        """UnsupportedLanguagePairError is a specialization of UnsupportedLanguageError."""
        assert issubclass(UnsupportedLanguagePairError, UnsupportedLanguageError)
        instance = UnsupportedLanguagePairError("en-xx")
        assert isinstance(instance, UnsupportedLanguageError)

    def test_backend_error_is_exception(self):
        """BackendError itself inherits from the built-in Exception."""
        assert issubclass(BackendError, Exception)

    def test_exceptions_can_carry_messages(self):
        """All exception classes preserve a descriptive message."""
        msg = "something went wrong"
        for exc_class in (
            BackendError,
            AuthenticationError,
            BackendTimeoutError,
            BackendRequestError,
            UnsupportedLanguageError,
            UnsupportedLanguagePairError,
            NoAvailableBackendError,
        ):
            exc = exc_class(msg)
            assert str(exc) == msg


# ---------------------------------------------------------------------------
# Requirement 1.9: get_settings() applies feature toggle defaults
# ---------------------------------------------------------------------------


class TestGetSettingsDefaults:
    """get_settings() must default missing feature toggles to True."""

    def test_defaults_when_no_setting_exists(self, settings):
        """When WAGTAIL_HEIMDALLUR is missing entirely, all features default to True."""
        # Remove the setting entirely
        if hasattr(settings, "WAGTAIL_HEIMDALLUR"):
            delattr(settings, "WAGTAIL_HEIMDALLUR")

        from wagtail_heimdallur.conf import get_settings

        result = get_settings()

        assert result["FEATURES"]["inline_proofreading"] is True
        assert result["FEATURES"]["page_translation"] is True

    def test_defaults_when_features_key_missing(self, settings):
        """When FEATURES key is absent, all features default to True."""
        settings.WAGTAIL_HEIMDALLUR = {
            "BACKENDS": {"test": {"CLASS": "some.Backend"}},
        }

        from wagtail_heimdallur.conf import get_settings

        result = get_settings()

        assert result["FEATURES"]["inline_proofreading"] is True
        assert result["FEATURES"]["page_translation"] is True

    def test_missing_toggle_defaults_to_true(self, settings):
        """When only some features are set, missing ones default to True."""
        settings.WAGTAIL_HEIMDALLUR = {
            "FEATURES": {
                "inline_proofreading": False,
                # page_translation is NOT set
            },
        }

        from wagtail_heimdallur.conf import get_settings

        result = get_settings()

        # Explicitly set feature is respected
        assert result["FEATURES"]["inline_proofreading"] is False
        # Missing features default to True
        assert result["FEATURES"]["page_translation"] is True

    def test_all_features_explicitly_disabled(self, settings):
        """When all features are explicitly disabled, they remain disabled."""
        settings.WAGTAIL_HEIMDALLUR = {
            "FEATURES": {
                "inline_proofreading": False,
                "page_translation": False,
            },
        }

        from wagtail_heimdallur.conf import get_settings

        result = get_settings()

        assert result["FEATURES"]["inline_proofreading"] is False
        assert result["FEATURES"]["page_translation"] is False

    def test_backends_preserved_from_user_settings(self, settings):
        """User BACKENDS config is preserved in the merged result."""
        settings.WAGTAIL_HEIMDALLUR = {
            "BACKENDS": {
                "mideind": {
                    "CLASS": "wagtail_heimdallur.backends.mideind.MideindBackend",
                    "OPTIONS": {"api_key": "secret"},
                },
            },
        }

        from wagtail_heimdallur.conf import get_settings

        result = get_settings()

        assert "mideind" in result["BACKENDS"]
        assert result["BACKENDS"]["mideind"]["OPTIONS"]["api_key"] == "secret"

    def test_language_routing_defaults(self, settings):
        """When LANGUAGE_ROUTING is missing, defaults are empty dicts."""
        settings.WAGTAIL_HEIMDALLUR = {}

        from wagtail_heimdallur.conf import get_settings

        result = get_settings()

        assert result["LANGUAGE_ROUTING"]["proofreading"] == {}
        assert result["LANGUAGE_ROUTING"]["translation"] == {}

    def test_language_routing_merges_with_defaults(self, settings):
        """User LANGUAGE_ROUTING entries are preserved."""
        settings.WAGTAIL_HEIMDALLUR = {
            "LANGUAGE_ROUTING": {
                "proofreading": {"is": "mideind"},
            },
        }

        from wagtail_heimdallur.conf import get_settings

        result = get_settings()

        assert result["LANGUAGE_ROUTING"]["proofreading"] == {"is": "mideind"}
        assert result["LANGUAGE_ROUTING"]["translation"] == {}
