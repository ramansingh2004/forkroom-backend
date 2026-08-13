from cryptography.fernet import Fernet, InvalidToken

from app.core.exceptions import IntegrationConfigurationError


class IntegrationTokenCipher:
    def __init__(self, key: str | None) -> None:
        if key is None or not key.strip():
            raise IntegrationConfigurationError("Integration token encryption is not configured")
        try:
            self._fernet = Fernet(key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as error:
            raise IntegrationConfigurationError(
                "Integration token encryption key is invalid"
            ) from error

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError) as error:
            raise IntegrationConfigurationError(
                "Stored integration credentials could not be decrypted"
            ) from error
