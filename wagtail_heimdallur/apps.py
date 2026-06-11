"""Django application configuration for Wagtail-Heimdallur."""

from django.apps import AppConfig

from wagtail_heimdallur.backends import BackendRegistry
from wagtail_heimdallur.conf import get_settings
from wagtail_heimdallur.hooks import register_heimdallur_hooks
from wagtail_heimdallur.validators import ConfigurationValidator

backend_registry = None


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
