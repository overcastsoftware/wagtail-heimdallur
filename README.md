# Wagtail-Heimdallur

Wagtail-Heimdallur adds proofreading and translation workflows to the Wagtail
admin. It ships with:

- **Inline proofreading** — a control in the Draftail rich text editor that
  checks a page's text and shows accept/dismiss suggestions inline.
- **Page-level translation** — when an editor copies a page to another locale,
  the page's text is queued and translated in the background.
- **Pluggable backends** — a default Miðeind [Málstaður](https://malstadur.is)
  backend, plus a small interface for adding your own services. Different
  languages and language pairs can be routed to different backends.

The plugin is configured entirely through a single `WAGTAIL_HEIMDALLUR` setting.

## Requirements

- Python 3.11+
- Django 4.2+
- Wagtail 6.0+

The inline proofreading control integrates with Wagtail's Draftail editor and is
developed and verified against Wagtail 7.x.

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

Mount the API URLs (used by the proofreading control) in your project URLconf:

```python
from django.urls import include, path

urlpatterns = [
    # ...
    path("", include("wagtail_heimdallur.urls")),
]
```

Then add a `WAGTAIL_HEIMDALLUR` setting with at least one backend (see below).

## Configuration

A minimal configuration using the Miðeind backend for Icelandic:

```python
import os

WAGTAIL_HEIMDALLUR = {
    "FEATURES": {
        "inline_proofreading": True,
        "page_translation": True,
    },
    "BACKENDS": {
        "mideind": {
            "CLASS": "wagtail_heimdallur.backends.mideind.MideindBackend",
            "OPTIONS": {
                "api_key": os.environ["MALSTADUR_API_KEY"],
                "supported_languages": ["is"],
                "supported_language_pairs": [("is", "en"), ("en", "is")],
            },
            "enabled": True,
        },
    },
    "LANGUAGE_ROUTING": {
        "proofreading": {"is": "mideind"},
        "translation": {
            ("is", "en"): "mideind",
            ("en", "is"): "mideind",
        },
    },
}
```

The configuration is validated at startup; an invalid setting (no backends, an
unimportable backend class, an unknown feature name, or a routing entry pointing
at an undefined backend) raises `ImproperlyConfigured`.

### `FEATURES`

A dictionary of feature toggles. **Each defaults to `True`** if omitted.

| Key                  | Default | Effect when `True`                                                                 |
| -------------------- | ------- | ---------------------------------------------------------------------------------- |
| `inline_proofreading`| `True`  | Registers the Draftail proofreading control and its API.                            |
| `page_translation`   | `True`  | Queues a translation job when a page is copied to a new locale, adds the "Publish & update translations" page action, and adds the report.|

Setting a toggle to `False` skips registering the hooks, views, and UI for that
feature.

### `BACKENDS`

A dictionary of named backend definitions. Each entry has:

| Key       | Required | Description                                                                 |
| --------- | -------- | --------------------------------------------------------------------------- |
| `CLASS`   | yes      | Dotted import path to a backend class.                                       |
| `OPTIONS` | no       | Keyword arguments passed to the backend's `__init__`.                        |
| `enabled` | no       | Defaults to `True`. `False` keeps the definition but removes it from routing.|

You may register as many backends as you like — for example one service for
Icelandic and another for a different language.

#### Miðeind backend options

`wagtail_heimdallur.backends.mideind.MideindBackend` accepts:

| Option                     | Default                     | Description                                                              |
| -------------------------- | --------------------------- | ------------------------------------------------------------------------ |
| `api_key`                  | `""`                        | Málstaður API key, sent as the `X-API-KEY` header.                       |
| `base_url`                 | `https://api.malstadur.is`  | API base URL.                                                            |
| `timeout`                  | `30`                        | Per-request timeout in seconds.                                          |
| `supported_languages`      | `["is"]`                    | Languages this backend proofreads.                                       |
| `supported_language_pairs` | queried from the API        | `(source, target)` pairs this backend translates.                       |
| `request_delay`            | `0.0`                       | Seconds to wait before each request. Throttles page translation to stay under the rate limit. |
| `rate_limit_retries`       | `2`                         | Retries on HTTP 429 (honouring `Retry-After`) before raising `RateLimitError`. |

### `LANGUAGE_ROUTING`

Maps languages and language pairs to a backend identifier:

```python
"LANGUAGE_ROUTING": {
    "proofreading": {"is": "mideind"},                  # {language: backend}
    "translation":  {("is", "en"): "mideind"},          # {(source, target): backend}
},
```

If a language or pair is **not** listed, the first configured backend that
supports it is used as a fallback — so with a single backend you don't need a
routing table at all; it becomes the default for everything it can handle.

## Multiple services and language routing

You can register several backends and route work to them per language
(proofreading) or per language pair (translation). Each backend declares what it
supports:

- proofreading backends implement `get_supported_languages()`
- translation backends implement `get_supported_language_pairs()`

Because backends declare their languages, the inline proofreading control only
appears in the editor for pages whose **content language** a backend actually
supports. Miðeind's Málstaður only proofreads Icelandic, for example, so the
Proofread button is hidden when editing an English page.

Example of routing two languages to two services:

```python
WAGTAIL_HEIMDALLUR = {
    "BACKENDS": {
        "mideind": {
            "CLASS": "wagtail_heimdallur.backends.mideind.MideindBackend",
            "OPTIONS": {"api_key": MIDEIND_KEY, "supported_languages": ["is"]},
        },
        "acme": {
            "CLASS": "myproject.backends.AcmeProofreader",
            "OPTIONS": {"api_key": ACME_KEY},
        },
    },
    "LANGUAGE_ROUTING": {
        "proofreading": {
            "is": "mideind",
            "en": "acme",
        },
    },
}
```

## Custom backends

Implement one or both of the abstract base classes in
`wagtail_heimdallur.backends.base`. A single class may implement both.

```python
from wagtail_heimdallur.backends.base import BaseProofreadingBackend
from wagtail_heimdallur.models import DiffAnnotation, ProofreadingResult


class AcmeProofreader(BaseProofreadingBackend):
    def __init__(self, api_key="", **kwargs):
        self.api_key = api_key

    def get_supported_languages(self):
        return ["en"]

    def proofread(self, text, language):
        # ... call your service ...
        return ProofreadingResult(
            original_text=text,
            corrected_text=corrected,
            annotations=[
                DiffAnnotation(
                    orig_start_idx=0, orig_end_idx=3, orig_string="teh",
                    changed_start_idx=0, changed_end_idx=3, changed_string="the",
                    change_type="spelling",
                ),
            ],
        )
```

For translation, implement `BaseTranslationBackend` with `translate(text,
source_language, target_language)` and `get_supported_language_pairs()`. Backends
should raise the typed exceptions from `wagtail_heimdallur.exceptions`
(`AuthenticationError`, `BackendTimeoutError`, `BackendRequestError`,
`UnsupportedLanguageError`, ...) so the admin can report failures cleanly.

> **Note:** page translation currently drives Miðeind's asynchronous
> text-translation endpoints. A custom translation backend used for page
> translation should also implement `start_text_translation()` and
> `get_text_translation_status()` as the Miðeind backend does.

## Inline proofreading

With `inline_proofreading` enabled, a **Proofread** button appears in the
Draftail toolbar of rich text fields (only for content languages a backend
supports). Clicking it:

1. Sends each block's text to the configured proofreading backend.
2. Highlights suggestions inline. A badge shows how many were found.
3. Clicking a highlight opens a popover with the original → suggestion and
   buttons to **accept all**, **accept**, or **dismiss** the suggestion.
4. Once suggestions exist, the toolbar button becomes **Apply all**, and a
   **Dismiss all** button appears.

Highlights are ephemeral review aids — they are stripped when the page is saved,
leaving only the corrected text.

## Page translation

With `page_translation` enabled, copying a page to another locale (Wagtail's
"Translate page" action, via `wagtail.contrib.simple_translation`) queues a
translation job for the page's translatable text — plain text, rich text, and
text inside StreamField blocks.

Jobs are processed by a management command (run it on a schedule or a worker):

```bash
python manage.py process_heimdallur_translation_queue
```

The command submits queued text to the backend's asynchronous translation
endpoint, then on later runs polls running tasks and applies completed
translations to the draft page. Use `--limit` to cap how many jobs a single run
processes, or `--until-done` to keep submitting and polling in one invocation
until the queue drains (tune the loop with `--poll-interval` and `--max-passes`):

```bash
python manage.py process_heimdallur_translation_queue --until-done
```

Job records accumulate over time; prune finished ones (translation memory is
kept) with:

```bash
python manage.py process_heimdallur_translation_queue --prune-completed-older-than-days 30
```

A page is submitted as one request per text segment, so a content-heavy page can
make many requests in quick succession. If the backend rate-limits you (HTTP 429,
raised as `RateLimitError`), set the Miðeind `request_delay` option to throttle
the requests, then re-run the queue with `--retry-failed` once the limit window
has passed.

Queue state, progress, failures, and skipped fields are visible in the Wagtail
admin under **Reports → Translation queue**. When a page has translation work in
progress, its edit screen shows a warning linking to the queue.

### Keeping translations up to date

After the first translation, edit the source page and use the **Publish & update
translations** action (in the page's Save/Publish menu) to push your changes to
its translations. It publishes the page and re-translates each translation — but
only the blocks whose source text actually changed. Each translatable block is
tracked by a stable key (derived from StreamField block ids) together with a hash
of its source text, so an edit to one paragraph re-translates that paragraph
alone and leaves everything else untouched. This keeps backend usage (and
rate-limit pressure) proportional to what you changed.

Re-translation does not happen on a plain **Publish** — only via this action, so
routine edits to a page don't silently regenerate translations.

Re-translations are saved as a **draft** for review, never auto-published:

- Blocks whose source is unchanged keep their current translation, including any
  manual corrections a translator made.
- If a changed block's translation had been hand-edited, it is still
  re-translated, but the block is listed under **Replaced edits** in the queue
  report and the translated page's edit screen prompts you to review the draft
  before publishing.

The action only appears on pages in a *source* locale, so you can't accidentally
machine-translate a translation back onto its original. By default the source
locale is the site's default locale; configure this under `PAGE_TRANSLATION`:

```python
WAGTAIL_HEIMDALLUR = {
    "PAGE_TRANSLATION": {
        "source_locales": ["is"],       # None = only the site default locale
        # StreamField block classes that must not be machine translated. They
        # follow the source like other non-text content and can be overridden
        # per locale. Defaults to excluding RawHTMLBlock; set to [] to translate
        # everything.
        "untranslatable_blocks": ["wagtail.blocks.RawHTMLBlock"],
        # Page fields to never translate (config, not content). Defaults to the
        # form builder's email settings.
        "untranslatable_fields": ["to_address", "from_address"],
        # Translatable text on child relations (InlinePanel content), as
        # {relation: [fields]}. Defaults to the form builder's fields so form
        # labels/help/choices are translated.
        "translatable_child_relations": {
            "form_fields": ["label", "help_text", "choices"],
        },
    },
}
```

#### Form pages and other child-relation content

Text that lives on a page's **child relations** (Wagtail `InlinePanel` content) is
translated too — out of the box this covers the **form builder**: each form
field's `label`, `help_text` and `choices`. Configure other relations (or add
fields like `default_value`) via `translatable_child_relations`.

Child objects are matched between source and target by their `translation_key`
when the child model is a `TranslatableMixin` (robust to reordering), and **by
position** otherwise. Either way, adding or removing children on the source after
the translation exists won't create/remove them on the translated page — re-copy
the page (Wagtail's "Translate page") for structural changes. Editing existing
children's text translates normally.

#### Non-text content (choosers, embeds, numbers …) and overrides

Non-translatable content inside StreamFields follows the source by default — an
image, number or link you change on the source page syncs to its translations.
A translator can also **override** such a block per locale (e.g. a localized
video in an `EmbedBlock`); that override is **sticky** — it is preserved on every
future re-translation, while un-overridden blocks keep following the source.
There is no "reset to source" action, so an overridden block stays overridden
until the translator changes it back themselves.

To stop a *text* block from being machine translated (so it behaves like the
non-text content above), either set `translatable = False` on the block class or
add its dotted path to `untranslatable_blocks`.

Retry jobs after fixing credentials or configuration:

```bash
python manage.py process_heimdallur_translation_queue --retry-failed
python manage.py process_heimdallur_translation_queue --retry-warnings
```

Requeue stale running jobs (an explicit age guard is required):

```bash
python manage.py process_heimdallur_translation_queue --retry-running --older-than-minutes 60
```

## Management commands

Validate configuration and inspect enabled features, registered backends, and
the resolved routing:

```bash
python manage.py heimdallur_check
```

Process the page-translation queue (see above):

```bash
python manage.py process_heimdallur_translation_queue
```

## API endpoints

Mounted by `wagtail_heimdallur.urls`:

| Method & path                      | Body / response                                                              |
| ---------------------------------- | --------------------------------------------------------------------------- |
| `POST /api/heimdallur/proofread/`  | `{"text": "...", "language": "is"}` → serialized `ProofreadingResult`.       |
| `GET /api/heimdallur/languages/`   | `{"proofreading": {"languages": [...]}, "translation": {"language_pairs": [...]}}` |

`POST` requests require Django's CSRF token; the editor control sends it
automatically. Backend errors are returned as
`{"error": {"type": ..., "message": ...}}` with HTTP 400.

## Demo site

Run the included demo from the repository root:

```bash
docker compose up demo
```

Open `http://localhost:8000/admin/` and sign in as `admin` / `admin`. Supply a
Málstaður API key to exercise the live backend:

```bash
MALSTADUR_API_KEY=your-key docker compose up demo
```

Without a key the demo still starts (the backend is configured with an empty
key) so the admin wiring, pages, and `heimdallur_check` can be inspected. The
demo creates Icelandic and English locales, a default site rooted at an
Icelandic sample page, and the `admin` superuser. Sample content lives in
`demo/home/fixtures/sample_pages.json`.

## Development

TypeScript sources for the editor control live in `wagtail_heimdallur/client`.
Rebuild the static bundle after changing them:

```bash
cd wagtail_heimdallur/client
npm install
npm run build       # outputs to wagtail_heimdallur/static/wagtail_heimdallur/js/
npm test
```

Run the Python test suite (in Docker):

```bash
docker compose run tests
docker compose run tests pytest tests/test_backends/test_mideind.py
docker compose run tests tox
```

Or locally:

```bash
pip install -e ".[dev]"
pytest
tox
```

## License

MIT. See `LICENSE`.
