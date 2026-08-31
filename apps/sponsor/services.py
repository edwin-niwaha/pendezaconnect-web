import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def _valid_recipients(*recipients):
    invalid_values = {"", "none", "null", "false"}
    valid = []
    seen = set()

    for email in recipients:
        if not email:
            continue

        normalized_email = email.strip()

        if normalized_email.lower() in invalid_values:
            continue

        if normalized_email.lower() in seen:
            continue

        valid.append(normalized_email)
        seen.add(normalized_email.lower())

    return valid


def sponsor_feedback_recipients():
    return _valid_recipients(
        getattr(settings, "PROGS_ADMIN_EMAIL", ""),
        getattr(settings, "BOO_EMAIL", ""),
        getattr(settings, "ED_EMAIL", ""),
    )


def get_from_email():
    return (
        getattr(settings, "DEFAULT_FROM_EMAIL", "")
        or getattr(settings, "RESEND_FROM_EMAIL", "")
        or getattr(settings, "EMAIL_HOST_USER", "")
    )


def send_sponsor_feedback_email(feedback):
    sponsor = feedback.sponsor
    internal_recipients = sponsor_feedback_recipients()
    sponsor_recipients = _valid_recipients(getattr(sponsor, "email", ""))
    from_email = get_from_email()

    if not from_email:
        feedback.email_error = "Sponsor feedback email skipped: sender email not configured."
        feedback.save(update_fields=["email_error", "updated_at"])
        logger.warning(feedback.email_error)
        return False

    if not internal_recipients:
        feedback.email_error = "Sponsor feedback email skipped: no internal recipients configured."
        feedback.save(update_fields=["email_error", "updated_at"])
        logger.warning(feedback.email_error)
        return False

    internal_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background:#f4f7fa; padding:20px;">
        <div style="max-width:700px;margin:auto;background:#fff;padding:25px;border-radius:8px;border:1px solid #ddd;">
            <h2 style="color:#0d6efd;">New Sponsor Feedback Submitted</h2>

            <p>A sponsor has submitted feedback through the Sponsor Portal.</p>

            <p><strong>Sponsor:</strong> {sponsor.first_name} {sponsor.last_name}</p>
            <p><strong>Sponsor ID:</strong> {sponsor.prefixed_id}</p>
            <p><strong>Email:</strong> {sponsor.email}</p>
            <p><strong>Subject:</strong> {feedback.subject}</p>

            <hr>

            <h4>Message</h4>
            <div style="background:#f8f9fa;padding:15px;border-left:4px solid #0d6efd;">
                {feedback.message}
            </div>

            <hr>

            <p style="font-size:12px;color:#6c757d;">
                Pendeza Uganda Sponsorship Management System
            </p>
        </div>
    </body>
    </html>
    """

    sponsor_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background:#f4f7fa; padding:20px;">
        <div style="max-width:700px;margin:auto;background:#fff;padding:25px;border-radius:8px;border:1px solid #ddd;">
            <h2 style="color:#0d6efd;">Thank You for Your Feedback</h2>

            <p>Dear {sponsor.first_name},</p>

            <p>
                Thank you for contacting Pendeza Uganda. We have successfully
                received your feedback and our team will review it shortly.
            </p>

            <p><strong>Your feedback subject:</strong> {feedback.subject}</p>

            <div style="background:#f8f9fa;padding:15px;border-left:4px solid #0d6efd;">
                {feedback.message}
            </div>

            <p>
                We appreciate your continued support and partnership.
            </p>

            <p>
                Kind regards,<br>
                <strong>Pendeza Uganda Team</strong>
            </p>

            <hr>

            <p style="font-size:12px;color:#6c757d;">
                This is an automated confirmation from Pendeza Uganda.
            </p>
        </div>
    </body>
    </html>
    """

    try:
        internal_email = EmailMultiAlternatives(
            subject=f"Sponsor Feedback: {feedback.subject}",
            body=strip_tags(internal_html),
            from_email=from_email,
            to=internal_recipients,
        )
        internal_email.attach_alternative(internal_html, "text/html")
        internal_email.send(fail_silently=False)

        sponsor_sent = False

        if sponsor_recipients:
            sponsor_email = EmailMultiAlternatives(
                subject="We Have Received Your Feedback",
                body=strip_tags(sponsor_html),
                from_email=from_email,
                to=sponsor_recipients,
            )
            sponsor_email.attach_alternative(sponsor_html, "text/html")
            sponsor_email.send(fail_silently=False)
            sponsor_sent = True
        else:
            logger.warning(
                "Sponsor feedback %s confirmation skipped: sponsor email missing.",
                feedback.id,
            )

        feedback.email_sent_at = timezone.now()
        feedback.email_error = ""
        feedback.save(
            update_fields=[
                "email_sent_at",
                "email_error",
                "updated_at",
            ]
        )

        logger.info(
            "Sponsor feedback %s internal email sent to %s. Sponsor confirmation sent: %s",
            feedback.id,
            ", ".join(internal_recipients),
            sponsor_sent,
        )

        return True

    except Exception as exc:
        feedback.email_error = str(exc)
        feedback.save(update_fields=["email_error", "updated_at"])

        logger.exception(
            "Sponsor feedback %s email failed: %s",
            feedback.id,
            exc,
        )

        return False
