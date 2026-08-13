import pytest
from cryptography.fernet import Fernet

from app.core.exceptions import IntegrationConfigurationError
from app.integrations.token_encryption import IntegrationTokenCipher


def test_integration_token_cipher_round_trip() -> None:
    cipher = IntegrationTokenCipher(Fernet.generate_key().decode("ascii"))

    encrypted = cipher.encrypt("xoxb-secret-token")

    assert encrypted != "xoxb-secret-token"
    assert cipher.decrypt(encrypted) == "xoxb-secret-token"


def test_integration_token_cipher_requires_valid_key() -> None:
    with pytest.raises(IntegrationConfigurationError):
        IntegrationTokenCipher(None)

    with pytest.raises(IntegrationConfigurationError):
        IntegrationTokenCipher("not-a-fernet-key")
