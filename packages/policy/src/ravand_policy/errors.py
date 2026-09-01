"""Typed fail-closed errors."""


class FailClosed(Exception):
    """Policy could not allow the action."""


class PolicyDenied(FailClosed):
    """An explicit deny (mismatch, classification, deny list)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.exit_code = 3


class UnknownAgent(FailClosed):
    """Agent id is not in the registry or harness."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.exit_code = 5
