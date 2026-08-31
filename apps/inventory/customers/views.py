from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

# Import custom decorators
from apps.users.decorators import (
    admin_or_manager_or_staff_required,
    admin_required,
)

from .forms import CustomerForm
from .models import Customer


# =================================== customers list view ===================================
@login_required
@admin_or_manager_or_staff_required
def customers_list_view(request):
    # Query all customers
    customers = Customer.objects.all().order_by("id")

    # Search functionality: filter by first_name or last_name
    search_query = request.GET.get("search", "")  # Default to empty string if no search
    if search_query:
        # Search in both first_name and last_name
        customers = customers.filter(first_name__icontains=search_query) | customers.filter(
            last_name__icontains=search_query
        )

    # Add pagination
    paginator = Paginator(customers, 25)  # Show 25 customers per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "active_icon": "customers",
        "customers": page_obj,
        "table_title": "Customers",
        "search_query": search_query,  # Pass search query to template for persistence
    }

    return render(request, "inventory/customers/customers.html", context)


# =================================== customers add view ===================================
@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
def customers_add_view(request):
    context = {
        "table_title": "Add Customer",
    }

    if request.method == "POST":
        form = CustomerForm(request.POST)
        if form.is_valid():
            # Check for existing customer with the same attributes
            attributes = form.cleaned_data
            if Customer.objects.filter(**attributes).exists():
                messages.error(request, "Customer already exists!", extra_tags="bg-warning")
                return redirect("customers:customers_add")

            try:
                # Save the new customer
                new_customer = form.save()
                messages.success(
                    request,
                    f"Customer: {new_customer.first_name} {new_customer.last_name} created successfully!",
                    extra_tags="bg-success",
                )
                return redirect("customers:customers_list")
            except Exception as e:
                messages.error(
                    request,
                    "There was an error during the creation!",
                    extra_tags="bg-danger",
                )
                print(e)
                return redirect("customers:customers_add")
        else:
            messages.error(request, "Please correct the errors below.", extra_tags="bg-danger")
    else:
        form = CustomerForm()

    context["form"] = form
    return render(request, "inventory/customers/customers_add.html", context=context)


# =================================== customers update view ===================================
@login_required
@admin_or_manager_or_staff_required
@transaction.atomic
def customers_update_view(request, customer_id):
    # Retrieve the customer by ID
    customer = get_object_or_404(Customer, id=customer_id)

    if request.method == "POST":
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            try:
                # Save the updated customer
                form.save()
                messages.success(
                    request,
                    f"Customer: {customer.get_full_name()} updated successfully!",
                    extra_tags="bg-success",
                )
                return redirect("customers:customers_list")
            except Exception as e:
                messages.error(
                    request,
                    "There was an error during the update!",
                    extra_tags="bg-danger",
                )
                print(e)
                return redirect("customers:customers_update", customer_id=customer_id)
        else:
            messages.error(request, "Please correct the errors below.", extra_tags="bg-danger")
    else:
        form = CustomerForm(instance=customer)

    context = {
        "active_icon": "customers",
        "form": form,
        "customer": customer,
    }

    return render(request, "inventory/customers/customers_update.html", context=context)


# =================================== customers delete view ===================================
@login_required
@admin_required
@transaction.atomic
def customers_delete_view(request, customer_id):
    try:
        # Retrieve and delete the customer
        customer = Customer.objects.get(id=customer_id)
        customer.delete()
        messages.success(
            request,
            f"Customer: {customer.get_full_name()} deleted!",
            extra_tags="bg-success",
        )
        return redirect("customers:customers_list")
    except Exception as e:
        messages.error(
            request,
            "There was an error during the elimination!",
            extra_tags="bg-danger",
        )
        print(e)
        return redirect("customers:customers_list")
