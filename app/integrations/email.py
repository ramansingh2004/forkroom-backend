import asyncio
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import Settings


class EmailService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send_verification_email(
        self,
        recipient: str,
        display_name: str,
        token: str,
    ) -> None:
        url = f"{self._settings.frontend_url.rstrip('/')}/verify-email?token={token}"
        await self._send(
            recipient=recipient,
            subject="Verify your ForkRoom email",
            text=(
                f"Hi {display_name},\n\n"
                f"Verify your ForkRoom email by opening this link:\n{url}\n\n"
                f"This link expires in "
                f"{self._settings.email_verification_expire_minutes} minutes."
            ),
        )

    async def send_password_reset_email(
        self,
        recipient: str,
        display_name: str,
        token: str,
    ) -> None:
        url = f"{self._settings.frontend_url.rstrip('/')}/reset-password?token={token}"
        await self._send(
            recipient=recipient,
            subject="Reset your ForkRoom password",
            text=(
                f"Hi {display_name},\n\n"
                f"Reset your ForkRoom password by opening this link:\n{url}\n\n"
                f"This link expires in "
                f"{self._settings.password_reset_expire_minutes} minutes. "
                "If you did not request this, you can ignore this email."
            ),
        )

    async def _send(self, recipient: str, subject: str, text: str) -> None:
        message = EmailMessage()
        message["From"] = formataddr(
            (self._settings.mail_from_name, self._settings.mail_from_address)
        )
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(text)
        await asyncio.to_thread(self._send_sync, message)

    def _send_sync(self, message: EmailMessage) -> None:
        with smtplib.SMTP(
            self._settings.smtp_host,
            self._settings.smtp_port,
            timeout=10,
        ) as smtp:
            if self._settings.smtp_use_tls:
                smtp.starttls()
            if self._settings.smtp_username and self._settings.smtp_password:
                smtp.login(
                    self._settings.smtp_username,
                    self._settings.smtp_password,
                )
            smtp.send_message(message)
