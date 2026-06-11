"""Tests for Wagtail-Heimdallur AppConfig."""

import wagtail_heimdallur

from wagtail_heimdallur.apps import WagtailHeimdallurConfig


def test_app_config_ready_validates_initializes_registry_and_registers_hooks(monkeypatch):
    calls = []
    config = {
        "BACKENDS": {
            "test": {
                "CLASS": "tests.test_backends.fakes.FakeCombinedBackend",
                "OPTIONS": {},
            },
        },
        "FEATURES": {},
        "LANGUAGE_ROUTING": {
            "proofreading": {},
            "translation": {},
        },
    }

    class Validator:
        def validate(self, settings):
            calls.append(("validate", settings))

    class Registry:
        def __init__(self, settings):
            calls.append(("registry", settings))

    def register_hooks(settings):
        calls.append(("hooks", settings))

    monkeypatch.setattr("wagtail_heimdallur.apps.get_settings", lambda: config)
    monkeypatch.setattr("wagtail_heimdallur.apps.ConfigurationValidator", Validator)
    monkeypatch.setattr("wagtail_heimdallur.apps.BackendRegistry", Registry)
    monkeypatch.setattr("wagtail_heimdallur.apps.register_heimdallur_hooks", register_hooks)

    app_config = WagtailHeimdallurConfig("wagtail_heimdallur", wagtail_heimdallur)
    app_config.ready()

    assert calls == [
        ("validate", config),
        ("registry", config),
        ("hooks", config),
    ]
