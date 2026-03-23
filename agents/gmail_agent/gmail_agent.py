import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import datetime

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from agents.gmail_agent.config import (
    SMTP_HOST, SMTP_PORT, EMAIL_USER, EMAIL_PASS,
)

logger = logging.getLogger("agents.gmail_agent.sender")


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


class EmailSender:
    """Low-level SMTP email sender with retry logic."""

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.smtp_host = smtp_host or SMTP_HOST
        self.smtp_port = smtp_port or SMTP_PORT
        self.user = user or EMAIL_USER
        self.password = password or EMAIL_PASS

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((smtplib.SMTPException, ConnectionError)),
        reraise=False,
    )
    def send(self, to_email: str, subject: str, body: str) -> bool:
        """Send one email via Gmail SMTP with TLS. Retries up to 3× on SMTP errors."""
        if not self.user or not self.password:
            logger.warning(f"[{_ts()}] ⚠ SMTP credentials not set — skipping email to {to_email}")
            return False

        msg = MIMEMultipart()
        msg["From"] = self.user
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.user, self.password)
                server.send_message(msg)
            logger.info(f"[{_ts()}] 📧 Email sent → {to_email}")
            return True
        except (smtplib.SMTPException, ConnectionError) as exc:
            logger.error(f"[{_ts()}] ❌ SMTP error sending to {to_email}: {exc}")
            raise        # let tenacity retry
        except Exception as exc:
            logger.error(f"[{_ts()}] ❌ Unexpected email error: {exc}")
            return False


# Singleton sender
email_sender = EmailSender()
