import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template
from xhtml2pdf import pisa

from apps.inventory.customers.models import Customer
from apps.inventory.products.models import (
    Inventory,
    Product,
    ProductVariant,
    StockMovement,
)

# Import custom decorators
from apps.users.decorators import (
    admin_or_manager_or_staff_required,
    admin_required,
)
from core.wsgi import *

from .forms import ReportPeriodForm
from .models import Sale, SaleDetail

logger = logging.getLogger(__name__)


# =================================== Sale list view ===================================


@login_required
@admin_or_manager_or_staff_required
def sales_list_view(request):
    # Fetch sales with enough item detail to calculate variant-aware profit.
    sales = (
        Sale.objects.all()
        .select_related("customer")
        .prefetch_related("items__product", "items__variant")
        .order_by("-id")
    )

    for sale in sales:
        sale.profit = sum(item.calculate_profit() for item in sale.items.all())

    paginator = Paginator(sales, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Calculate aggregated totals
    grand_total = sales.aggregate(Sum("grand_total"))["grand_total__sum"] or 0
    total_items = sum(sale.sum_items() for sale in sales)
    total_profit = sum(sale.profit for sale in sales)

    context = {
        "table_title": "Sales List",
        "sales": page_obj,
        "grand_total": grand_total,
        "total_items": total_items,
        "total_profit": total_profit,
    }

    return render(request, "inventory/sales/sales.html", context)


# =================================== Sale add view ===================================
@admin_or_manager_or_staff_required
@login_required
def sales_add_view(request):
    # Fetch only active products with their inventory
    products = Product.objects.filter(status="ACTIVE").select_related("inventory").prefetch_related("variants")
    variants = ProductVariant.objects.filter(status="ACTIVE", product__status="ACTIVE").select_related("product")
    sale_items = []
    for product in products:
        active_variants = list(product.variants.filter(status="ACTIVE"))
        if not active_variants:
            sale_items.append(
                {
                    "value": f"product:{product.id}",
                    "name": product.name,
                    "price": product.price,
                    "cost": product.cost,
                    "stock": product.base_stock,
                }
            )

    for variant in variants:
        sale_items.append(
            {
                "value": f"variant:{variant.id}",
                "name": variant.display_name,
                "price": variant.effective_price,
                "cost": variant.effective_cost,
                "stock": variant.quantity,
            }
        )

    context = {
        "customers": [c.to_select2() for c in Customer.objects.all()],
        "products": products,
        "sale_items": sale_items,
        "total_stock": sum(item["stock"] for item in sale_items),
    }

    if request.method == "POST":
        try:
            logger.debug(f"POST data: {request.POST}")

            # Extract and process form data
            customer_id = int(request.POST.get("customer"))
            sale_attributes = {
                "customer": Customer.objects.get(id=customer_id),
                "trans_date": request.POST.get("trans_date"),
                "sub_total": float(request.POST.get("sub_total", 0)),
                "grand_total": float(request.POST.get("grand_total", 0)),
                "tax_amount": float(request.POST.get("tax_amount", 0)),
                "tax_percentage": float(request.POST.get("tax_percentage", 0)),
                "amount_payed": float(request.POST.get("amount_payed", 0)),
                "amount_change": float(request.POST.get("amount_change", 0)),
            }

            with transaction.atomic():
                # Create the sale
                new_sale = Sale.objects.create(**sale_attributes)
                logger.info(f"Sale created successfully: {sale_attributes}")

                # Extract product details from form data
                products_data = request.POST.getlist("products")
                for product_data_str in products_data:
                    product_data = json.loads(product_data_str)
                    item_type = product_data.get("type", "product")
                    item_id = int(product_data["id"])
                    quantity_requested = int(product_data["quantity"])
                    variant_obj = None

                    if item_type == "variant":
                        variant_obj = ProductVariant.objects.select_for_update().get(id=item_id)
                        product_obj = variant_obj.product
                        if variant_obj.quantity < quantity_requested:
                            raise ValueError(f"Oops! Insufficient stock for {variant_obj.display_name}")
                        variant_obj.quantity -= quantity_requested
                        variant_obj.save(update_fields=["quantity", "updated_at"])
                    else:
                        product_obj = Product.objects.select_for_update().get(id=item_id)
                        # Check if the product has inventory and stock is available
                        if not hasattr(product_obj, "inventory") or product_obj.inventory.quantity < quantity_requested:
                            raise ValueError(f"Oops! Insufficient stock for {product_obj.name}")

                        # Update inventory stock
                        inventory_obj = product_obj.inventory
                        inventory_obj.quantity -= quantity_requested
                        inventory_obj.save()
                        logger.info(f"Stock updated for {product_obj.name}: {inventory_obj.quantity}")

                    # Create sale detail
                    detail_attributes = {
                        "sale": new_sale,
                        "product": product_obj,
                        "variant": variant_obj,
                        "price": float(product_data["price"]),
                        "quantity": quantity_requested,
                        "total_detail": float(product_data["total_product"]),
                    }
                    SaleDetail.objects.create(**detail_attributes)
                    StockMovement.objects.create(
                        product=product_obj,
                        variant=variant_obj,
                        movement_type=StockMovement.SALE,
                        quantity=-quantity_requested,
                        unit_cost=(variant_obj.effective_cost if variant_obj else product_obj.cost),
                        unit_price=float(product_data["price"]),
                        reference=f"Sale #{new_sale.id}",
                        created_by=request.user,
                    )
                    logger.info(f"Sale detail added: {detail_attributes}")

                messages.success(request, "Sale created successfully!", extra_tags="bg-success")
                return redirect("sales:sales_list")

        except ValueError as ve:
            logger.error(f"Stock error: {ve}")
            messages.error(request, str(ve), extra_tags="danger")
        except Exception as e:
            logger.error(f"Error during sale creation: {e}")
            messages.error(
                request,
                f"There was an error during the creation! Error: {e}",
                extra_tags="danger",
            )

        return redirect("sales:sales_list")

    return render(request, "inventory/sales/sales_add.html", context=context)


# =================================== Sale details view ===================================
@login_required
@admin_or_manager_or_staff_required
def sales_details_view(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id)

    # Get the sale details related to the sale
    details = SaleDetail.objects.filter(sale=sale)

    context = {
        "active_icon": "sales",
        "sale": sale,
        "details": details,
    }

    return render(request, "inventory/sales/sales_details.html", context=context)


# =================================== Sale delete view ===================================
@login_required
@admin_required
@transaction.atomic
def sale_delete_view(request, sale_id):
    try:
        # Get the sale to delete
        sale = Sale.objects.get(id=sale_id)
        sale.delete()
        messages.success(request, f"Sale: {sale_id} deleted successfully!", extra_tags="bg-success")
    except Sale.DoesNotExist:
        # Specific exception for when the sale is not found
        messages.error(
            request,
            f"Sale: {sale_id} not found!",
            extra_tags="bg-danger",
        )
    except Exception as e:
        # General exception for any other errors
        messages.error(
            request,
            "There was an error during the elimination!",
            extra_tags="bg-danger",
        )
        print(e)
    finally:
        return redirect("sales:sales_list")


# =================================== Sale receipt view ===================================
@login_required
@admin_or_manager_or_staff_required
def receipt_pdf_view(request, sale_id):
    # Get the sale
    sale = Sale.objects.get(id=sale_id)

    # Get the sale details
    details = SaleDetail.objects.filter(sale=sale)

    # Render the template
    template = get_template("inventory/sales/sales_receipt_pdf.html")
    context = {"sale": sale, "details": details}
    html_template = template.render(context)

    # Create a file-like buffer to receive PDF data
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="receipt.pdf"'

    # Convert HTML to PDF
    pisa_status = pisa.CreatePDF(html_template, dest=response)

    # Check if PDF was created successfully
    if pisa_status.err:
        return HttpResponse("Error generating PDF", status=500)

    return response


# =================================== Sale Report view ===================================


# @login_required
# @admin_or_manager_or_staff_required
# def sales_report_view(request):
#     # Initialize the form with GET parameters
#     form = ReportPeriodForm(request.GET or None)

#     # Validate form and extract start and end dates
#     if form.is_valid():
#         start_date = form.cleaned_data.get("start_date")
#         end_date = form.cleaned_data.get("end_date")
#     else:
#         start_date = end_date = None

#     # Fetch all sales with optional date filtering
#     sales = (
#         Sale.objects.all()
#         .select_related("customer")
#         .prefetch_related("items__product__inventory")
#         .order_by("id")
#     )

#     # Apply date filters if provided
#     if start_date:
#         sales = sales.filter(trans_date__gte=start_date)
#     if end_date:
#         sales = sales.filter(trans_date__lte=end_date)

#     # Calculate grand total for all sales
#     grand_total = sales.aggregate(Sum("grand_total"))["grand_total__sum"] or 0

#     # Calculate total items sold across all sales
#     total_items = sum(sale.sum_items() for sale in sales)

#     # Initialize totals for profit and stock balance
#     total_profit = 0
#     sales_with_details = []

#     # Iterate over each sale to calculate profit and stock balance
#     for sale in sales:
#         sale_profit = sum(item.calculate_profit() for item in sale.items.all())

#         # Attach the calculated profit and stock balance to the sale instance
#         sale.profit = sale_profit

#         # Add to overall totals
#         total_profit += sale_profit

#         # Add the sale to the list with details
#         sales_with_details.append(sale)

#     # Context to pass to the template
#     context = {
#         "table_title": "Sales Report",  # Title for the table
#         "sales": sales_with_details,  # List of sales with detailed info
#         "grand_total": grand_total,  # Total grand total for all sales
#         "total_items": total_items,  # Total number of items sold across all sales
#         "total_profit": total_profit,  # Total profit from all sales
#         "start_date": start_date,
#         "end_date": end_date,
#         "form": form,
#     }

#     return render(request, "inventory/sales/sales_report.html", context=context)


def sales_report_view(request):
    # Initialize the form with GET data
    form = ReportPeriodForm(request.GET or None)
    start_date = None
    end_date = None

    if form.is_valid():
        start_date = form.cleaned_data["start_date"]
        end_date = form.cleaned_data["end_date"]

    # Filter sales by date range and prefetch related data
    sales = (
        Sale.objects.all()
        .select_related("customer")
        .prefetch_related("items__product__inventory", "items__variant")
        .order_by("id")
    )

    if start_date:
        sales = sales.filter(trans_date__gte=start_date)
    if end_date:
        sales = sales.filter(trans_date__lte=end_date)

    for sale in sales:
        sale.profit = sum(item.calculate_profit() for item in sale.items.all())

    # Calculate stock balance
    stock_balance = Inventory.objects.aggregate(total_stock=Sum("quantity"))["total_stock"] or 0

    context = {
        "form": form,
        "start_date": start_date,
        "end_date": end_date,
        "sales": sales,
        "grand_total": sales.aggregate(Sum("grand_total"))["grand_total__sum"] or 0,
        "total_items": sum(sale.sum_items() for sale in sales),
        "total_profit": sum(sale.profit for sale in sales),
        "stock_balance": stock_balance,
        "table_title": "Sales Report",
    }

    return render(request, "inventory/sales/sales_report.html", context)
