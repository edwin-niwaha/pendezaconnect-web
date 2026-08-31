from django.contrib import messages
from django.contrib.auth.decorators import login_required

# =================================== supplier list view ===================================
# @login_required
# @admin_or_manager_or_staff_required
# def supplier_list(request):
#     suppliers = Supplier.objects.all()
#     # Pagination setup
#     paginator = Paginator(suppliers, 10)  # Display 10 suppliers per page
#     page_number = request.GET.get("page")  # Get the page number from the query string
#     page_obj = paginator.get_page(page_number)  # Get the current page
#     return render(
#         request,
#         "inventory/supplier/suppliers.html",
#         {"suppliers": page_obj},  # Pass the paginated object to the template
#     )
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.users.decorators import (
    admin_or_manager_or_staff_required,
    admin_required,
)

from .forms import SupplierForm
from .models import Supplier


@login_required
@admin_or_manager_or_staff_required
def supplier_list(request):
    search_query = request.GET.get("search", "")  # Get the search query from the GET request

    # Filter suppliers based on search query
    if search_query:
        suppliers = Supplier.objects.filter(
            Q(name__icontains=search_query)
            | Q(contact_name__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(phone__icontains=search_query)
            | Q(address__icontains=search_query)
        )
    else:
        suppliers = Supplier.objects.all()

    # Pagination setup
    paginator = Paginator(suppliers, 10)  # Display 10 suppliers per page
    page_number = request.GET.get("page")  # Get the page number from the query string
    page_obj = paginator.get_page(page_number)  # Get the current page

    return render(
        request,
        "inventory/supplier/suppliers.html",
        {
            "suppliers": page_obj,
            "search_query": search_query,
        },  # Pass search query to the template
    )


# =================================== supplier add view ===================================
@login_required
@admin_or_manager_or_staff_required
def supplier_add(request):
    form_title = "Add New Supplier"
    form = SupplierForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            supplier = form.save()
            messages.success(
                request,
                f'Supplier "{supplier.name}" added successfully.',
                extra_tags="bg-success",
            )
            return redirect("supplier:supplier_list")

    return render(
        request,
        "inventory/supplier/supplier_add.html",
        {"form": form, "form_title": form_title},
    )


# =================================== supplier update view ===================================
@login_required
@admin_or_manager_or_staff_required
def supplier_update(request, supplier_id):
    supplier = get_object_or_404(Supplier, id=supplier_id)
    form_title = "Update Supplier"
    form = SupplierForm(request.POST or None, instance=supplier)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
            messages.success(request, "Supplier updated successfully!", extra_tags="bg-success")
            return redirect("supplier:supplier_list")

    return render(
        request,
        "inventory/supplier/supplier_update.html",
        {"form": form, "form_title": form_title},
    )


# =================================== supplier delete view ===================================
@login_required
@admin_required
def supplier_delete(request, supplier_id):
    supplier = get_object_or_404(Supplier, id=supplier_id)

    try:
        supplier.delete()
        messages.success(request, f"Supplier: {supplier.name} deleted!", extra_tags="bg-danger")
    except Exception as e:
        messages.error(request, "There was an error during the deletion!", extra_tags="bg-danger")
        print(e)

    return redirect("supplier:supplier_list")
