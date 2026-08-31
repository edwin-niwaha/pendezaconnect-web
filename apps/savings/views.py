import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode

from apps.client.models import Client
from apps.loans.models import Loan
from apps.sponsorship.momo_prod import (
    create_access_token,
    generate_uuid,
    request_to_pay,
)
from apps.users.decorators import admin_or_manager_or_staff_required

from .forms import (
    ClientMobileMoneyDepositForm,
    ClientSavingsRequestForm,
    SavingsAccountForm,
    SavingsTransactionForm,
)
from .models import SavingsAccount, SavingsTransaction

logger = logging.getLogger(__name__)
MTN_DEPOSIT_FEE_RATE = Decimal("0.02")
MOBILE_MONEY_DEPOSIT_SESSION_KEY = "pending_mobile_money_savings_deposits"


def _client_for_user(user):
    profile = getattr(user, "profile", None)
    if profile and profile.client_id:
        return profile.client
    email = (getattr(user, "email", "") or "").strip()
    if not email:
        return None
    return Client.objects.filter(email__iexact=email).exclude(email="no-email@example.com").first()


def _pending_withdrawal_total(account):
    return account.transactions.filter(status="pending", transaction_type="withdrawal").aggregate(total=Sum("amount"))[
        "total"
    ] or Decimal("0.00")


def _savings_totals(queryset):
    return queryset.filter(status="approved").aggregate(
        credits=Sum("amount", filter=Q(transaction_type__in=SavingsTransaction.CREDIT_TYPES)),
        debits=Sum("amount", filter=Q(transaction_type__in=SavingsTransaction.DEBIT_TYPES)),
    )


def _mtn_deposit_fee(amount):
    return (Decimal(amount) * MTN_DEPOSIT_FEE_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _mtn_deposit_net_amount(amount):
    return Decimal(amount) - _mtn_deposit_fee(amount)


def _mtn_fee_reference(reference):
    return f"{reference}-FEE"


def _pending_deposit_session(request):
    return request.session.setdefault(MOBILE_MONEY_DEPOSIT_SESSION_KEY, {})


def _store_pending_deposit(request, reference, *, account, amount, fee_amount, phone, notes):
    pending_deposits = _pending_deposit_session(request)
    pending_deposits[reference] = {
        "account_id": account.pk,
        "amount": str(amount),
        "fee_amount": str(fee_amount),
        "phone": phone,
        "notes": notes,
    }
    request.session[MOBILE_MONEY_DEPOSIT_SESSION_KEY] = pending_deposits
    request.session.modified = True


def _get_pending_deposit(request, reference):
    return request.session.get(MOBILE_MONEY_DEPOSIT_SESSION_KEY, {}).get(reference)


def _clear_pending_deposit(request, reference):
    pending_deposits = request.session.get(MOBILE_MONEY_DEPOSIT_SESSION_KEY, {})
    if reference in pending_deposits:
        pending_deposits.pop(reference, None)
        request.session[MOBILE_MONEY_DEPOSIT_SESSION_KEY] = pending_deposits
        request.session.modified = True


def _create_successful_mobile_money_deposit(request, reference, pending_deposit):
    account = get_object_or_404(
        SavingsAccount.objects.select_related("client"),
        pk=pending_deposit["account_id"],
        client=_client_for_user(request.user),
    )
    existing_deposit = SavingsTransaction.objects.filter(
        account=account,
        transaction_type="deposit",
        payment_method="mobile_money",
        reference=reference,
    ).first()
    if existing_deposit:
        return existing_deposit

    amount = Decimal(pending_deposit["amount"])
    fee_amount = Decimal(pending_deposit["fee_amount"])
    phone = pending_deposit.get("phone", "")
    notes = pending_deposit.get("notes", "")
    approved_at = timezone.now()

    deposit = SavingsTransaction.objects.create(
        account=account,
        transaction_type="deposit",
        amount=amount,
        transaction_date=date.today(),
        payment_method="mobile_money",
        reference=reference,
        notes=(
            f"Client mobile money deposit from {phone}. "
            f"MTN fee: {fee_amount}. Net savings credit: {amount - fee_amount}. {notes}"
        ).strip(),
        status="approved",
        requested_by=request.user,
        approved_at=approved_at,
    )
    SavingsTransaction.objects.create(
        account=account,
        transaction_type="charge",
        amount=fee_amount,
        transaction_date=date.today(),
        payment_method="mobile_money",
        reference=_mtn_fee_reference(reference),
        notes=f"MTN mobile money collection fee for deposit {reference}.",
        status="approved",
        requested_by=request.user,
        approved_at=approved_at,
    )
    return deposit


def _format_client_phone(phone):
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if digits.startswith("256") and len(digits) == 12:
        return "0" + digits[3:]
    if digits.startswith("0") and len(digits) == 10:
        return digits
    return ""


def _client_statement_context(account, request):
    transactions = account.transactions.select_related("recorded_by", "approved_by", "requested_by")
    totals = _savings_totals(transactions)
    running_balance = Decimal("0.00")
    statement_rows = []
    chronological_transactions = transactions.order_by("transaction_date", "created_at", "id")
    for savings_transaction in chronological_transactions:
        if savings_transaction.status == "approved":
            if savings_transaction.is_credit:
                running_balance += savings_transaction.amount
            elif savings_transaction.is_debit:
                running_balance -= savings_transaction.amount
            savings_transaction.running_balance = running_balance
        else:
            savings_transaction.running_balance = None
        statement_rows.append(savings_transaction)

    statement_rows.reverse()
    paginator = Paginator(statement_rows, 25)
    return {
        "account": account,
        "transactions": paginator.get_page(request.GET.get("page")),
        "credits": totals["credits"] or Decimal("0.00"),
        "debits": totals["debits"] or Decimal("0.00"),
        "balance": account.balance,
    }


def _finance_notification_recipients():
    profiles = Q(profile__staff_role__in=["hof", "accountant"]) | Q(profile__role__in=["hof", "accountant"])
    return list(User.objects.filter(profiles).exclude(email="").values_list("email", flat=True).distinct())


def _notify_withdrawal_request(savings_transaction):
    recipients = _finance_notification_recipients()
    if not recipients:
        return
    client = savings_transaction.account.client
    subject = f"Withdrawal request pending approval - {client.full_name}"
    message = (
        f"{client.full_name} has submitted a savings withdrawal request.\n\n"
        f"Account: {savings_transaction.account.account_number}\n"
        f"Amount: {savings_transaction.amount}\n"
        f"Reference: {savings_transaction.reference or '-'}\n"
        "Please review it in Manage Savings."
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "EMAIL_HOST_USER", None)
    try:
        send_mail(
            subject,
            message,
            from_email,
            recipients,
            fail_silently=False,
        )
        logger.info("Withdrawal request email sent to %s", ", ".join(recipients))
    except Exception:
        logger.exception(
            "Withdrawal request email failed for transaction #%s",
            savings_transaction.pk,
        )


@login_required
@admin_or_manager_or_staff_required
def financial_services_dashboard(request):
    return savings_account_list(request)


@login_required
@admin_or_manager_or_staff_required
def savings_account_list(request):
    search_query = request.GET.get("search", "").strip()
    base_accounts = SavingsAccount.objects.select_related("client").order_by("client__full_name")
    transactions = SavingsTransaction.objects.select_related("account", "account__client")
    pending_withdrawals = transactions.filter(status="pending", transaction_type="withdrawal")
    pending_deposits = transactions.filter(status="pending", transaction_type="deposit")
    approved_transactions = transactions.filter(status="approved")
    totals = _savings_totals(transactions)
    deposits_total = approved_transactions.filter(transaction_type__in=SavingsTransaction.CREDIT_TYPES).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")
    withdrawals_total = approved_transactions.filter(transaction_type__in=SavingsTransaction.DEBIT_TYPES).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")
    accounts = base_accounts
    if search_query:
        accounts = accounts.filter(
            Q(account_number__icontains=search_query)
            | Q(client__full_name__icontains=search_query)
            | Q(client__reg_number__icontains=search_query)
            | Q(client__mobile_telephone__icontains=search_query)
        )

    paginator = Paginator(accounts, 50)
    page_number = request.GET.get("page")
    accounts = paginator.get_page(page_number)
    return render(
        request,
        "savings/savings_account_list.html",
        {
            "accounts": accounts,
            "search_query": search_query,
            "table_title": "Savings Accounts",
            "total_accounts": base_accounts.count(),
            "active_accounts": base_accounts.filter(status="active").count(),
            "dormant_accounts": base_accounts.filter(status="dormant").count(),
            "closed_accounts": base_accounts.filter(status="closed").count(),
            "linked_clients": base_accounts.values("client_id").distinct().count(),
            "pending_withdrawals_count": pending_withdrawals.count(),
            "pending_deposits_count": pending_deposits.count(),
            "pending_requests_count": pending_withdrawals.count() + pending_deposits.count(),
            "credits": totals["credits"] or Decimal("0.00"),
            "debits": totals["debits"] or Decimal("0.00"),
            "net_savings": deposits_total - withdrawals_total,
            "deposits_total": deposits_total,
            "withdrawals_total": withdrawals_total,
            "recent_transactions": transactions.order_by("-transaction_date", "-created_at")[:8],
            "pending_withdrawals": pending_withdrawals[:5],
        },
    )


@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
def savings_account_create(request):
    if request.method == "POST":
        form = SavingsAccountForm(request.POST)
        if form.is_valid():
            account = form.save(commit=False)
            account.created_by = request.user
            account.save()
            messages.success(request, "Savings account saved successfully.", extra_tags="bg-success")
            return redirect("savings_account_detail", account_id=account.id)
        messages.error(request, "Please correct the errors below.", extra_tags="bg-danger")
    else:
        form = SavingsAccountForm()

    return render(
        request,
        "savings/savings_account_form.html",
        {"form": form, "form_name": "Create Savings Account"},
    )


@login_required
@admin_or_manager_or_staff_required
def savings_account_detail(request, account_id):
    account = get_object_or_404(SavingsAccount.objects.select_related("client"), id=account_id)
    transactions = account.transactions.select_related("recorded_by", "approved_by", "requested_by")
    paginator = Paginator(transactions, 50)
    transactions_page = paginator.get_page(request.GET.get("page"))
    totals = _savings_totals(account.transactions.all())

    return render(
        request,
        "savings/savings_account_detail.html",
        {
            "account": account,
            "transactions": transactions_page,
            "credits": totals["credits"] or Decimal("0.00"),
            "debits": totals["debits"] or Decimal("0.00"),
            "balance": account.balance,
            "table_title": "Savings Account Statement",
        },
    )


@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
def savings_transaction_create(request, account_id=None):
    account = None
    if account_id is not None:
        account = get_object_or_404(SavingsAccount, id=account_id)

    if request.method == "POST":
        form = SavingsTransactionForm(request.POST, account=account)
        if form.is_valid():
            savings_transaction = form.save(commit=False)
            if account is not None:
                savings_transaction.account = account
            savings_transaction.recorded_by = request.user
            if savings_transaction.status == "approved":
                savings_transaction.approved_by = request.user
                from django.utils import timezone

                savings_transaction.approved_at = timezone.now()
            savings_transaction.save()
            messages.success(
                request,
                "Savings transaction saved successfully.",
                extra_tags="bg-success",
            )
            return redirect("savings_account_detail", account_id=savings_transaction.account_id)
        messages.error(request, "Please correct the errors below.", extra_tags="bg-danger")
    else:
        form = SavingsTransactionForm(account=account)

    return render(
        request,
        "savings/savings_transaction_form.html",
        {
            "form": form,
            "account": account,
            "form_name": "Record Savings Transaction",
        },
    )


@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
def savings_transaction_approve(request, transaction_id):
    savings_transaction = get_object_or_404(SavingsTransaction, id=transaction_id, status="pending")
    if request.method == "POST":
        try:
            savings_transaction.approve(request.user)
            messages.success(request, "Savings request approved.", extra_tags="bg-success")
        except Exception as exc:
            messages.error(request, str(exc), extra_tags="bg-danger")
    return redirect("savings_account_detail", account_id=savings_transaction.account_id)


@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
def savings_transaction_reject(request, transaction_id):
    savings_transaction = get_object_or_404(SavingsTransaction, id=transaction_id, status="pending")
    if request.method == "POST":
        savings_transaction.reject(request.user)
        messages.info(request, "Savings request rejected.", extra_tags="bg-warning")
    return redirect("savings_account_detail", account_id=savings_transaction.account_id)


@login_required
def client_savings_dashboard(request):
    client = _client_for_user(request.user)
    account = None
    transactions = []
    pending_requests = []
    loans = []
    deposit_form = None
    statement_summary = {}
    if client is not None:
        account = SavingsAccount.objects.filter(client=client).first()
        if account is not None:
            transactions = account.transactions.all()[:25]
            pending_requests = account.transactions.filter(status="pending")
            totals = _savings_totals(account.transactions.all())
            statement_summary = {
                "credits": totals["credits"] or Decimal("0.00"),
                "debits": totals["debits"] or Decimal("0.00"),
                "balance": account.balance,
            }
            deposit_form = ClientMobileMoneyDepositForm(
                initial={"phone": _format_client_phone(client.mobile_telephone)}
            )
        loans = Loan.objects.filter(borrower=client).order_by("-start_date", "-created_at")[:10]

    return render(
        request,
        "savings/client_savings_dashboard.html",
        {
            "client": client,
            "account": account,
            "transactions": transactions,
            "pending_requests": pending_requests,
            "loans": loans,
            "deposit_form": deposit_form,
            "mtn_deposit_fee_rate": MTN_DEPOSIT_FEE_RATE,
            "statement_summary": statement_summary,
            "form_name": "My Savings",
        },
    )


@login_required
def client_savings_statement(request):
    client = _client_for_user(request.user)
    account = SavingsAccount.objects.filter(client=client).first() if client else None
    if account is None:
        messages.error(
            request,
            "No savings account is linked to your login. Please contact staff.",
            extra_tags="bg-danger",
        )
        return redirect("client_savings_dashboard")

    context = _client_statement_context(account, request)
    context.update({"client": client, "form_name": "Savings Statement"})
    return render(request, "savings/client_savings_statement.html", context)


@login_required
@transaction.atomic
def client_savings_deposit_payment(request):
    client = _client_for_user(request.user)
    account = SavingsAccount.objects.filter(client=client, status="active").first() if client else None
    if account is None:
        messages.error(
            request,
            "No active savings account is linked to your login. Please contact staff.",
            extra_tags="bg-danger",
        )
        return redirect("client_savings_dashboard")

    if request.method != "POST":
        return redirect("client_savings_dashboard")

    form = ClientMobileMoneyDepositForm(request.POST)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error, extra_tags="bg-danger")
        return redirect("client_savings_dashboard")

    phone = form.cleaned_data["phone"]
    amount = form.cleaned_data["amount"]
    fee_amount = _mtn_deposit_fee(amount)
    amount_for_api = int(amount)
    api_phone = "256" + phone[1:]

    token = create_access_token(
        settings.MOMO_API_USER,
        settings.MOMO_API_KEY,
        settings.SUBSCRIPTION_KEY,
    )
    if not token:
        messages.error(
            request,
            "Mobile money service is temporarily unavailable.",
            extra_tags="bg-danger",
        )
        return redirect("client_savings_dashboard")

    ref = generate_uuid()
    status_code, response_text = request_to_pay(token, settings.SUBSCRIPTION_KEY, api_phone, amount_for_api, ref)
    logger.info("Savings deposit request-to-pay %s: %s", status_code, response_text)

    if status_code != 202:
        messages.error(
            request,
            "Mobile money deposit could not be initiated. Please try again.",
            extra_tags="bg-danger",
        )
        return redirect("client_savings_dashboard")

    notes = form.cleaned_data.get("notes") or ""
    _store_pending_deposit(
        request,
        ref,
        account=account,
        amount=amount,
        fee_amount=fee_amount,
        phone=phone,
        notes=notes,
    )

    query = urlencode({"ref": ref})
    return redirect(reverse("client_savings_deposit_waiting") + f"?{query}")


@login_required
def client_savings_deposit_waiting(request):
    client = _client_for_user(request.user)
    ref = request.GET.get("ref", "").strip()
    pending_deposit = _get_pending_deposit(request, ref)
    savings_transaction = (
        SavingsTransaction.objects.select_related("account", "account__client")
        .filter(
            reference=ref,
            account__client=client,
            transaction_type="deposit",
            payment_method="mobile_money",
        )
        .first()
    )
    if pending_deposit:
        account = get_object_or_404(SavingsAccount, pk=pending_deposit["account_id"], client=client)
        amount = Decimal(pending_deposit["amount"])
        fee_amount = Decimal(pending_deposit["fee_amount"])
        status_display = "Awaiting MTN approval"
    elif savings_transaction:
        account = savings_transaction.account
        amount = savings_transaction.amount
        fee_amount = _mtn_deposit_fee(amount)
        status_display = savings_transaction.get_status_display()
    else:
        messages.error(
            request,
            "Deposit request was not found. Please start again.",
            extra_tags="bg-danger",
        )
        return redirect("client_savings_dashboard")

    return render(
        request,
        "savings/client_deposit_waiting.html",
        {
            "client": client,
            "reference": ref,
            "amount": amount,
            "fee_amount": fee_amount,
            "net_amount": amount - fee_amount,
            "status_display": status_display,
            "account": account,
            "form_name": "Confirm Mobile Money Deposit",
        },
    )


@login_required
@transaction.atomic
def client_savings_deposit_status(request, reference):
    client = _client_for_user(request.user)
    savings_transaction = (
        SavingsTransaction.objects.select_for_update()
        .select_related("account", "account__client")
        .filter(
            reference=reference,
            account__client=client,
            transaction_type="deposit",
            payment_method="mobile_money",
        )
        .first()
    )
    pending_deposit = _get_pending_deposit(request, reference)

    if savings_transaction is None and pending_deposit is None:
        return JsonResponse({"status": "FAILED", "reason": "Deposit request was not found."}, status=404)

    fee_transaction = (
        SavingsTransaction.objects.select_for_update()
        .filter(
            account=(savings_transaction.account if savings_transaction else pending_deposit["account_id"]),
            transaction_type="charge",
            payment_method="mobile_money",
            reference=_mtn_fee_reference(reference),
        )
        .first()
    )

    if savings_transaction and savings_transaction.status == "approved":
        if fee_transaction and fee_transaction.status == "pending":
            fee_transaction.status = "approved"
            fee_transaction.approved_at = timezone.now()
            fee_transaction.save(update_fields=["status", "approved_at", "updated_at"])
        return JsonResponse(
            {
                "status": "SUCCESSFUL",
                "redirect_url": reverse("client_savings_statement"),
            }
        )
    if savings_transaction and savings_transaction.status == "rejected":
        if fee_transaction and fee_transaction.status == "pending":
            fee_transaction.status = "rejected"
            fee_transaction.approved_at = timezone.now()
            fee_transaction.save(update_fields=["status", "approved_at", "updated_at"])
        return JsonResponse({"status": "FAILED", "reason": "The deposit was not completed."})

    token = create_access_token(
        settings.MOMO_API_USER,
        settings.MOMO_API_KEY,
        settings.SUBSCRIPTION_KEY,
    )
    if not token:
        return JsonResponse({"status": "PENDING"})

    url = f"https://proxy.momoapi.mtn.com/collection/v1_0/requesttopay/{reference}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Ocp-Apim-Subscription-Key": settings.SUBSCRIPTION_KEY,
        "X-Target-Environment": "mtnuganda",
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
    except requests.exceptions.RequestException:
        return JsonResponse({"status": "PENDING"})

    if response.status_code != 200:
        return JsonResponse({"status": "PENDING"})

    data = response.json()
    momo_status = data.get("status", "PENDING")
    if momo_status == "SUCCESSFUL":
        if pending_deposit:
            savings_transaction = _create_successful_mobile_money_deposit(request, reference, pending_deposit)
            _clear_pending_deposit(request, reference)
        elif savings_transaction and savings_transaction.status != "approved":
            savings_transaction.status = "approved"
            savings_transaction.approved_at = timezone.now()
            savings_transaction.save(update_fields=["status", "approved_at", "updated_at"])
            if fee_transaction and fee_transaction.status == "pending":
                fee_transaction.status = "approved"
                fee_transaction.approved_at = timezone.now()
                fee_transaction.save(update_fields=["status", "approved_at", "updated_at"])
        return JsonResponse(
            {
                "status": "SUCCESSFUL",
                "redirect_url": reverse("client_savings_statement"),
            }
        )
    if momo_status == "FAILED":
        if savings_transaction:
            savings_transaction.status = "rejected"
            savings_transaction.approved_at = timezone.now()
            savings_transaction.save(update_fields=["status", "approved_at", "updated_at"])
        if fee_transaction and fee_transaction.status == "pending":
            fee_transaction.status = "rejected"
            fee_transaction.approved_at = timezone.now()
            fee_transaction.save(update_fields=["status", "approved_at", "updated_at"])
        _clear_pending_deposit(request, reference)
        return JsonResponse({"status": "FAILED", "reason": data.get("reason", "")})

    return JsonResponse({"status": "PENDING"})


@login_required
@transaction.atomic
def client_savings_request(request):
    return _client_savings_request(request)


@login_required
@transaction.atomic
def client_savings_deposit_request(request):
    return _client_savings_request(request, transaction_type="deposit", form_name="Submit Deposit Request")


@login_required
@transaction.atomic
def client_savings_withdrawal_request(request):
    return _client_savings_request(request, transaction_type="withdrawal", form_name="Submit Withdrawal Request")


def _client_savings_request(request, transaction_type=None, form_name="Submit Savings Request"):
    client = _client_for_user(request.user)
    account = SavingsAccount.objects.filter(client=client, status="active").first() if client else None
    if account is None:
        messages.error(
            request,
            "No active savings account is linked to your login. Please contact staff.",
            extra_tags="bg-danger",
        )
        return redirect("client_savings_dashboard")

    if request.method == "POST":
        form = ClientSavingsRequestForm(request.POST, transaction_type=transaction_type)
        if form.is_valid():
            request_txn = form.save(commit=False)
            request_txn.account = account
            if transaction_type:
                request_txn.transaction_type = transaction_type
            if request_txn.transaction_type == "withdrawal":
                available_balance = account.balance - _pending_withdrawal_total(account)
                if request_txn.amount > available_balance:
                    messages.error(
                        request,
                        "Withdrawal request cannot exceed your available savings balance.",
                        extra_tags="bg-danger",
                    )
                    return redirect("client_savings_dashboard")
            request_txn.status = "pending"
            request_txn.requested_by = request.user
            request_txn.transaction_date = date.today()
            request_txn.save()
            if request_txn.transaction_type == "withdrawal":
                _notify_withdrawal_request(request_txn)
            messages.success(
                request,
                "Savings request submitted for review.",
                extra_tags="bg-success",
            )
            return redirect("client_savings_dashboard")
        messages.error(request, "Please correct the errors below.", extra_tags="bg-danger")
    else:
        form = ClientSavingsRequestForm(transaction_type=transaction_type)

    return render(
        request,
        "savings/client_savings_request.html",
        {"form": form, "account": account, "form_name": form_name},
    )
