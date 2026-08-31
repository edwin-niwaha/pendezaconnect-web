from django import forms

from .models import (
    Category,
    Inventory,
    Product,
    ProductImage,
    ProductVariant,
    StockMovement,
)


# =================================== category form ===================================
class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter category name"}),
            "description": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter category description",
                }
            ),
        }
        labels = {
            "name": "Category Name",
            "description": "Description",
        }


# =================================== product form ===================================
class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name",
            "cost",
            "price",
            "description",
            "status",
            "category",
            "supplier",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter product name"}),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter product description",
                    "rows": 3,
                }
            ),
            "status": forms.Select(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-control"}),
            "supplier": forms.Select(attrs={"class": "form-control"}),
        }
        labels = {
            "name": "Product Name",
            "cost": "Cost Price",
            "price": "Selling Price",
            "description": "Description",
            "status": "Status",
            "category": "Category",
            "suppliers": "Suppliers",  # Label for the suppliers field
        }


class ProductVariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = [
            "product",
            "name",
            "sku",
            "barcode",
            "option_value",
            "cost",
            "price",
            "quantity",
            "low_stock_threshold",
            "status",
            "is_default",
        ]
        widgets = {
            "product": forms.Select(attrs={"class": "form-control"}),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Example: Blue / Large"}),
            "sku": forms.TextInput(attrs={"class": "form-control", "placeholder": "Unique variant SKU"}),
            "barcode": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional barcode"}),
            "option_value": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Size, color, pack, etc.",
                }
            ),
            "cost": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "low_stock_threshold": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "status": forms.Select(attrs={"class": "form-control"}),
            "is_default": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        cost = cleaned_data.get("cost")
        price = cleaned_data.get("price")

        if cost is not None and price is not None and price < cost:
            self.add_error("price", "Selling price should not be below cost.")

        return cleaned_data


# =================================== CHILD PROFILE ===================================
class ProductImageForm(forms.ModelForm):
    image = forms.ImageField(required=False)

    class Meta:
        model = ProductImage
        fields = ["image"]

        labels = {
            "image": "Upload Product Image:",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["image"].widget = forms.FileInput(attrs={"accept": "image/*"})

    def clean_image(self):
        image = self.cleaned_data.get("image")
        return image


class InventoryForm(forms.ModelForm):
    class Meta:
        model = Inventory
        fields = ["product", "quantity", "low_stock_threshold"]
        widgets = {
            "product": forms.Select(attrs={"class": "form-control"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Enter stock quantity"}),
            "low_stock_threshold": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter low stock threshold",
                }
            ),
        }
        labels = {
            "product": "Product",
            "quantity": "Stock Quantity",
            "low_stock_threshold": "Low Stock Threshold",
        }


class StockAdjustmentForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.all().order_by("name"),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Base Product",
    )
    variant = forms.ModelChoiceField(
        queryset=ProductVariant.objects.select_related("product").all().order_by("product__name", "name"),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Product Variant",
    )
    movement_type = forms.ChoiceField(
        choices=[
            (StockMovement.STOCK_IN, "Stock In"),
            (StockMovement.STOCK_OUT, "Stock Out"),
            (StockMovement.ADJUSTMENT, "Manual Adjustment"),
            (StockMovement.RETURN, "Return"),
        ],
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
        help_text="Enter a positive quantity. Stock Out will deduct it.",
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get("product")
        variant = cleaned_data.get("variant")

        if not product and not variant:
            raise forms.ValidationError("Select either a base product or a variant.")

        if product and variant:
            raise forms.ValidationError("Select only one stock item to adjust.")

        return cleaned_data
