from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Hash a password with Argon2 using pwdlib's recommended settings."""
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return whether a plaintext password matches its stored hash."""
    return password_hasher.verify(password, password_hash)
