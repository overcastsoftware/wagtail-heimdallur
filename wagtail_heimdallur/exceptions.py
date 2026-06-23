"""Custom exception hierarchy for Wagtail-Heimdallur."""


class BackendError(Exception):
    """Base exception for all backend errors."""

    pass


class AuthenticationError(BackendError):
    """Raised when API credentials are invalid or exhausted."""

    pass


class BackendTimeoutError(BackendError):
    """Raised when a backend request exceeds the configured timeout."""

    pass


class BackendRequestError(BackendError):
    """Raised when the backend returns HTTP 400 (bad request)."""

    pass


class RateLimitError(BackendError):
    """Raised when the backend rate-limits the request (HTTP 429).

    This is transient: the same request can succeed once the limit window has
    passed, so callers may retry the job later.
    """

    pass


class UnsupportedLanguageError(BackendError):
    """Raised when no backend supports the requested language/pair."""

    pass


class UnsupportedLanguagePairError(UnsupportedLanguageError):
    """Raised when a specific language pair is not available."""

    pass


class NoAvailableBackendError(BackendError):
    """Raised when all backends for an operation are disabled."""

    pass
