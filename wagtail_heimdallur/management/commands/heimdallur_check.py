"""Validate and report Wagtail-Heimdallur configuration."""

from django.core.management.base import BaseCommand

from wagtail_heimdallur.backends import BackendRegistry
from wagtail_heimdallur.conf import get_settings
from wagtail_heimdallur.validators import ConfigurationValidator


class Command(BaseCommand):
    help = "Validate Wagtail-Heimdallur configuration and report active routing."

    def handle(self, *args, **options):
        settings = get_settings()
        ConfigurationValidator().validate(settings)
        registry = BackendRegistry(settings)

        self.stdout.write(self.style.SUCCESS("Wagtail-Heimdallur configuration OK"))
        self._write_features(settings)
        self._write_backends(registry)
        self._write_routing(settings)

    def _write_features(self, settings):
        self.stdout.write("Enabled features:")
        for feature_name, enabled in sorted(settings.get("FEATURES", {}).items()):
            status = "enabled" if enabled else "disabled"
            self.stdout.write(f"  - {feature_name}: {status}")

    def _write_backends(self, registry):
        self.stdout.write("Backends:")
        for backend in registry.get_backend_statuses():
            status = "enabled" if backend["enabled"] else "disabled"
            self.stdout.write(f"  - {backend['identifier']}: {status}")
            if backend["proofreading_languages"]:
                self.stdout.write(
                    "    proofreading: "
                    + ", ".join(sorted(backend["proofreading_languages"]))
                )
            if backend["translation_pairs"]:
                pairs = [
                    f"{source}->{target}"
                    for source, target in sorted(backend["translation_pairs"])
                ]
                self.stdout.write("    translation: " + ", ".join(pairs))

    def _write_routing(self, settings):
        routing = settings.get("LANGUAGE_ROUTING", {})

        self.stdout.write("Language routing:")
        self.stdout.write("  proofreading:")
        for language, backend_id in sorted(routing.get("proofreading", {}).items()):
            self.stdout.write(f"    {language}: {backend_id}")

        self.stdout.write("  translation:")
        for pair, backend_id in sorted(
            routing.get("translation", {}).items(),
            key=lambda item: str(item[0]),
        ):
            source, target = _normalize_pair(pair)
            self.stdout.write(f"    {source}->{target}: {backend_id}")


def _normalize_pair(pair):
    if isinstance(pair, str):
        if "->" in pair:
            return tuple(pair.split("->", 1))
        if ":" in pair:
            return tuple(pair.split(":", 1))

    source, target = pair
    return source, target
