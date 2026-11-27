import logging

from django.http import JsonResponse


def csrf_failure(request, reason=""):
    """Return a predictable API error; Django logs the reason through our redacting filter."""
    return JsonResponse({"detail": "CSRF verification failed."}, status=403)


class SafeCsrfLogFilter(logging.Filter):
    """Keep useful CSRF failure categories while discarding dynamic header values and URLs."""

    def filter(self, record):
        message = record.getMessage().lower()
        if "origin checking failed" in message or "origin header" in message:
            category = "origin_rejected"
        elif "referer" in message:
            category = "referer_rejected"
        elif "csrf cookie" in message or "cookie not set" in message:
            category = "cookie_missing"
        elif "csrf token" in message and ("missing" in message or "not provided" in message):
            category = "token_missing"
        elif "csrf token" in message:
            category = "token_rejected"
        else:
            category = "request_rejected"

        record.msg = f"CSRF verification rejected ({category})"
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        return True
