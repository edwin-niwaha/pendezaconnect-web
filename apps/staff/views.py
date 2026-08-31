from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.users.decorators import (
    admin_or_manager_or_staff_required,
    admin_or_manager_required,
)

from .forms import StaffDepartureForm, StaffForm
from .models import Staff, StaffDeparture


@login_required
@admin_or_manager_or_staff_required
def staff_list(request):
    active_staff = Staff.objects.filter(is_departed=False)
    queryset = active_staff.order_by("first_name", "last_name", "id")

    search_query = request.GET.get("search", "").strip()
    if search_query:
        queryset = queryset.filter(
            Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(department__icontains=search_query)
            | Q(job_title__icontains=search_query)
        )

    paginator = Paginator(queryset, 25)
    page = request.GET.get("page")

    try:
        records = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        records = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        records = paginator.page(paginator.num_pages)

    return render(
        request,
        "staff/staff_details.html",
        {
            "records": records,
            "table_title": "Staff List",
            "active_staff_count": active_staff.count(),
            "sponsored_staff_count": active_staff.filter(is_sponsored=True).count(),
            "non_sponsored_staff_count": active_staff.filter(is_sponsored=False).count(),
            "departed_staff_count": Staff.objects.filter(is_departed=True).count(),
            "search_query": search_query or "",
        },
    )


# =================================== Register Staff ===================================


@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
def register_staff(request):
    if request.method == "POST":
        form = StaffForm(request.POST, request.FILES)

        if form.is_valid():
            form.save()
            messages.info(request, "Record saved successfully!", extra_tags="bg-success")
            return redirect("register_staff")
        else:
            # Display an error message if the form is not valid
            messages.error(
                request,
                "There was an error saving the record. Please check the form for errors.",
                extra_tags="bg-danger",
            )
    else:
        form = StaffForm()
    return render(
        request,
        "staff/staff_register.html",
        {
            "form_name": "Staff Registration",
            "form": form,
            "active_staff_count": Staff.objects.filter(is_departed=False).count(),
            "departed_staff_count": Staff.objects.filter(is_departed=True).count(),
            "sponsored_staff_count": Staff.objects.filter(
                is_departed=False,
                is_sponsored=True,
            ).count(),
        },
    )


# =================================== Update Staff data ===================================
@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
def update_staff(request, pk, template_name="staff/staff_update.html"):
    # Fetch the staff record or raise an error if not found
    staff_record = get_object_or_404(Staff, pk=pk)

    if request.method == "POST":
        form = StaffForm(request.POST, request.FILES, instance=staff_record)

        if form.is_valid():
            form.save()
            messages.success(request, "Staff record updated successfully!", extra_tags="bg-success")
            return redirect("staff_list")  # Redirect to the staff list after successful update
        else:
            messages.error(
                request,
                "There was an error saving the record. Please check the form for errors.",
                extra_tags="bg-danger",
            )
    else:
        # Populate the form with the existing staff data for GET requests
        form = StaffForm(instance=staff_record)

    context = {"form_name": "Update Staff Information", "form": form}
    return render(request, template_name, context)


# =================================== Deleted selected Staff ===================================
@login_required
@admin_or_manager_required
@transaction.atomic
def delete_staff(request, pk):
    records = Staff.objects.get(id=pk)
    records.delete()
    messages.info(request, "Record deleted successfully!", extra_tags="bg-danger")
    return HttpResponseRedirect(reverse("staff_list"))


# =================================== Depart staff ===================================
@login_required
@admin_or_manager_required
@transaction.atomic
def staff_departure(request):
    if request.method == "POST":
        form = StaffDepartureForm(request.POST, request.FILES)
        if form.is_valid():
            staff_id = request.POST.get("id")
            if not staff_id:
                messages.error(
                    request,
                    "Please select a staff member to depart.",
                    extra_tags="bg-danger",
                )
                return redirect("staff_departure")

            staff_instance = get_object_or_404(
                Staff.objects.filter(is_departed=False),
                pk=staff_id,
            )

            # Create a StaffDeparture instance
            staff_depart = StaffDeparture.objects.create(staff=staff_instance)
            staff_depart.departure_date = form.cleaned_data["departure_date"]
            staff_depart.departure_reason = form.cleaned_data["departure_reason"]
            staff_depart.save()

            # Update Staff status to "departed"
            staff_instance.is_departed = True
            staff_instance.is_sponsored = False
            staff_instance.save(update_fields=["is_departed", "is_sponsored", "updated_at"])

            messages.success(request, "Staff departed successfully!", extra_tags="bg-success")
            return redirect("staff_departure")
        else:
            messages.error(request, "Form is invalid.", extra_tags="bg-danger")
    else:
        form = StaffDepartureForm()

    records = Staff.objects.filter(is_departed=False).order_by("id")
    return render(
        request,
        "staff/staff_depature.html",
        {
            "form": form,
            "form_name": "Staff Departure Form",
            "records": records,
            "active_staff_count": records.count(),
            "departed_staff_count": Staff.objects.filter(is_departed=True).count(),
        },
    )


# =================================== staff Depature Report ===================================
@login_required
@admin_or_manager_required
def staff_depature_list(request):
    queryset = (
        Staff.objects.filter(is_departed=True).order_by("first_name", "last_name", "id").prefetch_related("departures")
    )

    search_query = request.GET.get("search", "").strip()
    if search_query:
        queryset = queryset.filter(
            Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(department__icontains=search_query)
            | Q(job_title__icontains=search_query)
        )

    paginator = Paginator(queryset, 25)
    page = request.GET.get("page")

    try:
        records = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        records = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        records = paginator.page(paginator.num_pages)

    return render(
        request,
        "staff/staff_depature_list.html",
        {
            "records": records,
            "table_title": "Departed Staff",
            "search_query": search_query,
            "departed_staff_count": queryset.count(),
            "active_staff_count": Staff.objects.filter(is_departed=False).count(),
        },
    )


# =================================== Reinstate departed staff ===================================
@login_required
@admin_or_manager_required
@transaction.atomic
def reinstate_staff(request, pk):
    staff = get_object_or_404(Staff, id=pk)

    if request.method == "POST":
        staff.is_departed = False
        staff.save(update_fields=["is_departed", "updated_at"])
        messages.success(request, "staff reinstated successfully!", extra_tags="bg-success")

        return redirect("staff_depature_list")

    return render(request, "staff/staff_depature_list.html", {"staff": staff})
