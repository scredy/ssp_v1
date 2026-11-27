"""Django email backend for Brevo's HTTPS Transactional Email API."""
import base64
import json
import logging
import os
import socket
from email.utils import parseaddr
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend


logger = logging.getLogger(__name__)
BREVO_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"


def _address(value):
    name, email = parseaddr(value or "")
    return {"email": email, **({"name": name} if name else {})}


def _attachment(filename, content, mimetype=None):
    if hasattr(content, "get_payload"):
        payload = content.get_payload(decode=True)
        content = payload if payload is not None else content.as_string().encode()
    if isinstance(content, str):
        content = content.encode()
    result = {"name": filename, "content": base64.b64encode(content).decode("ascii")}
    return result


class BrevoEmailBackend(BaseEmailBackend):
    """Send Django EmailMessage objects through Brevo without SMTP or retries."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.api_key = os.environ.get("BREVO_API_KEY", "").strip()
        try:
            self.timeout = float(os.environ.get("BREVO_TIMEOUT_SECONDS", "10"))
            if self.timeout <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ImproperlyConfigured("BREVO_TIMEOUT_SECONDS must be a positive number") from None

    @staticmethod
    def _payload(message):
        sender = _address(message.from_email)
        if not sender["email"]:
            raise ValueError("The configured sender address is invalid")
        payload = {
            "sender": sender,
            "to": [_address(address) for address in message.to],
            "subject": message.subject,
        }
        if message.cc:
            payload["cc"] = [_address(address) for address in message.cc]
        if message.bcc:
            payload["bcc"] = [_address(address) for address in message.bcc]
        if message.reply_to:
            payload["replyTo"] = _address(message.reply_to[0]) if len(message.reply_to) == 1 else {
                "email": _address(message.reply_to[0])["email"]
            }

        alternatives = getattr(message, "alternatives", ()) or ()
        html = next((content for content, mimetype in alternatives if mimetype == "text/html"), None)
        if html is not None:
            payload["htmlContent"] = html
            payload["textContent"] = message.body
        elif getattr(message, "content_subtype", "plain") == "html":
            payload["htmlContent"] = message.body
        else:
            payload["textContent"] = message.body

        if message.attachments:
            attachments = []
            for attachment in message.attachments:
                if isinstance(attachment, tuple):
                    filename, content, mimetype = (attachment + (None,))[:3]
                else:
                    filename = attachment.get_filename()
                    content = attachment
                    mimetype = attachment.get_content_type()
                if filename:
                    attachments.append(_attachment(filename, content, mimetype))
            if attachments:
                payload["attachment"] = attachments
        if message.extra_headers:
            payload["headers"] = {str(key): str(value) for key, value in message.extra_headers.items()}
        return payload

    def _send(self, message):
        if not self.api_key:
            raise ImproperlyConfigured("BREVO_API_KEY is not configured")
        payload = self._payload(message)
        request = Request(
            BREVO_EMAIL_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "api-key": self.api_key,
                "accept": "application/json",
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                status_code = response.getcode()
                response_data = response.read()
        except HTTPError as exc:
            status_code = exc.code
            category = {
                400: "unauthorized_sender_or_invalid_request",
                401: "invalid_api_key",
                403: "unauthorized_sender",
                429: "rate_limited",
            }.get(
                status_code, "provider_error" if status_code >= 500 else "request_rejected"
            )
            logger.warning("Brevo email rejected category=%s status=%s", category, status_code)
            return False
        except (TimeoutError, socket.timeout):
            logger.warning("Brevo email delivery outcome unknown category=timeout")
            return False
        except URLError as exc:
            category = "timeout" if isinstance(exc.reason, (TimeoutError, socket.timeout)) else "connection_error"
            logger.warning("Brevo email delivery outcome unknown category=%s", category)
            return False
        except OSError:
            logger.warning("Brevo email delivery outcome unknown category=connection_error")
            return False

        if status_code != 201:
            logger.warning("Brevo email rejected category=unexpected_status status=%s", status_code)
            return False
        try:
            response_json = json.loads(response_data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("Brevo email rejected category=invalid_response status=%s", status_code)
            return False
        if not isinstance(response_json, dict) or not isinstance(response_json.get("messageId"), str) or not response_json["messageId"].strip():
            logger.warning("Brevo email rejected category=invalid_response status=%s", status_code)
            return False
        logger.info("Brevo email accepted status=%s", status_code)
        return True

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        sent = 0
        for message in email_messages:
            if not message.recipients():
                continue
            try:
                sent += int(self._send(message))
            except Exception as exc:
                logger.warning("Brevo email failed category=%s", type(exc).__name__)
                if not self.fail_silently:
                    raise
        return sent
