# Requirements Document

## Introduction

Wagtail-Heimdallur is an open-source Wagtail CMS plugin that provides translation and proofreading capabilities directly within the Wagtail editor. The plugin integrates with Miðeind's Málstaður API as the default backend, supporting all language pairs available through that service, and supports a pluggable architecture allowing users to implement custom translation and proofreading services. The plugin is modular and fully configurable — developers can enable or disable individual features, register multiple backends, and route specific languages to specific providers via Django settings. The plugin is distributed via PyPI and includes a Docker-based demo site.

## Glossary

- **Plugin**: The Wagtail-Heimdallur Django/Wagtail package installable via pip
- **Backend**: A pluggable service adapter that implements translation or proofreading operations against an external API
- **Miðeind_Backend**: The default backend implementation that communicates with the Málstaður API (https://api.malstadur.is)
- **Málstaður_API**: Miðeind's hosted API providing grammar/proofreading and translation services supporting multiple language pairs
- **Supported_Language_Pairs**: The set of language pairs available for translation as reported by the Málstaður_API at runtime
- **Proofreading_Engine**: The component responsible for sending text to a backend and returning annotated corrections
- **Translation_Engine**: The component responsible for sending text to a backend and returning translated text
- **Editor_Extension**: A Draftail rich text editor extension that adds inline proofreading and translation controls to text fields in the Wagtail admin
- **Diff_Annotation**: A structured object describing a single change between original and corrected text, including character positions and change type
- **Page_Translation**: The process of translating all translatable content fields of a Wagtail Page from one locale to another
- **Inline_Proofreading**: Real-time grammar and spelling correction applied to individual text fields within the Wagtail editor
- **Inline_Translation**: Real-time translation of individual text field content within the Wagtail editor
- **Backend_Registry**: The configuration system that maps backend identifiers to their implementing classes, credentials, and supported operations
- **Feature_Toggle**: A boolean configuration flag that enables or disables a specific Plugin capability (Inline_Proofreading, Inline_Translation, or Page_Translation)
- **Language_Backend_Mapping**: A configuration entry that routes a specific language (for proofreading) or language pair (for translation) to a designated Backend
- **Settings_Dictionary**: The `WAGTAIL_HEIMDALLUR` dictionary in Django settings containing all Plugin configuration including feature toggles, backend definitions, and language routing
- **Language_Routing_Table**: The section of the Settings_Dictionary that maps language codes to Backend identifiers for proofreading and language pairs to Backend identifiers for translation
- **Backend_Capability**: A declaration of which operations (translation, proofreading) and which languages a specific Backend instance supports
- **Configuration_Validator**: The component that validates the entire Settings_Dictionary at startup, checking for missing backends, invalid language routes, and conflicting feature settings
- **Demo_Site**: A Docker Compose-based example Wagtail project demonstrating all plugin features

## Requirements

### Requirement 1: Plugin Installation and Configuration

**User Story:** As a developer, I want to install Wagtail-Heimdallur via pip and configure it through Django settings, so that I can add translation and proofreading to my Wagtail site with minimal effort and control exactly which features are active.

#### Acceptance Criteria

1. THE Plugin SHALL be installable via `pip install wagtail-heimdallur`
2. WHEN the Plugin is added to Django INSTALLED_APPS, THE Plugin SHALL register only the hooks, admin views, and static assets for features that are enabled via Feature_Toggles
3. THE Plugin SHALL require configuration of at least one Backend via a `WAGTAIL_HEIMDALLUR` dictionary in Django settings
4. WHEN no Backend is configured, THE Plugin SHALL raise an `ImproperlyConfigured` exception at application startup with a descriptive error message
5. THE Plugin SHALL support Python 3.11 and above
6. THE Plugin SHALL support Django 4.2 and above
7. THE Plugin SHALL support Wagtail 6.0 and above
8. THE Settings_Dictionary SHALL support a `FEATURES` key containing Feature_Toggle entries for `inline_proofreading`, `inline_translation`, and `page_translation`
9. WHEN a Feature_Toggle is not explicitly set in the Settings_Dictionary, THE Plugin SHALL default that feature to enabled
10. WHEN a Feature_Toggle is set to `False`, THE Plugin SHALL not register hooks, views, or UI elements associated with that feature
11. THE Settings_Dictionary SHALL support a `BACKENDS` key containing a dictionary of named Backend definitions, each specifying the backend class path and configuration options
12. THE Settings_Dictionary SHALL support a `LANGUAGE_ROUTING` key containing a `proofreading` mapping of language codes to Backend identifiers and a `translation` mapping of language pair tuples to Backend identifiers
13. WHEN a language or language pair is not present in the Language_Routing_Table, THE Plugin SHALL use the first configured Backend that supports the requested operation as a fallback
14. IF a Language_Routing_Table entry references a Backend identifier not defined in the `BACKENDS` key, THEN THE Plugin SHALL raise an `ImproperlyConfigured` exception at application startup
15. THE Configuration_Validator SHALL validate the entire Settings_Dictionary at application startup before any Plugin component is initialized
16. IF the `FEATURES` key contains an unrecognized feature name, THEN THE Configuration_Validator SHALL raise an `ImproperlyConfigured` exception listing valid feature names

### Requirement 2: Pluggable Backend Architecture

**User Story:** As a developer, I want to implement custom backends for translation and proofreading, so that I can use alternative services beyond the default Miðeind API and route different languages to different providers.

#### Acceptance Criteria

1. THE Plugin SHALL define a `BaseTranslationBackend` abstract class with a `translate(text: str, source_language: str, target_language: str) -> str` method and a `get_supported_language_pairs() -> list` method
2. THE Plugin SHALL define a `BaseProofreadingBackend` abstract class with a `proofread(text: str, language: str) -> ProofreadingResult` method and a `get_supported_languages() -> list` method
3. WHEN a custom Backend class is specified in the `BACKENDS` section of the Settings_Dictionary, THE Backend_Registry SHALL load and instantiate that class
4. IF a configured Backend class cannot be imported, THEN THE Backend_Registry SHALL raise an `ImproperlyConfigured` exception with the class path that failed
5. THE Plugin SHALL pass backend-specific configuration options from the settings dictionary to the Backend constructor as keyword arguments
6. THE `ProofreadingResult` SHALL contain the original text, the corrected text, and a list of Diff_Annotation objects
7. THE Backend_Registry SHALL support multiple named Backend instances simultaneously, allowing different backends to serve different languages
8. WHEN the Proofreading_Engine receives a proofreading request for a given language, THE Proofreading_Engine SHALL consult the Language_Routing_Table to select the appropriate Backend
9. WHEN the Translation_Engine receives a translation request for a given language pair, THE Translation_Engine SHALL consult the Language_Routing_Table to select the appropriate Backend
10. THE Backend_Registry SHALL expose a `get_backend_for_proofreading(language: str) -> BaseProofreadingBackend` method that resolves the Language_Routing_Table and returns the correct Backend instance
11. THE Backend_Registry SHALL expose a `get_backend_for_translation(source_language: str, target_language: str) -> BaseTranslationBackend` method that resolves the Language_Routing_Table and returns the correct Backend instance
12. IF no Backend in the Backend_Registry supports the requested language or language pair, THEN THE Backend_Registry SHALL raise an `UnsupportedLanguageError`
13. A single Backend class MAY implement both `BaseTranslationBackend` and `BaseProofreadingBackend` to serve as a combined backend for a service that provides both capabilities

### Requirement 3: Miðeind Proofreading Backend

**User Story:** As a content editor, I want my Icelandic text to be proofread using Miðeind's Málstaður API, so that I can correct grammar and spelling errors before publishing.

#### Acceptance Criteria

1. THE Miðeind_Backend SHALL send proofreading requests to the Málstaður_API endpoint `POST /v1/grammar`
2. THE Miðeind_Backend SHALL authenticate requests using the `X-API-KEY` header with the key provided in backend configuration
3. WHEN the Málstaður_API returns a successful response, THE Miðeind_Backend SHALL parse the response into a `ProofreadingResult` containing `originalText`, `changedText`, and a list of Diff_Annotation objects
4. WHEN the Málstaður_API returns HTTP 401 or 403, THEN THE Miðeind_Backend SHALL raise an `AuthenticationError` with a message indicating invalid or exhausted API credentials
5. WHEN the Málstaður_API returns HTTP 504 or the request exceeds a configurable timeout, THEN THE Miðeind_Backend SHALL raise a `BackendTimeoutError`
6. WHEN the Málstaður_API returns HTTP 400, THEN THE Miðeind_Backend SHALL raise a `BackendRequestError` with details from the response body
7. WHEN the Málstaður_API returns HTTP 500, THEN THE Miðeind_Backend SHALL raise a `BackendError` indicating a server-side failure
8. Each Diff_Annotation SHALL contain `orig_start_idx`, `orig_end_idx`, `orig_string`, `changed_start_idx`, `changed_end_idx`, `changed_string`, and `change_type` fields
9. THE Miðeind_Backend SHALL implement `get_supported_languages()` returning the list of languages supported for proofreading by the Málstaður_API

### Requirement 4: Miðeind Translation Backend

**User Story:** As a content editor, I want to translate content between any language pair supported by Miðeind's translation service, so that I can efficiently produce multilingual content.

#### Acceptance Criteria

1. THE Miðeind_Backend SHALL send translation requests to the Málstaður_API endpoint `POST /v1/translate`
2. THE Miðeind_Backend SHALL include `source_language` and `target_language` parameters in translation requests
3. THE Miðeind_Backend SHALL support all language pairs available through the Málstaður_API
4. THE Miðeind_Backend SHALL provide a `get_supported_language_pairs()` method that queries the Málstaður_API for available language pairs
5. WHEN the Málstaður_API returns a successful translation response, THE Miðeind_Backend SHALL return the translated text as a string
6. WHEN the Málstaður_API returns an error during translation, THEN THE Miðeind_Backend SHALL raise the appropriate error type consistent with the proofreading error handling (AuthenticationError, BackendTimeoutError, BackendRequestError, or BackendError)
7. IF a language pair not available in the Supported_Language_Pairs is requested, THEN THE Miðeind_Backend SHALL raise a `UnsupportedLanguagePairError`

### Requirement 5: Page-Level Translation

**User Story:** As a content editor, I want to translate an entire Wagtail page from one locale to another, so that I can quickly produce translated versions of my content.

#### Acceptance Criteria

1. WHEN a page is copied to a new locale via Wagtail's `simple_translation` module, THE Translation_Engine SHALL automatically translate all translatable text fields using the configured translation Backend
2. THE Translation_Engine SHALL translate plain text fields, rich text fields, and text content within StreamField blocks
3. WHILE a page translation is in progress, THE Plugin SHALL display a progress indicator in the Wagtail admin interface
4. WHEN page translation completes successfully, THE Plugin SHALL save the translated content as a draft page in the target locale
5. IF translation of any field fails, THEN THE Plugin SHALL log the error, skip the failed field, and continue translating remaining fields
6. WHEN translation completes with skipped fields, THE Plugin SHALL display a warning listing the fields that could not be translated

### Requirement 6: Inline Proofreading in Editor

**User Story:** As a content editor, I want to proofread Icelandic text directly within the Wagtail editor, so that I can fix grammar and spelling errors without leaving the page editing interface.

#### Acceptance Criteria

1. THE Editor_Extension SHALL add a "Proofread" button to Draftail rich text editor toolbars for configured text fields
2. WHEN the editor activates the Proofread button, THE Editor_Extension SHALL send the current field content to the Proofreading_Engine
3. WHEN proofreading results are returned, THE Editor_Extension SHALL display Diff_Annotations as inline highlights within the text field
4. WHEN the editor clicks on a highlighted annotation, THE Editor_Extension SHALL display a popover showing the original text, the suggested correction, and the change type
5. WHEN the editor accepts a suggestion from the popover, THE Editor_Extension SHALL apply the correction to the field content
6. WHEN the editor dismisses a suggestion from the popover, THE Editor_Extension SHALL remove the highlight for that annotation
7. THE Editor_Extension SHALL provide a "Dismiss All" action to clear all remaining highlights at once
8. IF the Proofreading_Engine returns an error, THEN THE Editor_Extension SHALL display a notification message describing the error to the editor

### Requirement 7: Inline Translation in Editor

**User Story:** As a content editor, I want to translate the content of individual text fields directly within the Wagtail editor, so that I can translate specific sections without triggering a full page translation.

#### Acceptance Criteria

1. THE Editor_Extension SHALL add a "Translate" button to Draftail rich text editor toolbars for configured text fields
2. WHEN the editor activates the Translate button, THE Editor_Extension SHALL display a language pair selector populated with the Supported_Language_Pairs from the configured translation Backend
3. WHEN the editor confirms the translation direction, THE Editor_Extension SHALL send the current field content to the Translation_Engine with the selected language pair
4. WHEN translation results are returned, THE Editor_Extension SHALL display the translated text in a preview panel adjacent to the field
5. WHEN the editor accepts the translation from the preview panel, THE Editor_Extension SHALL replace the field content with the translated text
6. WHEN the editor cancels the translation from the preview panel, THE Editor_Extension SHALL discard the translated text and retain the original content
7. IF the Translation_Engine returns an error, THEN THE Editor_Extension SHALL display a notification message describing the error to the editor

### Requirement 8: Backend Error Handling and Resilience

**User Story:** As a developer, I want the plugin to handle backend failures gracefully, so that errors in external services do not crash the Wagtail admin or corrupt content.

#### Acceptance Criteria

1. THE Plugin SHALL define a base `BackendError` exception class from which all backend-specific exceptions inherit
2. WHEN a Backend raises an unexpected exception not derived from `BackendError`, THE Plugin SHALL catch the exception, log it with full traceback, and re-raise it as a `BackendError`
3. THE Plugin SHALL implement configurable request timeouts for all Backend HTTP calls with a default of 30 seconds
4. WHEN a Backend operation fails, THE Plugin SHALL ensure no partial modifications are persisted to page content
5. THE Plugin SHALL log all Backend interactions at DEBUG level including request URL, response status, and elapsed time

### Requirement 9: Demo Site

**User Story:** As a developer evaluating the plugin, I want to run a fully functional demo site with Docker, so that I can explore all plugin features without setting up a full Wagtail project.

#### Acceptance Criteria

1. THE Demo_Site SHALL be launchable using a single `docker compose up` command from the repository root
2. THE Demo_Site SHALL include a pre-configured Wagtail instance with the Plugin installed and a Miðeind_Backend configured
3. THE Demo_Site SHALL include sample pages with Icelandic content for testing proofreading and translation features
4. THE Demo_Site SHALL provide instructions for supplying a Málstaður_API key via environment variable
5. IF no API key is provided, THEN THE Demo_Site SHALL start successfully and display a configuration warning in the Wagtail admin dashboard

### Requirement 10: Packaging and Distribution

**User Story:** As a developer, I want the plugin to follow modern Python packaging standards, so that I can reliably install and manage it as a dependency.

#### Acceptance Criteria

1. THE Plugin SHALL use `pyproject.toml` as the sole packaging configuration file
2. THE Plugin SHALL declare all required dependencies with minimum version constraints
3. THE Plugin SHALL be published to PyPI under the package name `wagtail-heimdallur`
4. THE Plugin SHALL include a LICENSE file with the MIT license text
5. THE Plugin SHALL include a comprehensive README with installation instructions, configuration examples, and usage documentation
6. THE Plugin SHALL use tox for running tests across the supported Python, Django, and Wagtail version matrix

### Requirement 11: Proofreading Result Serialization

**User Story:** As a developer extending the plugin, I want proofreading results to be serializable, so that I can cache, log, or transmit them between systems.

#### Acceptance Criteria

1. THE Proofreading_Engine SHALL serialize `ProofreadingResult` objects to JSON format
2. THE Proofreading_Engine SHALL deserialize JSON strings into `ProofreadingResult` objects
3. FOR ALL valid `ProofreadingResult` objects, serializing then deserializing SHALL produce an equivalent object (round-trip property)

### Requirement 13: Docker-Based Development and Testing Environment

**User Story:** As a developer contributing to the plugin, I want a Docker-based development environment, so that I can run the full test suite and develop without manually configuring Python versions, Django, or Wagtail dependencies on my host machine.

#### Acceptance Criteria

1. THE repository SHALL include a `Dockerfile` that provides an environment with Python 3.14, all plugin dependencies, and test tooling (pytest, hypothesis, tox)
2. THE repository SHALL include a `docker-compose.yml` at the repository root with a `tests` service for running the test suite
3. WHEN a developer runs `docker compose run tests`, THE container SHALL execute the full test suite and report results to stdout
4. THE `docker-compose.yml` SHALL volume-mount the source code directory so that code changes on the host are immediately reflected inside the container without rebuilding
5. THE Docker setup SHALL support running tox for matrix testing via `docker compose run tests tox`
6. THE Docker setup SHALL support running a specific test file or test function via `docker compose run tests pytest <path>`
7. THE `Dockerfile` SHALL install Node.js and npm for building the TypeScript frontend assets when needed

### Requirement 14: Feature Configuration and Language Routing

**User Story:** As a developer, I want fine-grained control over which features are enabled and which backend serves each language, so that I can tailor the plugin to my site's specific language support needs without running unnecessary services.

#### Acceptance Criteria

1. THE Settings_Dictionary SHALL accept a `LANGUAGE_ROUTING` structure that independently maps proofreading languages and translation language pairs to specific Backend identifiers
2. WHEN multiple Backends are configured, THE Plugin SHALL allow each Backend to serve a distinct set of languages for proofreading independently of its translation language pairs
3. THE Plugin SHALL allow a developer to enable proofreading for Icelandic via one Backend while enabling proofreading for English via a different Backend within the same Settings_Dictionary
4. THE Plugin SHALL allow a developer to enable translation without enabling proofreading, and vice versa, by setting the corresponding Feature_Toggle
5. WHEN `inline_proofreading` Feature_Toggle is set to `False`, THE Plugin SHALL not expose the Proofread button in the Editor_Extension regardless of Backend configuration
6. WHEN `inline_translation` Feature_Toggle is set to `False`, THE Plugin SHALL not expose the Translate button in the Editor_Extension regardless of Backend configuration
7. WHEN `page_translation` Feature_Toggle is set to `False`, THE Plugin SHALL not register the page translation hook regardless of Backend configuration
8. THE Plugin SHALL support per-Backend `enabled` configuration allowing a developer to disable a specific Backend without removing it from the Settings_Dictionary
9. WHEN a Backend has `enabled` set to `False`, THE Backend_Registry SHALL not route any language requests to that Backend
10. IF all Backends capable of a requested operation are disabled, THEN THE Plugin SHALL raise a `NoAvailableBackendError` with a message identifying the operation and language
11. THE Plugin SHALL provide a Django management command `heimdallur_check` that validates the current configuration and reports active features, registered backends, and language routing assignments
12. WHEN the `heimdallur_check` command is run, THE command SHALL list each enabled feature, each active Backend with its supported languages, and the resolved Language_Routing_Table
