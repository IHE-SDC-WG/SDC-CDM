"""Errors with stable command-line exit semantics."""


class SdcCdmError(RuntimeError):
    """Base error for expected SDC-CDM command failures."""


class ManifestError(SdcCdmError):
    """Raised when the database manifest is invalid."""


class MigrationHashMismatch(SdcCdmError):
    """Raised when an immutable applied migration changed on disk."""


class UsageError(SdcCdmError):
    """Raised for a command invocation that lacks a required target."""
