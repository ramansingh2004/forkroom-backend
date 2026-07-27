class EmailAlreadyRegisteredError(Exception):
    """Raised when registration uses an email owned by another account."""
