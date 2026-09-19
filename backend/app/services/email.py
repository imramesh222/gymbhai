"""Email, for sign-in codes (PLAN.md §5.5): `console` in development, `smtp` live."""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

log = logging.getLogger("gymbahi.email")


class EmailError(Exception):
    pass


def send(to: str, subject: str, body: str) -> None:
    if settings.email_provider == "console":
        log.info("Email to %s: %s\n%s", to, subject, body)
        return
    if not settings.smtp_host:
        raise EmailError("EMAIL_PROVIDER is smtp but SMTP_HOST is not set.")
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password or "")
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailError(str(exc)) from exc
