# Implementation Plan: Wagtail-Heimdallur

## Overview

This plan implements Wagtail-Heimdallur as a Wagtail CMS plugin providing inline proofreading, inline translation, and page-level translation. The implementation progresses from foundational package structure and data models through backend architecture, API views, Wagtail hooks, Draftail editor extensions, and finally the demo site and packaging.

## Tasks

- [ ] 1. Set up project structure, exceptions, and core data models
  - [x] 1.0 Scaffold full package structure and pyproject.toml
    - Create `pyproject.toml` with package metadata, dependencies (Django>=4.2, Wagtail>=6.0), dev dependencies (pytest, pytest-django, hypothesis, tox, httpx-mock), and entry points
    - Create complete directory tree with `__init__.py` files:
      - `wagtail_heimdallur/backends/`
      - `wagtail_heimdallur/engines/`
      - `wagtail_heimdallur/management/commands/`
      - `wagtail_heimdallur/static/wagtail_heimdallur/js/`
      - `wagtail_heimdallur/static/wagtail_heimdallur/css/`
      - `wagtail_heimdallur/templates/wagtail_heimdallur/admin/`
      - `wagtail_heimdallur/client/src/proofread/`
      - `wagtail_heimdallur/client/src/translate/`
    - Create `tests/__init__.py` and `tests/conftest.py` with basic Django settings for testing
    - Create `tests/test_backends/__init__.py` and `tests/test_engines/__init__.py`
    - _Requirements: 1.1, 10.1, 10.2_

  - [x] 1.1 Create package structure and exception hierarchy
    - Create `wagtail_heimdallur/` package directory with `__init__.py`
    - Create `wagtail_heimdallur/exceptions.py` with `BackendError`, `AuthenticationError`, `BackendTimeoutError`, `BackendRequestError`, `UnsupportedLanguageError`, `UnsupportedLanguagePairError`, `NoAvailableBackendError`
    - Create `wagtail_heimdallur/conf.py` with `get_settings()` function that reads `WAGTAIL_HEIMDALLUR` from Django settings and applies defaults (all features enabled)
    - _Requirements: 1.1, 1.8, 1.9, 8.1_

  - [x] 1.2 Implement core data models and serialization
    - Create `wagtail_heimdallur/models.py` with `DiffAnnotation` and `ProofreadingResult` dataclasses
    - Implement `to_dict()`, `from_dict()` on `DiffAnnotation`
    - Implement `to_json()`, `from_json()` on `ProofreadingResult`
    - _Requirements: 2.6, 3.8, 11.1, 11.2, 11.3_

  - [x] 1.3 Write property test for ProofreadingResult serialization round-trip
    - **Property 1: ProofreadingResult serialization round-trip**
    - Create `tests/strategies.py` with Hypothesis strategies for `DiffAnnotation` and `ProofreadingResult`
    - Create `tests/test_serialization.py` with round-trip property test
    - **Validates: Requirements 11.1, 11.2, 11.3**

  - [x] 1.4 Write unit tests for exception hierarchy and conf module
    - Test that all exceptions inherit from `BackendError`
    - Test `get_settings()` applies feature toggle defaults
    - _Requirements: 1.9, 8.1_

  - [x] 1.5 Create Docker-based development and testing environment
    - Create `Dockerfile` with Python 3.14, Node.js, pip dependencies (pytest, hypothesis, tox), and npm
    - Create `docker-compose.yml` at repository root with a `tests` service that volume-mounts source code
    - Default command: `pytest` (full test suite)
    - Support `docker compose run tests tox` for matrix testing
    - Support `docker compose run tests pytest <path>` for targeted test runs
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7_

- [x] 2. Implement backend abstract classes and registry
  - [x] 2.1 Create backend abstract base classes
    - Create `wagtail_heimdallur/backends/__init__.py`
    - Create `wagtail_heimdallur/backends/base.py` with `BaseTranslationBackend` and `BaseProofreadingBackend` ABCs
    - Define abstract methods: `translate()`, `get_supported_language_pairs()`, `proofread()`, `get_supported_languages()`
    - _Requirements: 2.1, 2.2, 2.13_

  - [x] 2.2 Implement BackendRegistry with language routing
    - Create `wagtail_heimdallur/backends/registry.py` with `BackendRegistry` class
    - Implement `_load_backends(settings)` to dynamically import and instantiate backend classes with OPTIONS kwargs
    - Implement `get_backend_for_proofreading(language)` with routing table lookup and fallback to first capable backend
    - Implement `get_backend_for_translation(source_language, target_language)` with routing table lookup and fallback
    - Raise `UnsupportedLanguageError` when no backend supports the language
    - Raise `NoAvailableBackendError` when all capable backends are disabled
    - Skip backends with `enabled: False`
    - _Requirements: 2.3, 2.4, 2.5, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 1.13, 12.8, 12.9, 12.10_

  - [x]* 2.3 Write property tests for backend registry routing
    - **Property 4: Proofreading language routing resolution**
    - **Property 5: Translation language pair routing resolution**
    - **Property 6: Routing fallback to first capable backend**
    - **Property 10: Unsupported language raises error**
    - **Property 17: Disabled backends excluded from routing**
    - **Property 18: All backends disabled raises NoAvailableBackendError**
    - Create `tests/test_backends/test_registry.py` with Hypothesis strategies for settings dictionaries and routing tables
    - **Validates: Requirements 2.8, 2.9, 2.10, 2.11, 2.12, 1.13, 12.8, 12.9, 12.10**

  - [x]* 2.4 Write property test for backend options pass-through
    - **Property 9: Backend options pass-through**
    - Verify all OPTIONS key-value pairs arrive as kwargs to backend `__init__`
    - **Validates: Requirements 2.5**

- [x] 3. Implement configuration validator
  - [x] 3.1 Create ConfigurationValidator
    - Create `wagtail_heimdallur/validators.py` with `ConfigurationValidator` class
    - Implement `_validate_backends()`: check CLASS path importability, raise `ImproperlyConfigured` on failure
    - Implement `_validate_features()`: reject unrecognized feature names with `ImproperlyConfigured`
    - Implement `_validate_language_routing()`: reject backend identifiers not in BACKENDS dict
    - Implement top-level `validate(settings)` that calls all sub-validators
    - _Requirements: 1.4, 1.14, 1.15, 1.16, 2.4_

  - [x]* 3.2 Write property tests for configuration validator
    - **Property 7: Invalid backend references in routing rejected**
    - **Property 8: Unrecognized feature names rejected**
    - Create `tests/test_validators.py` with Hypothesis strategies for invalid settings
    - **Validates: Requirements 1.14, 1.16**

- [x] 4. Checkpoint - Core architecture validated
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement Miðeind backend
  - [x] 5.1 Implement MideindBackend class
    - Create `wagtail_heimdallur/backends/mideind.py` with `MideindBackend` implementing both `BaseTranslationBackend` and `BaseProofreadingBackend`
    - Implement `proofread()`: POST to `/v1/grammar` with `X-API-KEY` header, parse response into `ProofreadingResult`
    - Map camelCase API response fields to snake_case `DiffAnnotation` fields
    - Implement `translate()`: POST to `/v1/translate` with source/target language params
    - Implement `get_supported_languages()` and `get_supported_language_pairs()`
    - Handle HTTP errors: 401/403 → `AuthenticationError`, 504/timeout → `BackendTimeoutError`, 400 → `BackendRequestError`, 500 → `BackendError`
    - Use configurable timeout (default 30s) from OPTIONS
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 8.3, 8.5_

  - [x]* 5.2 Write property test for Málstaður response parsing
    - **Property 11: Málstaður response parsing preserves all annotations**
    - Create `tests/test_backends/test_mideind.py` with Hypothesis strategy for mock Málstaður responses
    - **Validates: Requirements 3.3**

  - [x]* 5.3 Write unit tests for MideindBackend error handling
    - Test HTTP 401/403 raises `AuthenticationError`
    - Test HTTP 504 and timeout raises `BackendTimeoutError`
    - Test HTTP 400 raises `BackendRequestError`
    - Test HTTP 500 raises `BackendError`
    - Test `UnsupportedLanguagePairError` for invalid pair
    - Use `httpx-mock` or `responses` for HTTP mocking
    - _Requirements: 3.4, 3.5, 3.6, 3.7, 4.6, 4.7_

- [x] 6. Implement engines and API views
  - [x] 6.1 Implement ProofreadingEngine and TranslationEngine
    - Create `wagtail_heimdallur/engines/__init__.py`
    - Create `wagtail_heimdallur/engines/proofreading.py` with `ProofreadingEngine` that uses `BackendRegistry` to route and invoke proofreading
    - Create `wagtail_heimdallur/engines/translation.py` with `TranslationEngine` that uses `BackendRegistry` to route and invoke translation
    - Wrap unexpected exceptions as `BackendError` (Property 15)
    - Ensure atomicity — no partial state on failure (Property 16)
    - Log all backend interactions at DEBUG level
    - _Requirements: 2.8, 2.9, 8.2, 8.4, 8.5_

  - [x]* 6.2 Write property tests for engine error wrapping
    - **Property 15: Unexpected exceptions wrapped as BackendError**
    - **Property 16: No partial modifications on backend failure**
    - Create `tests/test_engines/test_proofreading.py` and `tests/test_engines/test_translation.py`
    - **Validates: Requirements 8.2, 8.4**

  - [x] 6.3 Implement API views and URL configuration
    - Create `wagtail_heimdallur/views.py` with `ProofreadView`, `TranslateView`, `SupportedLanguagesView`
    - `ProofreadView`: accept POST with `text` and `language`, return serialized `ProofreadingResult`
    - `TranslateView`: accept POST with `text`, `source_language`, `target_language`, return `{"translated_text": "..."}`
    - `SupportedLanguagesView`: GET endpoint returning available languages/pairs
    - Return consistent error JSON format on `BackendError` subclasses
    - Create `wagtail_heimdallur/urls.py` with URL patterns under `/api/heimdallur/`
    - _Requirements: 6.2, 7.3, 8.2_

  - [x]* 6.4 Write unit tests for API views
    - Test successful proofreading request/response cycle
    - Test successful translation request/response cycle
    - Test error response format for various BackendError types
    - Test SupportedLanguagesView returns correct structure
    - Use Django test client with mocked engines
    - _Requirements: 6.2, 7.3, 8.2_

- [x] 7. Implement Wagtail hooks and AppConfig
  - [x] 7.1 Implement Wagtail hooks with feature toggle gating
    - Create `wagtail_heimdallur/hooks.py` with conditional hook registration based on feature toggles
    - Register `register_rich_text_features` hook for Draftail plugin (proofreading and translation)
    - Register `insert_editor_js` and `insert_editor_css` hooks for loading frontend bundle
    - Gate each registration on respective feature toggle
    - _Requirements: 1.2, 1.10, 12.5, 12.6, 12.7_

  - [x] 7.2 Implement AppConfig with startup validation
    - Create `wagtail_heimdallur/apps.py` with `WagtailHeimdallurConfig` AppConfig
    - In `ready()`: run `ConfigurationValidator`, initialize `BackendRegistry`, register hooks
    - Raise `ImproperlyConfigured` if no backends configured
    - _Requirements: 1.4, 1.15_

  - [x]* 7.3 Write property test for feature toggle conditional registration
    - **Property 2: Feature toggle conditional registration**
    - **Property 3: Feature toggle defaults to enabled**
    - Create `tests/test_hooks.py` with Hypothesis strategies for feature toggle combinations
    - **Validates: Requirements 1.2, 1.9, 1.10, 12.5, 12.6, 12.7**

- [x] 8. Implement page translation
  - [x] 8.1 Implement page translation hook and field processing
    - Implement signal handler for Wagtail's `copy_for_translation` (or hook into `simple_translation` module)
    - Iterate all translatable fields: plain text, rich text, StreamField text blocks
    - Invoke `TranslationEngine` for each text segment
    - Handle partial failures: log errors, skip failed fields, continue with remaining
    - Save result as draft page in target locale
    - Display progress indicator in admin
    - Show warning listing skipped fields on partial completion
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 12.7_

  - [x]* 8.2 Write property tests for page translation
    - **Property 12: Page translation processes all translatable field types**
    - **Property 13: Partial field failure does not prevent remaining translations**
    - Create `tests/test_engines/test_page_translation.py`
    - **Validates: Requirements 5.2, 5.5**

- [ ] 9. Checkpoint - Backend and integration complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Implement Draftail editor extension (TypeScript/React)
  - [ ] 10.1 Set up TypeScript build toolchain
    - Create `wagtail_heimdallur/client/package.json` with React, Draft.js typings, and build scripts
    - Create `wagtail_heimdallur/client/tsconfig.json`
    - Configure bundler (webpack/esbuild) to output to `wagtail_heimdallur/static/wagtail_heimdallur/js/`
    - Create `wagtail_heimdallur/client/src/index.ts` as entry point registering Draftail plugins
    - _Requirements: 6.1, 7.1_

  - [ ] 10.2 Implement inline proofreading components
    - Create `ProofreadButton.tsx` (toolbar source component) — sends field content to `/api/heimdallur/proofread/`
    - Create `AnnotationDecorator.tsx` — renders inline highlights for Diff_Annotations as Draftail entity decorators
    - Create `AnnotationPopover.tsx` — shows original text, suggestion, change type; accept/dismiss actions
    - Implement "Dismiss All" action to clear all highlights
    - Handle API errors by displaying notification toast
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

  - [ ]* 10.3 Write property test for annotation correction application
    - **Property 14: Annotation correction application**
    - Test in TypeScript (Jest) or Python — applying a DiffAnnotation replaces exactly the target substring
    - **Validates: Requirements 6.5**

  - [ ] 10.4 Implement inline translation components
    - Create `TranslateButton.tsx` (toolbar source component) — opens language pair selector modal
    - Create `LanguagePairSelector.tsx` — fetches supported pairs from `/api/heimdallur/languages/`
    - Create `TranslationPreview.tsx` — displays translated text with accept/cancel actions
    - On accept, replace field content with translated text
    - Handle API errors by displaying notification toast
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [ ]* 10.5 Write frontend unit tests
    - Test ProofreadButton renders and triggers API call
    - Test AnnotationPopover accept/dismiss behavior
    - Test TranslateButton and LanguagePairSelector rendering
    - Test TranslationPreview accept/cancel flow
    - Use Jest with @testing-library/react and MSW for API mocking
    - _Requirements: 6.1–6.8, 7.1–7.7_

  - [ ] 10.6 Create editor CSS styles
    - Create `wagtail_heimdallur/static/wagtail_heimdallur/css/` with styles for annotation highlights, popovers, and translation preview panel
    - Ensure accessibility: sufficient contrast ratios, focus indicators
    - _Requirements: 6.3, 6.4_

- [ ] 11. Implement management command
  - [ ] 11.1 Create heimdallur_check management command
    - Create `wagtail_heimdallur/management/__init__.py` and `commands/__init__.py`
    - Create `wagtail_heimdallur/management/commands/heimdallur_check.py`
    - Output: enabled features, active backends with supported languages, resolved language routing table
    - Use `self.stdout.write()` with styling for success/warning output
    - _Requirements: 12.11, 12.12_

  - [ ]* 11.2 Write property test for management command output completeness
    - **Property 19: Management command output completeness**
    - Create `tests/test_management_commands.py` with Hypothesis strategy for valid configurations
    - Verify output contains all enabled features, backend identifiers, and routing entries
    - **Validates: Requirements 12.11, 12.12**

- [ ] 12. Checkpoint - All features implemented
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. Demo site and packaging
  - [ ] 13.1 Create Docker-based demo site
    - Create `demo/` directory with a minimal Wagtail project configured with the plugin
    - Create `docker-compose.yml` at repository root
    - Configure demo with Miðeind backend reading API key from environment variable
    - Include sample Icelandic content pages
    - Handle missing API key gracefully: start successfully, show admin warning
    - Add README instructions for running the demo
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ] 13.2 Set up packaging and CI
    - Create `pyproject.toml` with package metadata, dependencies (min version constraints), and entry points
    - Create `tox.ini` for test matrix across Python 3.11+, Django 4.2+, Wagtail 6.0+
    - Add MIT LICENSE file
    - Create comprehensive README.md with installation, configuration, and usage docs
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 1.5, 1.6, 1.7_

- [ ] 14. Final checkpoint - All tests pass and packaging validated
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document using Hypothesis
- Unit tests validate specific examples and edge cases
- The TypeScript frontend build must output to the static directory before the Django package can serve it
- The demo site depends on the complete package being functional

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.0", "1.1", "1.2", "1.5"] },
    { "id": 1, "tasks": ["1.3", "1.4", "2.1"] },
    { "id": 2, "tasks": ["2.2", "3.1"] },
    { "id": 3, "tasks": ["2.3", "2.4", "3.2"] },
    { "id": 4, "tasks": ["5.1"] },
    { "id": 5, "tasks": ["5.2", "5.3", "6.1"] },
    { "id": 6, "tasks": ["6.2", "6.3"] },
    { "id": 7, "tasks": ["6.4", "7.1", "7.2"] },
    { "id": 8, "tasks": ["7.3", "8.1"] },
    { "id": 9, "tasks": ["8.2", "10.1", "11.1"] },
    { "id": 10, "tasks": ["10.2", "10.4", "11.2"] },
    { "id": 11, "tasks": ["10.3", "10.5", "10.6"] },
    { "id": 12, "tasks": ["13.1", "13.2"] }
  ]
}
```
