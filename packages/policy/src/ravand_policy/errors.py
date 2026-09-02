"""Typed fail-closed errors."""


class FailClosed(Exception):
    """Policy could not allow the action."""

    exit_code = 3

    def __init__(self, message: str = "fail closed") -> None:
        super().__init__(message)
        self.exit_code = type(self).exit_code


class PolicyDenied(FailClosed):
    """An explicit deny (mismatch, classification, deny list)."""

    exit_code = 3


class UnknownAgent(FailClosed):
    """Agent id is not in the registry or harness."""

    exit_code = 5
