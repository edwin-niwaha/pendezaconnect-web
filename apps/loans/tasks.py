import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)

BLOCKED_BORROWER_EMAILS = {"pendezaug@gmail.com"}


@shared_task
def send_push_loan_reminders():
    from apps.loans.services.push_reminders import loan_reminder_service

    return loan_reminder_service.send_due_soon()


def is_blocked_borrower_email(email):
    return (email or "").strip().lower() in BLOCKED_BORROWER_EMAILS


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

        email_key = normalized_email.lower()
        if is_blocked_borrower_email(email_key):
            logger.info(
                "Loan email recipient skipped because it is blocked: %s",
                email_key,
            )
            continue

        if email_key in seen:
            continue

        valid.append(normalized_email)
        seen.add(email_key)

    return valid


def _role_email_recipients(*roles):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return _valid_recipients(
        *User.objects.filter(
            is_active=True,
        )
        .filter(Q(profile__role__in=roles) | Q(profile__staff_role__in=roles))
        .values_list("email", flat=True)
    )


def _approval_recipients(*setting_names, roles=()):
    configured_recipients = [getattr(settings, setting_name, "") for setting_name in setting_names]
    return _valid_recipients(
        *configured_recipients,
        *_role_email_recipients(*roles),
    )


def _loan_stage_payload(loan, stage_status, actor_name, base_url):
    borrower_name = getattr(loan.borrower, "full_name", str(loan.borrower))
    amount = f"UGX {loan.principal_amount:,.2f}"
    applications_url = f"{base_url.rstrip('/')}/loans/applications/"
    disburse_url = f"{base_url.rstrip('/')}/loans/disburse/"

    if stage_status == "pending":
        return {
            "subject": f"New Loan Application {loan.id} Requires BOO Review",
            "recipients": _approval_recipients("BOO_EMAIL", roles=("boo",)),
            "heading": "BOO approval required",
            "message": (
                f"Loan #{loan.id} for {borrower_name} ({amount}) was submitted by "
                f"{actor_name}. Please review it for BOO approval."
            ),
            "action_label": "Review Loan",
            "action_url": applications_url,
        }

    if stage_status == "boo_approved":
        return {
            "subject": f"Loan {loan.id} Approved by BOO",
            "recipients": _approval_recipients("HOF_EMAIL", roles=("hof",)),
            "heading": "HOF approval required",
            "message": (
                f"Loan #{loan.id} for {borrower_name} ({amount}) was approved by "
                f"{actor_name}. Please review it for HOF approval."
            ),
            "action_label": "Review Loan",
            "action_url": applications_url,
        }

    if stage_status == "hof_approved":
        return {
            "subject": f"Loan {loan.id} Approved by HOF",
            "recipients": _approval_recipients("ED_EMAIL", roles=("ed",)),
            "heading": "ED approval required",
            "message": (
                f"Loan #{loan.id} for {borrower_name} ({amount}) was approved by "
                f"{actor_name}. Please review it for ED approval."
            ),
            "action_label": "Review Loan",
            "action_url": applications_url,
        }

    if stage_status == "approved":
        return {
            "subject": f"Loan {loan.id} Fully Approved",
            "recipients": _approval_recipients(
                "ACCOUNTANT_EMAIL",
                roles=("accountant",),
            ),
            "heading": "Loan ready for disbursement",
            "message": (
                f"Loan #{loan.id} for {borrower_name} ({amount}) was fully approved by "
                f"{actor_name}. Please proceed with disbursement."
            ),
            "action_label": "Disburse Loan",
            "action_url": disburse_url,
        }

    return None


def _loan_approval_payload(loan, new_status, approver_name, base_url):
    return _loan_stage_payload(loan, new_status, approver_name, base_url)


def _approval_email_html(heading, message, action_label, action_url):
    return f"""
    <html>
    <body style="font-family:Arial,sans-serif;background:#f5f7fb;padding:24px;color:#344054;">
      <div style="max-width:620px;margin:0 auto;background:#ffffff;border:1px solid #dfe5ef;border-radius:8px;padding:24px;">
        <h2 style="margin:0 0 14px;color:#182230;">{heading}</h2>
        <p style="font-size:15px;line-height:1.55;">{message}</p>
        <p style="margin:24px 0;">
          <a href="{action_url}" style="background:#175cd3;color:#ffffff;padding:11px 18px;text-decoration:none;border-radius:6px;font-weight:bold;">
            {action_label}
          </a>
        </p>
        <p style="font-size:12px;color:#667085;margin-top:24px;">Pendeza Uganda - Loan Management System</p>
      </div>
    </body>
    </html>
    """


# Generic task to send an email
def build_html_template(content: str, title: str) -> str:
    """
    Generates a styled HTML email template.
    """
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #f4f7fa; }}
            .card {{ border-radius: 10px; max-width: 600px; margin: 0 auto; }}
            .card-header {{ background-color: #007bff; padding: 1rem; }}
            .card-body {{ padding: 30px; background-color: #ffffff; }}
            .btn-view {{ 
                background-color: #4CAF50; 
                color: white; 
                padding: 12px 20px; 
                text-decoration: none; 
                border-radius: 5px; 
                font-size: 16px; 
                display: inline-block;
                transition: all 0.3s ease; 
                border: none;
            }}
            .btn-view:hover {{ 
                background-color: #218838; 
                transform: translateY(-2px); 
                box-shadow: 0 4px 8px rgba(0,0,0,0.2);
            }}
            .footer {{ font-size: 0.85rem; color: #6c757d; text-align: center; }}
        </style>
    </head>
    <body>
        <div class="container my-4">
            <div class="card shadow-sm">
                <div class="card-header text-white text-center">
                    <h3 class="mb-0">{title}</h3>
                </div>
                <div class="card-body">{content}</div>
                <div class="card-footer footer">
                    Pendeza Uganda - Loan Management System (LMS)
                </div>
            </div>
        </div>
    </body>
    </html>
    """


@shared_task(ignore_result=True)
def send_email_task(subject, text_content, html_content, recipients):
    """
    Celery task to send an email asynchronously.
    """
    recipients = _valid_recipients(*recipients)
    if not recipients:
        logger.info(
            "Email skipped because all recipients were invalid or blocked for subject: %s",
            subject,
        )
        return False
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.EMAIL_HOST_USER,
        to=recipients,
    )
    email.attach_alternative(html_content, "text/html")
    try:
        email.send(fail_silently=False)
        logger.info(f"Email sent to {', '.join(recipients)}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {', '.join(recipients)}: {e}")
        return False


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_html_email_task(self, subject, html_body, recipients):
    recipients = _valid_recipients(*recipients)
    if not recipients:
        logger.warning(
            "HTML email skipped because no recipients were configured for subject: %s",
            subject,
        )
        return False

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or getattr(settings, "EMAIL_HOST_USER", "")
    if not from_email:
        logger.warning(
            "HTML email skipped because DEFAULT_FROM_EMAIL is not configured for subject: %s",
            subject,
        )
        return False

    email = EmailMultiAlternatives(
        subject=subject,
        body=strip_tags(html_body),
        from_email=from_email,
        to=recipients,
    )
    email.attach_alternative(html_body, "text/html")
    sent_count = email.send(fail_silently=False)
    logger.info("HTML email sent to %s: %s", ", ".join(recipients), subject)
    return sent_count


def _send_loan_stage_notification(loan_id, stage_status, actor_name, base_url):
    from .models import Loan

    loan = Loan.objects.select_related("borrower").get(id=loan_id)
    payload = _loan_stage_payload(loan, stage_status, actor_name, base_url)
    if not payload:
        logger.info(
            "No stage notification configured for loan %s status %s.",
            loan_id,
            stage_status,
        )
        return False

    recipients = payload["recipients"]
    if not recipients:
        logger.warning(
            "Loan %s stage notification skipped for status %s because no recipients are configured.",
            loan_id,
            stage_status,
        )
        return False

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or getattr(settings, "EMAIL_HOST_USER", "")
    if not from_email:
        logger.warning(
            "Loan %s stage notification skipped because DEFAULT_FROM_EMAIL is not configured.",
            loan_id,
        )
        return False

    html_body = _approval_email_html(
        payload["heading"],
        payload["message"],
        payload["action_label"],
        payload["action_url"],
    )
    email = EmailMultiAlternatives(
        subject=payload["subject"],
        body=strip_tags(html_body),
        from_email=from_email,
        to=recipients,
    )
    email.attach_alternative(html_body, "text/html")
    sent_count = email.send(fail_silently=False)
    logger.info(
        "Loan %s stage notification sent to %s for status %s.",
        loan_id,
        ", ".join(recipients),
        stage_status,
    )
    return sent_count


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_loan_stage_notification_task(self, loan_id, stage_status, actor_name, base_url):
    return _send_loan_stage_notification(loan_id, stage_status, actor_name, base_url)


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_loan_approval_notification_task(self, loan_id, new_status, approver_name, base_url):
    return _send_loan_stage_notification(
        loan_id,
        new_status,
        approver_name,
        base_url,
    )


# Task to send loan application email
@shared_task(ignore_result=True)
def send_loan_application_email_task(recipient_name, client_name, recipient_email, application_id, is_applicant=True):
    applicant_dashboard_url = "https://sponsorwithpendeza.org/loans/applications/"
    officer_review_url = "https://sponsorwithpendeza.org/loans/applications/"
    subject = "Your Loan Application Submitted" if is_applicant else "New Loan Application for Review"

    if is_applicant:
        email_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                <h2 style="color: #2E86C1; text-align: center;">Loan Application Submitted on Behalf of Client</h2>
                <p>Hello <strong>{recipient_name}</strong>,</p>
                <p>A loan application has been successfully submitted on behalf of <strong>{client_name}</strong>. The application ID is <strong>{application_id}</strong>. You can track the status of this application by clicking the button below:</p>
                <div style="text-align: center; margin: 20px 0;">
                    <a href="{applicant_dashboard_url}" style="background-color: #2E86C1; color: #fff; text-decoration: none; padding: 10px 20px; border-radius: 5px;">View Application Status</a>
                </div>
                <p>Thank you for assisting clients with their financial needs through Pendeza Uganda.</p>
                <p style="color: #888;">- Pendeza Uganda - Finance Department</p>
            </div>
        </body>
        </html>
        """
    else:
        email_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                <h2 style="color: #C0392B; text-align: center;">Loan Application Approval Needed</h2>
                <p>Hello <strong>{recipient_name}</strong>,</p>
                <p>A new loan application with ID <strong>{application_id}</strong> is awaiting your review. Please review and process the application by clicking the button below:</p>
                <div style="text-align: center; margin: 20px 0;">
                    <a href="{officer_review_url}" style="background-color: #C0392B; color: #fff; text-decoration: none; padding: 10px 20px; border-radius: 5px;">Review Application</a>
                </div>
                <p>Thank you for your prompt attention to this matter.</p>
                <p style="color: #888;">- Pendeza Uganda - Finance Department</p>
            </div>
        </body>
        </html>
        """

    if is_blocked_borrower_email(recipient_email):
        logger.info(
            "Loan application email skipped for blocked borrower email: %s",
            recipient_email,
        )
        return False

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or getattr(settings, "EMAIL_HOST_USER", None)
    to = [recipient_email]

    try:
        email = EmailMultiAlternatives(subject, strip_tags(email_body), from_email, to)
        email.attach_alternative(email_body, "text/html")
        email.send()
        return True
    except Exception as e:
        logger.error(f"Error sending email to {recipient_email}: {str(e)}")
        return False
