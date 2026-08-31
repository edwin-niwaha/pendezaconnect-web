import base64
import logging
from email.utils import formataddr, parseaddr

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class ResendEmailBackend(BaseEmailBackend):
    """Send Django EmailMessage objects through Resend's HTTPS API."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.api_key = getattr(settings, "RESEND_API_KEY", "")
        self.api_url = getattr(settings, "RESEND_API_URL", "https://api.resend.com/emails")
        self.timeout = getattr(settings, "EMAIL_TIMEOUT", 10)

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not self.api_key:
            if self.fail_silently:
                return 0
            raise ValueError("RESEND_API_KEY is required when using ResendEmailBackend.")

        sent_count = 0
        for message in email_messages:
            try:
                response = requests.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=self._build_payload(message),
                    timeout=self.timeout,
                )
                if response.status_code >= 400:
                    logger.error(
                        "Resend rejected email '%s' with status %s: %s",
                        message.subject,
                        response.status_code,
                        response.text[:1000],
                    )
                response.raise_for_status()
                sent_count += 1
            except Exception:
                logger.exception("Failed to send email through Resend: %s", message.subject)
                if not self.fail_silently:
                    raise
        return sent_count

    def _build_payload(self, message):
        text_body, html_body = self._message_bodies(message)
        from_email = self._format_sender(
            getattr(settings, "RESEND_FROM_EMAIL", "")
            or message.from_email
            or getattr(settings, "DEFAULT_FROM_EMAIL", "")
        )

        payload = {
            "from": from_email,
            "to": list(message.to),
            "subject": message.subject,
        }
        if text_body:
            payload["text"] = text_body
        if html_body:
            payload["html"] = html_body
        if message.cc:
            payload["cc"] = list(message.cc)
        if message.bcc:
            payload["bcc"] = list(message.bcc)
        if message.reply_to:
            payload["reply_to"] = list(message.reply_to)

        attachments = self._attachments(message)
        if attachments:
            payload["attachments"] = attachments

        return payload

    @staticmethod
    def _format_sender(from_email):
        name, address = parseaddr(from_email)
        if not address:
            return from_email
        if name:
            return formataddr((name, address))
        return address

    @staticmethod
    def _message_bodies(message):
        if getattr(message, "content_subtype", "plain") == "html":
            text_body = ""
            html_body = message.body
        else:
            text_body = message.body
            html_body = ""

        for alternative in getattr(message, "alternatives", []):
            content = alternative[0]
            mimetype = alternative[1]
            if mimetype == "text/html":
                html_body = content
            elif mimetype == "text/plain":
                text_body = content

        return text_body, html_body

    @staticmethod
    def _attachments(message):
        attachments = []
        for attachment in message.attachments:
            if hasattr(attachment, "get_payload"):
                filename = attachment.get_filename()
                content = attachment.get_payload(decode=True)
            else:
                filename, content, _mimetype = attachment
                if isinstance(content, str):
                    content = content.encode("utf-8")

            if not filename or content is None:
                continue

            attachments.append(
                {
                    "filename": filename,
                    "content": base64.b64encode(content).decode("ascii"),
                }
            )
        return attachments
