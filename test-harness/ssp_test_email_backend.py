"""File-only mail backend for acceptance tests; no SMTP or external delivery."""
from pathlib import Path
from uuid import uuid4

from django.core.mail.backends.base import BaseEmailBackend


class FileEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        output = Path(__file__).resolve().parent / "artifacts" / "emails"
        output.mkdir(parents=True, exist_ok=True)
        sent = 0
        for message in email_messages:
            message_path = output / f"{uuid4().hex}.eml"
            message_path.write_bytes(message.message().as_bytes())
            sent += 1
        return sent
