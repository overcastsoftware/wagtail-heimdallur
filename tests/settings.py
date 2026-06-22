"""Minimal Django settings for running wagtail_heimdallur tests."""

SECRET_KEY = "test-secret-key-not-for-production"

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "wagtail",
    "wagtail_heimdallur",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

USE_TZ = True

STATIC_URL = "/static/"

WAGTAIL_HEIMDALLUR = {
    "FEATURES": {
        "inline_proofreading": True,
        "page_translation": True,
    },
    "BACKENDS": {
        "test": {
            "CLASS": "tests.conftest.DummyBackend",
            "OPTIONS": {},
            "enabled": True,
        },
    },
    "LANGUAGE_ROUTING": {
        "proofreading": {},
        "translation": {},
    },
}
