import base64
import csv
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import F, Q
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from core.profile_photos import normalize_profile_photo

logger = logging.getLogger(__name__)

from apps.users.decorators import (
    admin_or_manager_or_staff_required,
    admin_or_manager_required,
    admin_required,
)
from apps.users.roles import is_staff_user

from .forms import ClientForm, ClientPhotoForm, ImportClientsForm, SevenHillsRegistrationForm
from .importing import import_clients
from .models import Client, ClientImportJob, ClientProfilePicture, ClientRegistrationDraft, SevenHillsRegistration
from .profile_fields import PROFILE_FIELDS, profile_sections
from .tasks import enqueue_client_import


# =================================== Fetch and display all clients details ===================================
@login_required
@admin_or_manager_or_staff_required
def client_list(request, inactive_report=False):
    status = "inactive" if inactive_report else request.GET.get("status", "active")
    if status not in {"active", "inactive", "all"}:
        status = "active"
    all_clients = Client.objects.all()
    base_queryset = all_clients.select_related("status_changed_by").prefetch_related("profile_pictures").order_by(
        F("reg_number").asc(nulls_last=True), "id"
    )
    if status != "all":
        base_queryset = base_queryset.filter(is_active=status == "active")
    queryset = base_queryset

    search_query = request.GET.get("search", "").strip()
    if search_query:
        queryset = queryset.filter(
            Q(full_name__icontains=search_query)
            | Q(reg_number__icontains=search_query)
            | Q(mobile_telephone__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(branch__icontains=search_query)
            | Q(occupation__icontains=search_query)
        )

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        filename = "inactive_clients.csv" if status == "inactive" else "clients.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        writer = csv.writer(response)
        export_fields = (*PROFILE_FIELDS, "is_active", "status_changed_at", "status_changed_by")
        writer.writerow(export_fields)
        for client in queryset.iterator(chunk_size=200):
            values = []
            for name in export_fields:
                value = getattr(client, name)
                text = str(value) if value is not None else ""
                # Prevent text values being evaluated as spreadsheet formulas.
                if text.startswith(("=", "+", "-", "@")):
                    text = "'" + text
                values.append(text)
            writer.writerow(values)
        return response

    paginator = Paginator(queryset, 20)  # Show 20 records per page
    page = request.GET.get("page")

    try:
        records = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        records = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        records = paginator.page(paginator.num_pages)

    for client in records:
        client.preview_sections = profile_sections(client)

    return render(
        request,
        "client/client_list.html",
        {
            "records": records,
            "table_title": "Inactive clients report" if inactive_report else "Client directory",
            "inactive_report": inactive_report,
            "status_filter": status,
            "active_clients": all_clients.filter(is_active=True).count(),
            "inactive_clients": all_clients.filter(is_active=False).count(),
            "can_manage_status": (
                getattr(getattr(request.user, "profile", None), "role", "") in {"administrator", "manager", "ed", "hof"}
                or is_staff_user(request.user, {"administrator", "manager", "ed", "hof"})
            ),
            "search_query": search_query,
            "total_clients": base_queryset.count(),
            "clients_with_phone": base_queryset.exclude(mobile_telephone__isnull=True)
            .exclude(mobile_telephone="")
            .count(),
            "clients_with_email": base_queryset.exclude(email__isnull=True)
            .exclude(email="")
            .exclude(email="no-email@example.com")
            .count(),
        },
    )


@login_required
@admin_or_manager_required
@require_POST
@transaction.atomic
def change_client_status(request, pk):
    action = request.POST.get("action")
    if action not in {"deactivate", "reactivate"}:
        return HttpResponse("Choose deactivate or reactivate.", status=400)
    client = get_object_or_404(Client.objects.select_for_update(), pk=pk)
    active = action == "reactivate"
    if client.is_active != active:
        client.is_active = active
        client.status_changed_at = timezone.now()
        client.status_changed_by = request.user
        client.save(update_fields=["is_active", "status_changed_at", "status_changed_by", "updated_at"])
        messages.success(request, f"{client.full_name} has been {'reactivated' if active else 'deactivated'}.")
    else:
        messages.info(request, "This client already has the selected status.")
    return redirect("inactive_clients_report" if request.POST.get("return_to") == "inactive" else "client_list")


# =================================== Upload Client Photo ===================================


@login_required
@transaction.atomic
@admin_or_manager_or_staff_required
def upload_client_photo(request):
    clients = Client.objects.order_by("full_name", "id")
    form = ClientPhotoForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        client = get_object_or_404(clients, pk=request.POST.get("id"))
        remove_requested = request.POST.get("remove_picture") == "1"
        uploaded_picture = form.cleaned_data.get("picture")

        if remove_requested and not uploaded_picture:
            ClientProfilePicture.objects.filter(client=client, is_current=True).update(is_current=False)
            client.picture = None
            client.save(update_fields=["picture", "updated_at"])
            messages.success(
                request,
                f"Current profile picture removed from {client.full_name}.",
                extra_tags="bg-success",
            )
            return redirect("upload_client_photo")

        if uploaded_picture:
            ClientProfilePicture.objects.filter(client=client, is_current=True).update(is_current=False)
            photo = ClientProfilePicture.objects.create(
                client=client,
                picture=uploaded_picture,
                is_current=True,
            )
            client.picture = photo.picture
            client.save(update_fields=["picture", "updated_at"])
            messages.success(
                request,
                f"Photo updated for {client.full_name}.",
                extra_tags="bg-success",
            )
            return redirect("upload_client_photo")

        form.add_error("picture", "Take a photo, choose one from the gallery, or remove the current picture.")

    if request.method == "POST":
        messages.error(
            request,
            "The photo could not be uploaded. Check the selected client and photo.",
            extra_tags="bg-danger",
        )

    return render(
        request,
        "client/client_photo.html",
        {
            "form": form,
            "clients": clients,
            "form_name": "Upload Client Photo",
            "allow_current_photo_removal": True,
        },
    )


@login_required
@admin_or_manager_required
@transaction.atomic
def delete_client_profile_picture(request, pk):
    if request.method != "POST":
        messages.error(request, "Use the Delete button to remove a client photo.")
        return redirect("client_list")

    photo = get_object_or_404(ClientProfilePicture.objects.select_related("client"), pk=pk)
    client = photo.client
    was_current = photo.is_current or str(client.picture) == str(photo.picture)
    photo.delete()

    if was_current:
        replacement = ClientProfilePicture.objects.filter(client=client).first()
        if replacement:
            replacement.is_current = True
            replacement.save(update_fields=["is_current"])
            client.picture = replacement.picture
        else:
            client.picture = None
        client.save(update_fields=["picture", "updated_at"])

    messages.info(request, f"Photo removed from {client.full_name}.", extra_tags="bg-danger")
    return redirect("client_list")


# =================================== Register Client  ===================================


@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
@never_cache
def register_client(request):
    if request.method == "POST" and request.POST.get("draft_id"):
        draft = (
            ClientRegistrationDraft.objects.select_for_update()
            .filter(
                user=request.user,
                pk=request.POST["draft_id"],
            )
            .first()
        )
        if not draft:
            messages.info(request, "This registration has already been completed. Start a new client below.")
            return redirect("register_client")
    else:
        draft, _ = ClientRegistrationDraft.objects.get_or_create(user=request.user)
    if request.method == "POST":
        files = request.FILES.copy()
        if not files.get("picture") and draft.photo and request.POST.get("remove_picture") != "1":
            files["picture"] = SimpleUploadedFile(draft.photo_name, bytes(draft.photo), content_type="image/jpeg")
        form = ClientForm(request.POST, files)

        if form.is_valid():
            client = form.save()
            if client.picture:
                ClientProfilePicture.objects.filter(client=client, is_current=True).update(is_current=False)
                ClientProfilePicture.objects.create(
                    client=client,
                    picture=client.picture,
                    is_current=True,
                )
            draft.delete()
            messages.success(request, "Record saved successfully!", extra_tags="bg-success")
            return redirect("register_client")
        else:
            # Display an error message if the form is not valid
            messages.error(
                request,
                "There was an error saving the record. Please check the form for errors.",
                extra_tags="bg-danger",
            )

    else:
        form = ClientForm(initial=draft.data)

    return render(
        request,
        "client/client_register.html",
        {
            "form_name": "Client Registration",
            "form": form,
            "draft": draft,
            "allow_current_photo_removal": True,
            "current_photo_url": "data:image/jpeg;base64," + base64.b64encode(bytes(draft.photo)).decode()
            if draft.photo
            else "",
        },
    )


@login_required
@admin_or_manager_or_staff_required
@require_POST
@never_cache
@transaction.atomic
def save_registration_draft(request):
    draft = ClientRegistrationDraft.objects.select_for_update().filter(user=request.user).first()
    if (
        not draft
        or request.POST.get("draft_id") != str(draft.pk)
        or request.POST.get("revision") != str(draft.revision)
    ):
        return JsonResponse({"error": "This draft changed in another page. Reload before continuing."}, status=409)
    data = {name: request.POST.get(name, "") for name in PROFILE_FIELDS}
    if any(len(value) > 10000 for value in data.values()):
        return JsonResponse({"error": "A field is too long to save."}, status=400)
    try:
        step = max(0, min(6, int(request.POST.get("step", 0))))
        photo = normalize_profile_photo(request.FILES.get("picture"))
    except (ValueError, TypeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    if photo:
        draft.photo, draft.photo_name = photo.read(), photo.name[:255]
    elif request.POST.get("remove_picture") == "1":
        draft.photo, draft.photo_name = None, ""
    draft.data, draft.step = data, step
    draft.revision += 1
    draft.save()
    return JsonResponse({"revision": draft.revision, "saved_at": draft.updated_at.isoformat()})


# =================================== Update client data ===================================
@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
def update_client(request, pk, template_name="client/client_update.html"):
    try:
        client_record = Client.objects.get(pk=pk)
    except Client.DoesNotExist:
        messages.error(request, "Client record not found!", extra_tags="bg-danger")
        return redirect("client_list")  # Or a relevant error page

    if request.method == "POST":
        form = ClientForm(request.POST, request.FILES, instance=client_record)
        if form.is_valid():
            uploaded_picture = request.FILES.get("picture")
            remove_picture = request.POST.get("remove_picture") == "1" and not uploaded_picture
            client = form.save(commit=False)
            if remove_picture:
                client.picture = None
            client.save()

            if uploaded_picture and client.picture:
                ClientProfilePicture.objects.filter(client=client, is_current=True).update(is_current=False)
                ClientProfilePicture.objects.create(
                    client=client,
                    picture=client.picture,
                    is_current=True,
                )
            elif remove_picture:
                ClientProfilePicture.objects.filter(client=client, is_current=True).update(is_current=False)

            messages.success(request, "Client record updated successfully!", extra_tags="bg-success")
            return redirect("client_list")
    else:
        # Pre-populate the form with existing data
        form = ClientForm(instance=client_record)

    context = {
        "form_name": "Update client",
        "client_record": client_record,
        "allow_current_photo_removal": True,
        "form": form,
        "current_photo_url": client_record.picture.url if client_record.picture else "",
        "photo_subject": client_record.full_name,
    }
    return render(request, template_name, context)


# =================================== Delete selected client ===================================
@login_required
@admin_or_manager_required
@transaction.atomic
def delete_client(request, pk):
    records = Client.objects.get(id=pk)
    records.delete()
    messages.info(request, "Record deleted successfully!", extra_tags="bg-danger")
    return HttpResponseRedirect(reverse("client_list"))


# =================================== Process and Import Excel data ===================================
@login_required
@admin_required
def import_client_data(request):
    result = None
    if request.method == "POST":
        form = ImportClientsForm(request.POST, request.FILES)
        if form.is_valid():
            excel_file = form.cleaned_data["excel_file"]
            if not excel_file.name.lower().endswith(".xlsx"):
                form.add_error("excel_file", "Please upload an .xlsx workbook.")
            elif excel_file.size > 10 * 1024 * 1024:
                form.add_error("excel_file", "Upload a workbook smaller than 10 MB. Split larger files first.")
            else:
                job = ClientImportJob.objects.create(
                    user=request.user, filename=excel_file.name[:255], workbook=excel_file.read()
                )
                transaction.on_commit(lambda: enqueue_client_import(job.pk))
                return redirect("client_import_status", pk=job.pk)
    else:
        form = ImportClientsForm()
    jobs = ClientImportJob.objects.filter(user=request.user).defer("workbook", "result").order_by("-created_at")[:10]
    return render(request, "client/bulk_import.html", {"form": form, "result": result, "jobs": jobs})


@login_required
@admin_required
@never_cache
def client_import_status(request, pk):
    job = get_object_or_404(ClientImportJob.objects.defer("workbook"), pk=pk, user=request.user)
    if request.GET.get("format") == "json":
        return JsonResponse({"status": job.status, "processed": job.processed})
    return render(request, "client/import_status.html", {"job": job, "result": job.result})


# Function to import Excel data
def process_and_import_data(excel_file):
    return import_clients(excel_file)


@login_required
@admin_or_manager_or_staff_required
def client_profile(request, pk):
    client = get_object_or_404(Client, pk=pk)
    return render(
        request,
        "client/client_profile.html",
        {
            "client": client,
            "sections": profile_sections(client),
        },
    )


# =================================== Delete all records at once ===================================
@login_required
@admin_or_manager_required
@transaction.atomic
def delete_confirm(request):
    if request.method == "POST":
        Client.objects.all().delete()
        messages.info(request, "All records deleted!", extra_tags="bg-danger")
        return HttpResponseRedirect(reverse("client_list"))


# =================================== seven_hills registration ===================================
@login_required
@transaction.atomic
def seven_hills_registration_view(request):
    if request.method == "POST":
        form = SevenHillsRegistrationForm(request.POST, request.FILES)

        if form.is_valid():
            form.save()
            messages.success(request, "Record saved successfully!", extra_tags="bg-success")
            return redirect("seven_hills_registration")
        else:
            # Display error messages if the form is invalid
            messages.error(
                request,
                "There was an error saving the record. Please check the form for errors.",
                extra_tags="bg-danger",
            )
    else:
        form = SevenHillsRegistrationForm()

    context = {
        "form_name": "Seven Hills Registration Form",
        "form": form,
    }

    return render(request, "client/seven_hills_register.html", context)


# =================================== Fetch and display all Seven Hills Registration details ===================================
@login_required
def seven_hills_list(request):
    # Fetch all records
    queryset = SevenHillsRegistration.objects.all().order_by("id")

    # Apply search filter
    search_query = request.GET.get("search")
    if search_query:
        queryset = queryset.filter(
            Q(full_name__icontains=search_query)
            | Q(residence__icontains=search_query)
            | Q(services_interested__icontains=search_query)
            | Q(ministry_groups__icontains=search_query)
        )
        if not queryset.exists():
            messages.info(request, "No results found for your search.")

    # Paginate the filtered queryset
    paginator = Paginator(queryset, 100)
    page = request.GET.get("page")

    try:
        records = paginator.page(page)
    except PageNotAnInteger:
        records = paginator.page(1)
    except EmptyPage:
        records = paginator.page(paginator.num_pages)

    # Pass both the full queryset and paginated records to the template
    return render(
        request,
        "client/seven_hills_list.html",
        {
            "records": records,  # Paginated records for display
            "table_title": "Seven Hills Members List",
            "queryset": queryset,  # Full queryset if needed elsewhere
        },
    )


# =================================== Update Seven Hills data ===================================
@login_required
@transaction.atomic
def update_seven_hills(request, pk, template_name="client/seven_hills_update.html"):
    try:
        record = SevenHillsRegistration.objects.get(pk=pk)
    except SevenHillsRegistration.DoesNotExist:
        messages.error(request, "Record not found!", extra_tags="bg-danger")
        return redirect("seven_hills_list")  # Or a relevant error page

    if request.method == "POST":
        form = SevenHillsRegistrationForm(request.POST, request.FILES, instance=record)
        if form.is_valid():
            form.save()

            messages.success(request, "Record updated successfully!", extra_tags="bg-success")
            return redirect("seven_hills_list")
    else:
        # Pre-populate the form with existing data
        form = SevenHillsRegistrationForm(instance=record)

    context = {"form_name": "Seven Hills Update", "form": form}
    return render(request, template_name, context)


# =================================== Delete selected Seven Hills ===================================
@login_required
@admin_or_manager_required
@transaction.atomic
def delete_seven_hills(request, pk):
    records = SevenHillsRegistration.objects.get(id=pk)
    records.delete()
    messages.info(request, "Record deleted successfully!", extra_tags="bg-danger")
    return HttpResponseRedirect(reverse("seven_hills_list"))


# =================================== Fetch and display selected member details ===================================
@login_required
def seven_hills_details(request, pk):
    record = SevenHillsRegistration.objects.get(pk=pk)
    age = record.calculate_age()

    context = {"table_title": "Profile Report", "record": record, "age": age}
    return render(request, "client/seven_hills_profile_rpt.html", context)
