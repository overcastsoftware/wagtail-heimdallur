# Wagtail-Heimdallur

Wagtail-Heimdallur adds proofreading and translation workflows to the Wagtail admin. It provides pluggable backend classes, a default Miðeind Málstaður backend, JSON API endpoints, Draftail editor controls, page-level translation hooks, and a configuration check command.

## Installation

```bash
pip install wagtail-heimdallur
```

Add the app to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # Wagtail and project apps...
    "wagtail_heimdallur",
]
```

Configure at least one backend:

```python
WAGTAIL_HEIMDALLUR = {
    "FEATURES": {
        "inline_proofreading": True,
        "inline_translation": True,
        "page_translation": True,
    },
    "BACKENDS": {
        "mideind": {
            "CLASS": "wagtail_heimdallur.backends.mideind.MideindBackend",
            "OPTIONS": {
                "api_key": os.environ.get("MALSTADUR_API_KEY", ""),
                "supported_language_pairs": [("is", "en"), ("en", "is")],
            },
            "enabled": True,
        },
    },
    "LANGUAGE_ROUTING": {
        "proofreading": {"is": "mideind"},
        "translation": {("is", "en"): "mideind", ("en", "is"): "mideind"},
    },
}
```

Missing feature toggles default to enabled. Per-backend `enabled: False` removes a backend from routing without deleting its configuration.

## API

The package exposes:

- `POST /api/heimdallur/proofread/` with `{"text": "...", "language": "is"}`
- `POST /api/heimdallur/translate/` with `{"text": "...", "source_language": "is", "target_language": "en"}`
- `GET /api/heimdallur/languages/`

Include the URLs from your project URLconf if you want the endpoints mounted:

```python
from django.urls import include, path

urlpatterns = [
    path("", include("wagtail_heimdallur.urls")),
]
```

## Management Command

Validate configuration and inspect enabled features, backends, and routing:

```bash
python manage.py heimdallur_check
```

## Frontend Assets

TypeScript sources live in `wagtail_heimdallur/client`. To rebuild the static editor bundle:

```bash
cd wagtail_heimdallur/client
npm install
npm run build
npm test
```

The compiled assets are served from `wagtail_heimdallur/static/wagtail_heimdallur/`.

## Demo Site

Run the included demo site from the repository root:

```bash
docker compose up demo
```

Then open `http://localhost:8000/admin/`. Supply a Málstaður API key with:

```bash
MALSTADUR_API_KEY=your-key docker compose up demo
```

If `MALSTADUR_API_KEY` is not provided, the demo still starts. The demo settings keep the backend configured with an empty key so local pages, admin wiring, and configuration checks can be inspected before credentials are available.

Sample Icelandic content is defined in `demo/home/fixtures/sample_pages.json` for projects that want to load starter content.

## Development

Run tests in Docker:

```bash
docker compose run tests
docker compose run tests pytest tests/test_backends/test_mideind.py
docker compose run tests tox
```

Run tests locally:

```bash
pip install -e ".[dev]"
pytest
tox
```

## License

MIT. See `LICENSE`.
