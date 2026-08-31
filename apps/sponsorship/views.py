import json
import logging
import re

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.csrf import csrf_exempt

from apps.child.models import Child
from apps.sponsor.models import Sponsor
from apps.staff.models import Staff
from apps.users.decorators import (
    admin_or_manager_or_staff_required,
    admin_or_manager_required,
)

from .forms import (
    ChildSponsorshipEditForm,
    ChildSponsorshipForm,
    StaffSponsorshipEditForm,
    StaffSponsorshipForm,
)
from .models import ChildSponsorship, MoMoTransaction, StaffSponsorship
from .momo_prod import create_access_token, generate_uuid, request_to_pay

# Set up logging
logger = logging.getLogger(__name__)


# =================================== Child Sponsorship ===================================
@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
def child_sponsorship(request):
    if request.method == "POST":
        form = ChildSponsorshipForm(request.POST, request.FILES)
        if form.is_valid():
            sponsor_id = request.POST.get("sponsor_id")
            child_id = request.POST.get("child_id")
            if not sponsor_id or not child_id:
                messages.error(
                    request,
                    "Please select both a sponsor and a child.",
                    extra_tags="bg-danger",
                )
                return redirect("child_sponsorship")

            sponsor_instance = get_object_or_404(
                Sponsor.objects.active_real_supporters(),
                pk=sponsor_id,
            )
            child_instance = get_object_or_404(
                Child.objects.filter(is_departed=False),
                pk=child_id,
            )

            # Check if sponsorship already exists
            existing_sponsorship = ChildSponsorship.objects.filter(
                sponsor=sponsor_instance, child=child_instance
            ).first()
            if existing_sponsorship and existing_sponsorship.is_active:
                messages.error(
                    request,
                    "Sponsorship already exists for this child and sponsor.",
                    extra_tags="bg-danger",
                )
            else:
                try:
                    # Create the sponsorship instance
                    with transaction.atomic():
                        sponsorship = existing_sponsorship or ChildSponsorship(
                            sponsor=sponsor_instance,
                            child=child_instance,
                        )
                        sponsorship.sponsorship_type = form.cleaned_data["sponsorship_type"]
                        sponsorship.start_date = form.cleaned_data["start_date"]
                        sponsorship.end_date = None
                        sponsorship.is_active = True
                        sponsorship.save()

                        # Update sponsor status to "departed"
                        child_instance.is_sponsored = True
                        child_instance.save(update_fields=["is_sponsored", "updated_at"])
                        sponsor_instance.is_child_sponsor = True
                        sponsor_instance.save(update_fields=["is_child_sponsor", "updated_at"])

                    messages.success(request, "Assigned successfully!", extra_tags="bg-success")
                    return redirect("child_sponsorship")
                except IntegrityError:
                    # Handle integrity error if any
                    messages.error(request, "An error occurred while processing the request.")
        else:
            messages.error(request, "Form is invalid.", extra_tags="bg-danger")
    else:
        form = ChildSponsorshipForm()

    children = Child.objects.filter(is_departed=False).order_by("id")
    sponsors = (
        Sponsor.objects.active()
        .filter(
            Q(is_child_sponsor=True)
            | Q(payments__program__code="child_support")
            | Q(payments__program__code="child_co_support")
        )
        .distinct()
        .order_by("id")
    )
    active_sponsorships = (
        ChildSponsorship.objects.select_related("sponsor", "child")
        .filter(is_active=True, sponsor__is_departed=False, child__is_departed=False)
        .order_by("child__full_name", "sponsor__first_name", "sponsor__last_name")
    )
    return render(
        request,
        "sponsorship/child_sponsorship.html",
        {
            "form": form,
            "form_name": "Child Sponsorship",
            "sponsors": sponsors,
            "children": children,
            "active_sponsorships": active_sponsorships,
        },
    )


# =================================== Child Sponsorship Report ===================================
@login_required
@admin_or_manager_or_staff_required
def child_sponsorship_report(request):
    children = Child.objects.filter(is_departed=False).order_by("id")
    context = {
        "table_title": "Sponsorship Report - Child",
        "children": children,
        "has_selected_child": False,
    }
    if request.method == "POST":
        child_id = request.POST.get("id")
        if child_id:
            selected_child = get_object_or_404(Child, id=child_id)
            child_sponsorship = (
                ChildSponsorship.objects.select_related("child", "sponsor")
                .filter(child_id=child_id)
                .order_by("-is_active", "-start_date", "sponsor__first_name")
            )
            active_count = child_sponsorship.filter(is_active=True).count()
            inactive_count = child_sponsorship.filter(is_active=False).count()
            context.update(
                {
                    "table_title": "Child-to-Sponsor Report",
                    "has_selected_child": True,
                    "selected_child": selected_child,
                    "child_name": selected_child.full_name,
                    "prefix_id": selected_child.prefixed_id,
                    "child_sponsorship": child_sponsorship,
                    "active_count": active_count,
                    "inactive_count": inactive_count,
                    "record_count": child_sponsorship.count(),
                }
            )
            return render(request, "sponsorship/child_sponsorship_rpt.html", context)
        else:
            messages.error(request, "No child selected.", extra_tags="bg-danger")

    return render(request, "sponsorship/child_sponsorship_rpt.html", context)


# =================================== sponsor_to_child_rpt ===================================
@login_required
@admin_or_manager_or_staff_required
def sponsor_to_child_rpt(request):
    sponsors = Sponsor.objects.all().filter(is_departed=False).order_by("id")
    if request.method == "POST":
        sponsor_id = request.POST.get("sponsor_id")
        if sponsor_id:
            selected_sponsor = get_object_or_404(Sponsor, id=sponsor_id)
            sponsor_to_child = ChildSponsorship.objects.filter(sponsor_id=sponsor_id)
            return render(
                request,
                "sponsorship/sponsor_to_child_rpt.html",
                {
                    "table_title": "sponsor-to-child report",
                    "sponsors": sponsors,
                    "first_name": selected_sponsor.first_name,
                    "last_name": selected_sponsor.last_name,
                    "prefix_id": selected_sponsor.prefixed_id,
                    "sponsor_to_child": sponsor_to_child,
                },
            )
        else:
            messages.error(request, "No sponsor selected.", extra_tags="bg-danger")
    return render(
        request,
        "sponsorship/sponsor_to_child_rpt.html",
        {"table_title": "sponsorship report - sponsor", "sponsors": sponsors},
    )


# =================================== Edit Staff Sponsorship Data ===================================
@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
def edit_child_sponsorship(request, sponsorship_id):
    sponsorship = get_object_or_404(ChildSponsorship, id=sponsorship_id)

    if request.method == "POST":
        form = ChildSponsorshipEditForm(request.POST, instance=sponsorship)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Child sponsorship updated successfully!",
                extra_tags="bg-success",
            )
            return redirect("child_sponsorship_report")  # Redirect to a report or list view
    else:
        form = ChildSponsorshipEditForm(instance=sponsorship)

    return render(
        request,
        "sponsorship/child_sponsorship_edit.html",
        {
            "form_name": "CHILD SPONSORSHIP UPDATE",
            "form": form,
            "sponsorship": sponsorship,
        },
    )


# =================================== Delete Sponsorship Data ===================================
@login_required
@admin_or_manager_required
@transaction.atomic
def delete_child_sponsorship(request, pk):
    records = ChildSponsorship.objects.get(id=pk)
    records.delete()
    messages.info(request, "Record deleted successfully!", extra_tags="bg-danger")
    return HttpResponseRedirect(reverse("child_sponsorship_report"))


# =================================== Terminate Child Sponsorship ===================================
@login_required
@admin_or_manager_required
@transaction.atomic
def terminate_child_sponsorship(request, sponsorship_id):
    sponsorship = get_object_or_404(ChildSponsorship, id=sponsorship_id)

    if request.method == "POST":
        if sponsorship.is_active:
            sponsorship.end_date = timezone.now().date()  # Set end_date to today
            sponsorship.is_active = False
            sponsorship.save()

            # Assuming a direct ForeignKey relationship to Child
            sponsored_child = sponsorship.child
            if sponsored_child:
                sponsored_child.is_sponsored = ChildSponsorship.objects.filter(
                    child=sponsored_child,
                    is_active=True,
                ).exists()
                sponsored_child.save(update_fields=["is_sponsored", "updated_at"])

            messages.success(request, "Sponsorship terminated successfully!", extra_tags="bg-success")
            return HttpResponseRedirect(reverse("child_sponsorship_report"))

    return HttpResponseBadRequest("Invalid request")


# =================================== Staff Sponsorship ===================================
@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
def staff_sponsorship_create(request):
    if request.method == "POST":
        form = StaffSponsorshipForm(request.POST, request.FILES)
        if form.is_valid():
            sponsor_id = request.POST.get("sponsor_id")
            staff_id = request.POST.get("id")
            if not sponsor_id or not staff_id:
                messages.error(
                    request,
                    "Please select both a sponsor and a staff member.",
                    extra_tags="bg-danger",
                )
                return redirect("staff_sponsorship_create")

            sponsor_instance = get_object_or_404(
                Sponsor.objects.active_real_supporters(),
                pk=sponsor_id,
            )
            staff_instance = get_object_or_404(
                Staff.objects.filter(is_departed=False),
                pk=staff_id,
            )

            # Check if sponsorship already exists
            existing_sponsorship = StaffSponsorship.objects.filter(
                sponsor=sponsor_instance, staff=staff_instance
            ).first()
            if existing_sponsorship and existing_sponsorship.is_active:
                messages.error(request, "Sponsorship already exists for this staff and sponsor.")
            else:
                try:
                    # Create the sponsorship instance
                    with transaction.atomic():
                        sponsorship = existing_sponsorship or StaffSponsorship(
                            sponsor=sponsor_instance,
                            staff=staff_instance,
                        )
                        sponsorship.sponsorship_type = form.cleaned_data["sponsorship_type"]
                        sponsorship.start_date = form.cleaned_data["start_date"]
                        sponsorship.end_date = None
                        sponsorship.is_active = True
                        sponsorship.save()

                        # Update sponsorship status
                        staff_instance.is_sponsored = True
                        staff_instance.save(update_fields=["is_sponsored", "updated_at"])
                        sponsor_instance.is_staff_sponsor = True
                        sponsor_instance.save(update_fields=["is_staff_sponsor", "updated_at"])

                    messages.success(request, "Assigned successfully!", extra_tags="bg-success")
                    return redirect("staff_sponsorship_create")
                except IntegrityError:
                    # Handle integrity error if any
                    messages.error(request, "An error occurred while processing the request.")
        else:
            messages.error(request, "Form is invalid.", extra_tags="bg-danger")
    else:
        form = StaffSponsorshipForm()

    active_staff = Staff.objects.filter(is_departed=False).order_by("id")
    sponsors = (
        Sponsor.objects.active()
        .filter(Q(is_staff_sponsor=True) | Q(payments__program__code="staff_support"))
        .distinct()
        .order_by("id")
    )
    active_sponsorships = (
        StaffSponsorship.objects.select_related("sponsor", "staff")
        .filter(is_active=True, sponsor__is_departed=False, staff__is_departed=False)
        .order_by("staff__first_name", "staff__last_name", "sponsor__first_name")
    )
    return render(
        request,
        "sponsorship/staff_sponsorship.html",
        {
            "form": form,
            "form_name": "Staff Sponsorship",
            "sponsors": sponsors,
            "active_staff": active_staff,
            "active_sponsorships": active_sponsorships,
        },
    )


# =================================== Staff Sponsorship Report ===================================
@login_required
@admin_or_manager_or_staff_required
def staff_sponsorship_report(request):
    active_staff = Staff.objects.filter(is_departed=False).order_by("id")
    context = {
        "table_title": "Sponsorship Report - Staff",
        "active_staff": active_staff,
        "has_selected_staff": False,
    }
    if request.method == "POST":
        staff_id = request.POST.get("id")
        if staff_id:
            selected_staff = get_object_or_404(Staff, id=staff_id)
            staff_sponsorship = (
                StaffSponsorship.objects.select_related("staff", "sponsor")
                .filter(staff_id=staff_id)
                .order_by("-is_active", "-start_date", "sponsor__first_name")
            )
            active_count = staff_sponsorship.filter(is_active=True).count()
            inactive_count = staff_sponsorship.filter(is_active=False).count()
            context.update(
                {
                    "table_title": "Staff Sponsorship Report",
                    "has_selected_staff": True,
                    "selected_staff": selected_staff,
                    "first_name": selected_staff.first_name,
                    "last_name": selected_staff.last_name,
                    "prefix_id": selected_staff.prefixed_id,
                    "staff_sponsorship": staff_sponsorship,
                    "active_count": active_count,
                    "inactive_count": inactive_count,
                    "record_count": staff_sponsorship.count(),
                }
            )
            return render(request, "sponsorship/staff_sponsorship_rpt.html", context)
        else:
            messages.error(request, "No Staff selected.", extra_tags="bg-danger")
    return render(request, "sponsorship/staff_sponsorship_rpt.html", context)


# =================================== sponsor_to_staff_rpt ===================================
@login_required
@admin_or_manager_or_staff_required
def sponsor_to_staff_rpt(request):
    sponsors = Sponsor.objects.all().filter(is_departed=False).order_by("id")
    if request.method == "POST":
        sponsor_id = request.POST.get("sponsor_id")
        if sponsor_id:
            selected_sponsor = get_object_or_404(Sponsor, id=sponsor_id)
            sponsor_to_staff = StaffSponsorship.objects.filter(sponsor_id=sponsor_id)
            return render(
                request,
                "sponsorship/sponsor_to_staff_rpt.html",
                {
                    "table_title": "sponsorship report - sponsor",
                    "sponsors": sponsors,
                    "first_name": selected_sponsor.first_name,
                    "last_name": selected_sponsor.last_name,
                    "prefix_id": selected_sponsor.prefixed_id,
                    "sponsor_to_staff": sponsor_to_staff,
                },
            )
        else:
            messages.error(request, "No sponsor selected.", extra_tags="bg-danger")
    return render(
        request,
        "sponsorship/sponsor_to_staff_rpt.html",
        {"table_title": "sponsorship report - sponsor", "sponsors": sponsors},
    )


# =================================== Edit Staff Sponsorship Data ===================================
@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
def edit_staff_sponsorship(request, sponsorship_id):
    sponsorship = get_object_or_404(StaffSponsorship, id=sponsorship_id)

    if request.method == "POST":
        form = StaffSponsorshipEditForm(request.POST, instance=sponsorship)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Staff sponsorship updated successfully!",
                extra_tags="bg-success",
            )
            return redirect("staff_sponsorship_report")  # Redirect to a report or list view
    else:
        form = StaffSponsorshipEditForm(instance=sponsorship)

    return render(
        request,
        "sponsorship/staff_sponsorship_edit.html",
        {
            "form_name": "STAFF SPONSORSHIP UPDATE",
            "form": form,
            "sponsorship": sponsorship,
        },
    )


# =================================== Delete Sponsorship Data ===================================
@login_required
@admin_or_manager_required
@transaction.atomic
def delete_staff_sponsorship(request, pk):
    records = StaffSponsorship.objects.get(id=pk)
    records.delete()

    messages.info(request, "Record deleted successfully!", extra_tags="bg-danger")
    return HttpResponseRedirect(reverse("staff_sponsorship_report"))


# =================================== End Staff Sponsorship Data ===================================
@login_required
@admin_or_manager_required
@transaction.atomic
def terminate_staff_sponsorship(request, sponsorship_id):
    sponsorship = get_object_or_404(StaffSponsorship, id=sponsorship_id)

    if request.method == "POST":
        if sponsorship.is_active:
            sponsorship.end_date = timezone.now().date()  # Set end_date to today
            sponsorship.is_active = False
            sponsorship.save()

            # Assuming a direct ForeignKey relationship to Staff
            staff_member = sponsorship.staff  # Replace 'staff' with actual related name if different
            if staff_member:
                staff_member.is_sponsored = False
                staff_member.save()

            messages.success(request, "Sponsorship terminated successfully!", extra_tags="bg-success")
            return HttpResponseRedirect(reverse("staff_sponsorship_report"))

    return HttpResponseBadRequest("Invalid request")


# ---------------- MoMo Payment Initiation View ---------------- #
def initiate_payment(request):
    if request.method == "POST":
        phone = re.sub(r"[^0-9]", "", request.POST.get("phone", ""))
        if phone.startswith("256") and len(phone) == 12:
            phone = "0" + phone[3:]
        amount = request.POST.get("amount", "").strip()
        name = request.POST.get("name", "").strip() or None
        email = request.POST.get("email", "").strip() or None

        if not re.match(r"^07\d{8}$", phone):
            messages.error(request, "Invalid phone number.", extra_tags="alert-danger")
            return render(request, "sponsorship/initiate_payment.html")

        # Convert phone to MTN API format 2567XXXXXXX
        api_phone = "256" + phone[1:]

        # Validate amount
        try:
            amount = int(float(amount))
            if amount < 5000:
                raise ValueError
        except ValueError:
            messages.error(request, "Amount must be 5,000 UGX or more.", extra_tags="alert-danger")
            return render(request, "sponsorship/initiate_payment.html")

        token = create_access_token(settings.MOMO_API_USER, settings.MOMO_API_KEY, settings.SUBSCRIPTION_KEY)
        if not token:
            messages.error(request, "Service temporarily unavailable.", extra_tags="alert-danger")
            return render(request, "sponsorship/initiate_payment.html")

        ref = generate_uuid()
        status, res_text = request_to_pay(token, settings.SUBSCRIPTION_KEY, api_phone, amount, ref)
        print("RequestToPay Status:", status)
        print("RequestToPay Response:", res_text)

        if status == 202:
            # redirect to waiting page with query parameters
            query = urlencode(
                {
                    "ref": ref,
                    "amount": amount,
                    "phone": phone,
                    "name": name or "",
                    "email": email or "",
                }
            )
            return HttpResponseRedirect(reverse("waiting") + f"?{query}")

        else:
            messages.error(request, "Payment failed. Try again.", extra_tags="alert-danger")

    return render(request, "sponsorship/initiate_payment.html")


# ---------------- Waiting Page ---------------- #
def waiting(request):
    """
    Display waiting page after initiating MoMo payment.
    Expects query params: ref, amount, phone, name, email
    """
    ref = request.GET.get("ref")
    amount = request.GET.get("amount")
    phone = request.GET.get("phone")
    donor_name = request.GET.get("name", "")
    donor_email = request.GET.get("email", "")

    if not ref or not amount or not phone:
        # fallback: redirect to form if missing data
        return redirect("initiate_payment")

    context = {
        "transaction_id": ref,
        "amount": amount,
        "phone": phone,
        "donor_name": donor_name,
        "donor_email": donor_email,
    }
    return render(request, "sponsorship/waiting.html", context)


# ---------------- Auto Status Check ---------------- #
def get_transaction_status(request, ref_id):
    """
    Securely checks MTN MoMo transaction status using server-side credentials only.
    No API keys exposed to the browser.
    """
    # 1. Generate token using YOUR secrets (never exposed)
    token = create_access_token(settings.MOMO_API_USER, settings.MOMO_API_KEY, settings.SUBSCRIPTION_KEY)
    if not token:
        return JsonResponse({"status": "PENDING"})  # Don't leak errors

    # 2. Query the transaction status
    url = f"https://proxy.momoapi.mtn.com/collection/v1_0/requesttopay/{ref_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Ocp-Apim-Subscription-Key": settings.SUBSCRIPTION_KEY,
        "X-Target-Environment": "mtnuganda",
    }

    try:
        res = requests.get(url, headers=headers, timeout=30)
        if res.status_code == 200:
            data = res.json()
            # MTN returns "status": "SUCCESSFUL" | "FAILED" | "PENDING"
            return JsonResponse(
                {
                    "status": data.get("status", "PENDING"),
                    "reason": data.get("reason", ""),
                }
            )
        else:
            return JsonResponse({"status": "PENDING"})
    except requests.exceptions.RequestException:
        return JsonResponse({"status": "PENDING"})


# ---------------- MoMo Callback Handler ---------------- #
@csrf_exempt
def momo_callback(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error("Invalid JSON received in MTN callback")
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    # Extract relevant fields from MTN callback
    external_id = payload.get("externalId")
    status = payload.get("status")
    amount = payload.get("amount")
    currency = payload.get("currency")
    payer_message = payload.get("payerMessage")
    payee_note = payload.get("payeeNote")
    phone_number = payload.get("payer", {}).get("partyId")

    if not external_id:
        logger.warning("MTN callback missing externalId")
        return JsonResponse({"error": "Missing externalId"}, status=400)

    # Attempt to find the transaction
    try:
        txn = MoMoTransaction.objects.get(external_id=external_id)
    except MoMoTransaction.DoesNotExist:
        logger.warning(f"MTN callback received for unknown transaction {external_id}")
        return JsonResponse({"error": "Transaction not found"}, status=404)

    # Idempotent update: only change status if it differs
    if txn.status != status:
        txn.status = status
        txn.amount = amount or txn.amount
        txn.currency = currency or txn.currency
        txn.payer_message = payer_message or txn.payer_message
        txn.payee_note = payee_note or txn.payee_note
        txn.phone_number = phone_number or txn.phone_number
        txn.updated_at = timezone.now()
        txn.save()
        logger.info(f"Transaction {external_id} updated to {status}")
    else:
        logger.info(f"Transaction {external_id} callback received but status already {status}")

    return JsonResponse({"status": "ok"})


# ---------------- Thank You Page ---------------- #
def thank_you(request):
    transaction_id = request.GET.get("ref", "N/A")
    amount = request.GET.get("amount", "N/A")
    phone = request.GET.get("phone", "N/A")
    donor_name = request.GET.get("name", None)
    donor_email = request.GET.get("email", None)

    # ✅ SAVE ONLY ONCE (no duplicates)
    if transaction_id != "N/A":
        MoMoTransaction.objects.get_or_create(
            reference_id=transaction_id,
            defaults={
                "phone_number": phone,
                "amount": int(amount) if amount != "N/A" else 0,
                "donor_name": donor_name,
                "donor_email": donor_email,
                "status": "SUCCESSFUL",
            },
        )

    context = {
        "transaction_id": transaction_id,
        "amount": amount,
        "phone": phone,  # ✅
        "donor_name": donor_name,
        "donor_email": donor_email,
    }
    return render(request, "sponsorship/thank_you.html", context)


# ---------------- MoMo Transaction List View ---------------- #
@login_required
@admin_or_manager_required
@transaction.atomic
def momo_transaction_list(request):
    search_query = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "").strip()
    transactions = MoMoTransaction.objects.all().order_by("-created_at")

    if search_query:
        transactions = transactions.filter(
            Q(donor_name__icontains=search_query)
            | Q(donor_email__icontains=search_query)
            | Q(phone_number__icontains=search_query)
            | Q(reference_id__icontains=search_query)
            | Q(external_id__icontains=search_query)
        )
    if status_filter:
        transactions = transactions.filter(status=status_filter)

    summary = transactions.aggregate(
        total_amount=Sum("amount"),
        total_count=Count("id"),
        successful_count=Count("id", filter=Q(status="SUCCESSFUL")),
        pending_count=Count("id", filter=Q(status="PENDING")),
        failed_count=Count("id", filter=Q(status="FAILED")),
    )
    query_params = request.GET.copy()
    query_params.pop("page", None)

    paginator = Paginator(transactions, 25)
    page_number = request.GET.get("page")
    records = paginator.get_page(page_number)

    context = {
        "records": records,
        "table_title": "MoMo Transactions",
        "search_query": search_query,
        "status_filter": status_filter,
        "status_choices": MoMoTransaction.STATUS_CHOICES,
        "total_amount": summary["total_amount"] or 0,
        "total_count": summary["total_count"],
        "successful_count": summary["successful_count"],
        "pending_count": summary["pending_count"],
        "failed_count": summary["failed_count"],
        "query_string": query_params.urlencode(),
    }
    return render(request, "sponsorship/momo_trans_list.html", context)


# ---------------- MoMo Transaction Delete View ---------------- #
@login_required
@admin_or_manager_required
@transaction.atomic
def delete_momo_transaction(request, pk):
    transaction = get_object_or_404(MoMoTransaction, pk=pk)
    transaction.delete()
    messages.success(request, "Transaction deleted successfully.")
    return redirect("momo_transaction_list")
