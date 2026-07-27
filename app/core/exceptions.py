class EmailAlreadyRegisteredError(Exception):
    """Raised when registration uses an email owned by another account."""


class InvalidCredentialsError(Exception):
    """Raised when an email and password combination is invalid."""


class InactiveAccountError(Exception):
    """Raised when an inactive account attempts to authenticate."""
