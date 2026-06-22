"""Configuration validation for Wagtail-Heimdallur."""

from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string


class ConfigurationValidator:
    """Validate WAGTAIL_HEIMDALLUR settings before plugin initialization."""

    VALID_FEATURES = {
        "inline_proofreading",
        "page_translation",
    }

    def validate(self, settings: dict) -> None:
        """Validate the complete WAGTAIL_HEIMDALLUR settings dictionary."""
        backends = settings.get("BACKENDS", {})
        self._validate_backends(backends)
        self._validate_features(settings.get("FEATURES", {}))
        self._validate_language_routing(
            settings.get("LANGUAGE_ROUTING", {}),
            backends,
        )

    def _validate_backends(self, backends: dict) -> None:
        """Validate backend definitions and CLASS importability."""
        if not backends:
            raise ImproperlyConfigured(
                "WAGTAIL_HEIMDALLUR requires at least one backend in BACKENDS."
            )

        for identifier, config in backends.items():
            class_path = config.get("CLASS")
            if not class_path:
                raise ImproperlyConfigured(
                    f"Backend '{identifier}' must define a CLASS path."
                )

            try:
                import_string(class_path)
            except ImportError as exc:
                raise ImproperlyConfigured(
                    f"Could not import backend class '{class_path}' "
                    f"for backend '{identifier}'."
                ) from exc

    def _validate_features(self, features: dict) -> None:
        """Reject feature toggle names that are not recognized."""
        invalid_features = set(features) - self.VALID_FEATURES
        if invalid_features:
            valid_features = ", ".join(sorted(self.VALID_FEATURES))
            invalid = ", ".join(sorted(invalid_features))
            raise ImproperlyConfigured(
                f"Unrecognized WAGTAIL_HEIMDALLUR feature(s): {invalid}. "
                f"Valid feature names are: {valid_features}."
            )

    def _validate_language_routing(self, routing: dict, backends: dict) -> None:
        """Reject routing entries that reference undefined backend identifiers."""
        backend_ids = set(backends)
        routing_tables = {
            "proofreading": routing.get("proofreading", {}),
            "translation": routing.get("translation", {}),
        }

        for table_name, table in routing_tables.items():
            for route, backend_id in table.items():
                if backend_id not in backend_ids:
                    raise ImproperlyConfigured(
                        "WAGTAIL_HEIMDALLUR language routing references "
                        f"undefined backend '{backend_id}' for "
                        f"{table_name} route '{route}'."
                    )
