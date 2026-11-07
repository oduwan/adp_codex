"""Stable API errors and CLI exit codes."""


class ADPError(Exception):
    """A controlled refusal, safe to display without raw command output."""

    code = 3


class ConfigurationError(ADPError):
    code = 2


class Conflict(ADPError):
    code = 4


class GitError(ADPError):
    code = 5


class AuthorityError(ADPError):
    code = 6
