"""Django application configuration for Wagtail-Heimdallur."""

from django.apps import AppConfig

backend_registry = None


def get_settings():
    from wagtail_heimdallur.conf import get_settings as get_heimdallur_settings

    return get_heimdallur_settings()


class ConfigurationValidator:
    def __new__(cls, *args, **kwargs):
        from wagtail_heimdallur.validators import ConfigurationValidator as Validator

        return Validator(*args, **kwargs)


class BackendRegistry:
    def __new__(cls, *args, **kwargs):
        from wagtail_heimdallur.backends import BackendRegistry as Registry

        return Registry(*args, **kwargs)


def register_heimdallur_hooks(settings):
    from wagtail_heimdallur.hooks import register_heimdallur_hooks as register_hooks

    return register_hooks(settings)


class WagtailHeimdallurConfig(AppConfig):
    """Validate configuration and register Wagtail hooks at startup."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "wagtail_heimdallur"
    verbose_name = "Wagtail Heimdallur"

    def ready(self):
        config = get_settings()
        ConfigurationValidator().validate(config)

        global backend_registry
        backend_registry = BackendRegistry(config)

        register_heimdallur_hooks(config)
