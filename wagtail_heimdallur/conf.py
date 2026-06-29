"""Settings access and defaults for Wagtail-Heimdallur."""

from django.conf import settings

DEFAULTS = {
    "FEATURES": {
        "inline_proofreading": True,
        "page_translation": True,
    },
    "BACKENDS": {},
    "LANGUAGE_ROUTING": {
        "proofreading": {},
        "translation": {},
    },
    "PAGE_TRANSLATION": {
        # Which locales are treated as translation sources. This gates where the
        # "Publish & update translations" page action appears. None means "only
        # the site default locale", which keeps a translation from being
        # machine-translated back onto its original.
        "source_locales": None,
    },
}


def get_settings() -> dict:
    """Read WAGTAIL_HEIMDALLUR from Django settings and apply defaults.

    Missing feature toggles default to True (enabled).
    """
    user_settings = getattr(settings, "WAGTAIL_HEIMDALLUR", {})

    merged = {
        **DEFAULTS,
        **user_settings,
    }

    # Merge FEATURES with defaults — missing toggles default to True
    user_features = user_settings.get("FEATURES", {})
    merged["FEATURES"] = {
        **DEFAULTS["FEATURES"],
        **user_features,
    }

    # Merge LANGUAGE_ROUTING with defaults
    user_routing = user_settings.get("LANGUAGE_ROUTING", {})
    merged["LANGUAGE_ROUTING"] = {
        "proofreading": user_routing.get(
            "proofreading", DEFAULTS["LANGUAGE_ROUTING"]["proofreading"]
        ),
        "translation": user_routing.get(
            "translation", DEFAULTS["LANGUAGE_ROUTING"]["translation"]
        ),
    }

    # Merge PAGE_TRANSLATION with defaults
    merged["PAGE_TRANSLATION"] = {
        **DEFAULTS["PAGE_TRANSLATION"],
        **user_settings.get("PAGE_TRANSLATION", {}),
    }

    return merged
