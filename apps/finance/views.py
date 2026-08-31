from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.child.models import Child
from apps.finance.services import (
    apply_sponsor_flags_for_program,
    get_child_payment_sponsors,
    get_staff_payment_sponsors,
    sync_child_payment_to_unified,
    sync_donor_payment_to_unified,
    sync_staff_payment_to_unified,
)
from apps.sponsor.models import Donor, Sponsor
from apps.sponsorship.models import ChildSponsorship, StaffSponsorship
from apps.staff.models import Staff
from apps.users.decorators import (
    admin_or_manager_or_staff_required,
    admin_or_manager_required,
)

from .forms import (
    ChildPaymentEditForm,
    ChildPaymentForm,
    DonorPaymentForm,
    SponsorLevelPaymentForm,
    StaffPaymentEditForm,
    StaffPaymentForm,
)
from .models import (
    ChildPayments,
    DonorPayment,
    Payment,
    StaffPayments,
)


# =================================== Child Payment ===================================
@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
def child_sponsor_payment(request):
    if request.method == "POST":
        form = ChildPaymentForm(request.POST, request.FILES)
        if form.is_valid():
            sponsor_id = request.POST.get("sponsor_id")
            child_id = request.POST.get("child_id")
            if not sponsor_id or not child_id:
                messages.error(
                    request,
                    "Please select both a sponsor and a child.",
                    extra_tags="bg-danger",
                )
                return redirect("child_sponsor_payment")

            sponsor_instance = get_object_or_404(
                Sponsor.objects.active().child_sponsors(),
                pk=sponsor_id,
            )
            child_instance = get_object_or_404(
                Child.objects.filter(is_departed=False),
                pk=child_id,
            )

            active_child_ids = ChildSponsorship.objects.filter(
                sponsor=sponsor_instance,
                is_active=True,
            ).values_list("child_id", flat=True)
            if active_child_ids.exists() and child_instance.id not in active_child_ids:
                messages.error(
                    request,
                    "The selected child is not actively linked to this sponsor.",
                    extra_tags="bg-danger",
                )
                return redirect("child_sponsor_payment")

            try:
                # Create the payment instance
                with transaction.atomic():
                    payment = form.save(commit=False)
                    payment.sponsor = sponsor_instance
                    payment.child = child_instance
                    payment.save()
                    sponsor_instance.is_child_sponsor = True
                    sponsor_instance.save(update_fields=["is_child_sponsor", "updated_at"])

                messages.success(request, "Payment submitted successfully!", extra_tags="bg-success")
                return redirect("child_sponsor_payment")
            except IntegrityError:
                messages.error(request, "An error occurred while processing the request.")
        else:
            messages.error(request, "Form is invalid.", extra_tags="bg-danger")
    else:
        form = ChildPaymentForm()

    children = Child.objects.filter(is_departed=False).order_by("id")
    sponsors = get_child_payment_sponsors()
    sponsorships = (
        ChildSponsorship.objects.select_related("sponsor", "child")
        .filter(is_active=True, sponsor__is_departed=False, child__is_departed=False)
        .order_by("sponsor__first_name", "sponsor__last_name", "child__full_name")
    )
    return render(
        request,
        "finance/child_sponsor_payments.html",
        {
            "form": form,
            "form_name": "Child-Sponsor Payments",
            "sponsors": sponsors,
            "children": children,
            "sponsorships": sponsorships,
        },
    )


# =================================== sponsor_payment_without_child Payment ===================================
@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
def sponsor_payment_without_child(request):
    if request.method == "POST":
        form = SponsorLevelPaymentForm(request.POST, request.FILES)
        if form.is_valid():
            sponsor_id = request.POST.get("sponsor_id")

            sponsor_instance = get_object_or_404(Sponsor, pk=sponsor_id)

            try:
                with transaction.atomic():
                    payment = form.save(commit=False)
                    payment.sponsor = sponsor_instance
                    payment.child = None
                    payment.staff = None
                    payment.save()
                    apply_sponsor_flags_for_program(sponsor_instance, payment.program)

                messages.success(request, "Payment submitted successfully!", extra_tags="bg-success")
                return redirect("sponsor_payment_without_child")
            except IntegrityError:
                messages.error(request, "An error occurred while processing the request.")
        else:
            messages.error(request, "Form is invalid.", extra_tags="bg-danger")
    else:
        form = SponsorLevelPaymentForm()

    sponsors = Sponsor.objects.active().order_by("id")
    return render(
        request,
        "finance/sponsor_payment_without_child.html",
        {
            "form": form,
            "form_name": "Other Sponsor Payments",
            "sponsors": sponsors,
        },
    )


# =================================== donor_payment_view Payment ===================================
@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
def donor_payment_view(request):
    if request.method == "POST":
        form = DonorPaymentForm(request.POST, request.FILES)
        if form.is_valid():
            donor_id = request.POST.get("donor_id")
            donor_instance = get_object_or_404(Donor, pk=donor_id)

            try:
                # Create the payment instance, link to donor and save
                donor_payment = form.save(commit=False)
                donor_payment.donor = donor_instance
                donor_payment.save()
                sponsor_instance = None
                if donor_instance.email:
                    sponsor_instance = Sponsor.objects.filter(email__iexact=donor_instance.email).first()
                if sponsor_instance is None:
                    full_name = donor_instance.full_name or "Unknown"
                    first_name, _, last_name = full_name.partition(" ")
                    sponsor_instance = Sponsor.objects.create(
                        first_name=first_name,
                        last_name=last_name,
                        email=donor_instance.email or "",
                        gender="Male",
                        expected_amt=0,
                        is_one_time_donor=True,
                    )
                sync_donor_payment_to_unified(donor_payment, sponsor_instance)

                messages.success(request, "Payment submitted successfully!", extra_tags="bg-success")
                return redirect("donor_payment")

            except IntegrityError:
                # Handle database integrity errors
                messages.error(
                    request,
                    "An error occurred while processing the payment.",
                    extra_tags="bg-danger",
                )

        else:
            messages.error(request, "Form is invalid.", extra_tags="bg-danger")

    else:
        form = DonorPaymentForm()

    donors = Donor.objects.all().order_by("id")

    return render(
        request,
        "finance/donor_payments.html",
        {
            "form": form,
            "form_name": " One time contributions",
            "donors": donors,
        },
    )


# =================================== donor_payment_list_view Payment ===================================
@login_required
@admin_or_manager_or_staff_required
def donor_payment_list_view(request):
    search_query = request.GET.get("search", "").strip()
    donor_payments = DonorPayment.objects.all().order_by("-payment_date")

    # Filter by donor name if search query is provided
    if search_query:
        donor_payments = donor_payments.filter(donor__full_name__icontains=search_query)

    # Pagination
    paginator = Paginator(donor_payments, 50)
    page_number = request.GET.get("page")
    donor_payments = paginator.get_page(page_number)

    return render(
        request,
        "finance/donor_payments_list.html",
        {"donor_payments": donor_payments, "search_query": search_query},
    )


# =================================== delete_donor_payment Transaction ===================================
@login_required
@admin_or_manager_required
@transaction.atomic
def delete_donor_payment_view(request, pk):
    records = DonorPayment.objects.get(id=pk)
    records.delete()
    messages.info(request, "Record deleted successfully!", extra_tags="bg-danger")
    return HttpResponseRedirect(reverse("donor_payment_list"))


# =================================== Saff Payment ===================================
@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
def staff_sponsor_payment(request):
    if request.method == "POST":
        form = StaffPaymentForm(request.POST, request.FILES)
        if form.is_valid():
            sponsor_id = request.POST.get("sponsor_id")
            staff_id = request.POST.get("staff_id")
            if not sponsor_id or not staff_id:
                messages.error(
                    request,
                    "Please select both a sponsor and a staff member.",
                    extra_tags="bg-danger",
                )
                return redirect("staff_sponsor_payment")

            sponsor_instance = get_object_or_404(
                Sponsor.objects.active().staff_sponsors(),
                pk=sponsor_id,
            )
            staff_instance = get_object_or_404(
                Staff.objects.filter(is_departed=False),
                pk=staff_id,
            )

            active_staff_ids = StaffSponsorship.objects.filter(
                sponsor=sponsor_instance,
                is_active=True,
            ).values_list("staff_id", flat=True)
            if active_staff_ids.exists() and staff_instance.id not in active_staff_ids:
                messages.error(
                    request,
                    "The selected staff member is not actively linked to this sponsor.",
                    extra_tags="bg-danger",
                )
                return redirect("staff_sponsor_payment")

            try:
                # Create the payment instance
                with transaction.atomic():
                    payment = form.save(commit=False)
                    payment.sponsor = sponsor_instance
                    payment.staff = staff_instance
                    payment.save()
                    sponsor_instance.is_staff_sponsor = True
                    sponsor_instance.save(update_fields=["is_staff_sponsor", "updated_at"])

                messages.success(request, "Payment submitted successfully!", extra_tags="bg-success")
                return redirect("staff_sponsor_payment")
            except IntegrityError:
                messages.error(request, "An error occurred while processing the request.")
        else:
            messages.error(request, "Form is invalid.", extra_tags="bg-danger")
    else:
        form = StaffPaymentForm()

    active_staff = Staff.objects.filter(is_departed=False).order_by("id")
    sponsors = get_staff_payment_sponsors()
    sponsorships = (
        StaffSponsorship.objects.select_related("sponsor", "staff")
        .filter(is_active=True, sponsor__is_departed=False, staff__is_departed=False)
        .order_by("sponsor__first_name", "sponsor__last_name", "staff__first_name")
    )
    return render(
        request,
        "finance/staff_sponsor_payments.html",
        {
            "form": form,
            "form_name": "Staff-Sponsor Payments",
            "sponsors": sponsors,
            "active_staff": active_staff,
            "sponsorships": sponsorships,
        },
    )


# =================================== Validate Child payment  ===================================
@login_required
@admin_or_manager_required
@transaction.atomic
def validate_child_payment(request, payment_id):
    sponsor_payments = get_object_or_404(ChildPayments, id=payment_id)

    if request.method == "POST":
        if not sponsor_payments.is_valid:
            sponsor_payments.is_valid = True
            sponsor_payments.save()
            sync_child_payment_to_unified(sponsor_payments)

            messages.success(request, "Pyament validated successfully!", extra_tags="bg-success")
            return HttpResponseRedirect(reverse("child_sponsor_payments_report"))

    return HttpResponseBadRequest("Invalid request")


# =================================== Edit Child Payment  ===================================
@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
def edit_child_payment(request, payment_id):
    sponsor_payments = get_object_or_404(ChildPayments, id=payment_id)

    if request.method == "POST":
        form = ChildPaymentEditForm(request.POST, instance=sponsor_payments)
        if form.is_valid():
            payment = form.save()
            if payment.is_valid:
                sync_child_payment_to_unified(payment)
            messages.success(request, "Updated successfully!", extra_tags="bg-success")
            return redirect("child_sponsor_payments_report")
    else:
        form = ChildPaymentEditForm(instance=sponsor_payments)

    return render(
        request,
        "finance/child_payment_edit.html",
        {
            "form_name": "PAYEMENT UPDATE",
            "form": form,
            "sponsor_payments": sponsor_payments,
        },
    )


# =================================== Delete Child Payment Transaction ===================================
@login_required
@admin_or_manager_required
@transaction.atomic
def delete_child_payment(request, pk):
    records = ChildPayments.objects.get(id=pk)
    records.delete()
    messages.info(request, "Record deleted successfully!", extra_tags="bg-danger")
    return HttpResponseRedirect(reverse("child_sponsor_payments_report"))


# =================================== Validate Staff payment  ===================================
@login_required
@admin_or_manager_required
@transaction.atomic
def validate_staff_payment(request, payment_id):
    sponsor_payments = get_object_or_404(StaffPayments, id=payment_id)

    if request.method == "POST":
        if not sponsor_payments.is_valid:
            sponsor_payments.is_valid = True
            sponsor_payments.save()
            sync_staff_payment_to_unified(sponsor_payments)

            messages.success(request, "Pyament validated successfully!", extra_tags="bg-success")
            return HttpResponseRedirect(reverse("staff_sponsor_payments_report"))

    return HttpResponseBadRequest("Invalid request")


# =================================== Edit Staff Payment  ===================================
@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
def edit_staff_payment(request, payment_id):
    sponsor_payments = get_object_or_404(StaffPayments, id=payment_id)

    if request.method == "POST":
        form = StaffPaymentEditForm(request.POST, instance=sponsor_payments)
        if form.is_valid():
            payment = form.save()
            if payment.is_valid:
                sync_staff_payment_to_unified(payment)
            messages.success(request, "Updated successfully!", extra_tags="bg-success")
            return redirect("staff_sponsor_payments_report")
    else:
        form = StaffPaymentEditForm(instance=sponsor_payments)

    return render(
        request,
        "finance/staff_payment_edit.html",
        {
            "form_name": "PAYEMENT UPDATE",
            "form": form,
            "sponsor_payments": sponsor_payments,
        },
    )


# =================================== Delete Staff Payment Transaction ===================================
@login_required
@admin_or_manager_required
@transaction.atomic
def delete_staff_payment(request, pk):
    records = StaffPayments.objects.get(id=pk)
    records.delete()
    messages.info(request, "Record deleted successfully!", extra_tags="bg-danger")
    return HttpResponseRedirect(reverse("staff_sponsor_payments_report"))


# =================================== Child & Saff Payments Reports ===================================


def group_payments_by_year(payments):
    payments_by_year = defaultdict(list)
    for payment in payments:
        payments_by_year[payment.payment_year].append(payment)
    return payments_by_year


def calculate_subtotals(payments_by_year):
    return {year: sum(p.amount for p in payments) for year, payments in payments_by_year.items()}


def group_sponsor_level_payments_by_year(payments):
    payments_by_year = defaultdict(list)
    for payment in payments:
        payments_by_year[payment.payment_date.year].append(payment)
    return payments_by_year


def generate_payments_report(request, report_title, template_name, payment_model):
    sponsors = Sponsor.objects.real_sponsors_only().order_by("id")
    context = {
        "table_title": report_title,
        "sponsors": sponsors,
        "has_selected_sponsor": False,
    }

    if request.method == "POST":
        sponsor_id = request.POST.get("id")
        if sponsor_id:
            selected_sponsor = get_object_or_404(Sponsor, id=sponsor_id)
            sponsor_payments = payment_model.objects.select_related("sponsor").filter(sponsor_id=sponsor_id)
            related_fields = {
                field.name for field in payment_model._meta.get_fields() if getattr(field, "many_to_one", False)
            }
            if "child" in related_fields:
                sponsor_payments = sponsor_payments.select_related("child")
            if "staff" in related_fields:
                sponsor_payments = sponsor_payments.select_related("staff")
            sponsor_payments = sponsor_payments.order_by(
                "-payment_year",
                "-payment_date",
                "-id",
            )

            # Group payments by year and calculate subtotals
            payments_by_year = group_payments_by_year(sponsor_payments)
            subtotals = calculate_subtotals(payments_by_year)
            total_amount = sum(subtotals.values())
            validated_count = sponsor_payments.filter(is_valid=True).count()
            pending_count = sponsor_payments.filter(is_valid=False).count()

            context.update(
                {
                    "has_selected_sponsor": True,
                    "selected_sponsor": selected_sponsor,
                    "first_name": selected_sponsor.first_name,
                    "last_name": selected_sponsor.last_name,
                    "prefix_id": selected_sponsor.prefixed_id,
                    "sponsor_payments": sponsor_payments,
                    "total_amount": total_amount,
                    "payments_by_year": payments_by_year,
                    "subtotals": subtotals,
                    "payment_count": sponsor_payments.count(),
                    "validated_count": validated_count,
                    "pending_count": pending_count,
                }
            )

            return render(request, template_name, context)
        else:
            messages.error(request, "No Sponsor selected.", extra_tags="bg-danger")

    return render(request, template_name, context)


@login_required
@admin_or_manager_or_staff_required
def child_sponsor_payments_report(request):
    return generate_payments_report(
        request,
        "Child - Sponsor Payments Report",
        "finance/child_sponsor_payments_rpt.html",
        ChildPayments,
    )


@login_required
@admin_or_manager_or_staff_required
def staff_sponsor_payments_report(request):
    return generate_payments_report(
        request,
        "Staff - Sponsor Payments Report",
        "finance/staff_sponsor_payments_rpt.html",
        StaffPayments,
    )


@login_required
@admin_or_manager_or_staff_required
def sponsor_payment_without_child_report(request):
    sponsors = Sponsor.objects.active().order_by("id")
    context = {
        "table_title": "Other Sponsor Payments Report",
        "sponsors": sponsors,
        "has_selected_sponsor": False,
    }

    if request.method == "POST":
        sponsor_id = request.POST.get("id")
        if sponsor_id:
            selected_sponsor = get_object_or_404(Sponsor, id=sponsor_id)
            sponsor_payments = (
                Payment.objects.with_related()
                .filter(
                    sponsor_id=sponsor_id,
                    child__isnull=True,
                    staff__isnull=True,
                    program__code__in=SponsorLevelPaymentForm.ALLOWED_PROGRAMS,
                )
                .order_by("-payment_date", "-id")
            )
            payments_by_year = group_sponsor_level_payments_by_year(sponsor_payments)
            subtotals = calculate_subtotals(payments_by_year)

            context.update(
                {
                    "has_selected_sponsor": True,
                    "selected_sponsor": selected_sponsor,
                    "sponsor_payments": sponsor_payments,
                    "total_amount": sum(subtotals.values()),
                    "payments_by_year": payments_by_year,
                    "subtotals": subtotals,
                    "payment_count": sponsor_payments.count(),
                }
            )
        else:
            messages.error(request, "No Sponsor selected.", extra_tags="bg-danger")

    return render(
        request,
        "finance/sponsor_payment_without_child_rpt.html",
        context,
    )


@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
def edit_sponsor_payment_without_child(request, payment_id):
    sponsor_payment = get_object_or_404(
        Payment.objects.with_related(),
        id=payment_id,
        child__isnull=True,
        staff__isnull=True,
        program__code__in=SponsorLevelPaymentForm.ALLOWED_PROGRAMS,
    )

    if request.method == "POST":
        form = SponsorLevelPaymentForm(request.POST, instance=sponsor_payment)
        if form.is_valid():
            form.save()
            messages.success(request, "Updated successfully!", extra_tags="bg-success")
            return redirect("sponsor_payment_without_child_report")
    else:
        form = SponsorLevelPaymentForm(instance=sponsor_payment)

    return render(
        request,
        "finance/sponsor_payment_without_child_edit.html",
        {
            "form_name": "Sponsor Payment Update",
            "form": form,
            "sponsor_payment": sponsor_payment,
        },
    )


@login_required
@admin_or_manager_required
@transaction.atomic
def delete_sponsor_payment_without_child(request, pk):
    record = get_object_or_404(
        Payment,
        id=pk,
        child__isnull=True,
        staff__isnull=True,
        program__code__in=SponsorLevelPaymentForm.ALLOWED_PROGRAMS,
    )
    record.delete()
    messages.info(request, "Record deleted successfully!", extra_tags="bg-danger")
    return HttpResponseRedirect(reverse("sponsor_payment_without_child_report"))
