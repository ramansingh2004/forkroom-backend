class EmailAlreadyRegisteredError(Exception):
    """Raised when registration uses an email owned by another account."""


class InvalidCredentialsError(Exception):
    """Raised when an email and password combination is invalid."""


class InactiveAccountError(Exception):
    """Raised when an inactive account attempts to authenticate."""


class InvalidTokenError(Exception):
    """Raised when an authentication token is invalid, expired, or reused."""


class EmailNotVerifiedError(Exception):
    """Raised when an account must verify its email before authentication."""


class InvalidActionTokenError(Exception):
    """Raised when an email verification or password reset token is invalid."""
