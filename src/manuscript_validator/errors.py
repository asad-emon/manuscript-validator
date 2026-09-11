"""Exception hierarchy.

Pipeline stages raise these; `pipeline.run` is responsible for turning them
into a `PipelineResult` the UI and CLI can render. Semantic-check failures are
deliberately *not* exceptions -- they degrade to a `check_failed` violation so
a missing API key or a dropped network connection never blocks the rest of the
run (spec sections 4.2 and 13).
"""


class ManuscriptValidatorError(Exception):
    """Base class for every error this application raises."""


class DocumentError(ManuscriptValidatorError):
    """The input file could not be opened, parsed, or written."""


class UnsupportedDocumentError(DocumentError):
    """The file is not a readable .docx (wrong format, or corrupt)."""


class RuleConfigError(ManuscriptValidatorError):
    """A rule config file is malformed.

    The message must name the offending ``rule_id`` and field: a journal
    template is edited by humans, and silent acceptance of a bad rule is worse
    than a loud failure at load time.
    """


class SegmentationError(ManuscriptValidatorError):
    """Section boundaries could not be established at all."""


class FixApplicationError(ManuscriptValidatorError):
    """A fix action failed against the document it was planned for."""


class SettingsError(ManuscriptValidatorError):
    """The settings store could not be read or written."""


class UnsupportedPlatformError(SettingsError):
    """No secure secret store is available on this platform.

    Raised rather than silently falling back to plaintext -- the dev-only
    backend must be opted into explicitly via an environment variable.
    """
