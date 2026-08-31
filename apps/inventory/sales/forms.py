from django import forms

from .models import Sale, SaleDetail


# =================================== Sale Form ===================================
class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = [
            "trans_date",
            "customer",
            "sub_total",
            "grand_total",
            "tax_amount",
            "tax_percentage",
            "amount_payed",
            "amount_change",
        ]
        widgets = {
            "trans_date": forms.DateInput(attrs={"type": "date", "required": True}),
            "date_added": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "customer": forms.Select(attrs={"class": "form-control"}),
            "sub_total": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "grand_total": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "tax_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "tax_percentage": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "amount_payed": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "amount_change": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }


# =================================== Sale Detail Form ===================================
class SaleDetailForm(forms.ModelForm):
    class Meta:
        model = SaleDetail
        fields = [
            "sale",
            "product",
            "price",
            "quantity",
            "total_detail",
        ]
        widgets = {
            "sale": forms.Select(attrs={"class": "form-control"}),
            "product": forms.Select(attrs={"class": "form-control"}),
            "price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control"}),
            "total_detail": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }


# =================================== Report Period Form Form ===================================


class ReportPeriodForm(forms.Form):
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        label="Start Date",
        required=True,
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        label="End Date",
        required=True,
    )

    def clean(self):
        # First, call the parent class's clean method to get the cleaned data
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        # Check if both start_date and end_date are provided
        if start_date and end_date:
            # Ensure that the end_date is later than start_date
            if start_date > end_date:
                # Add an error message to the 'end_date' field if the condition fails
                self.add_error("end_date", "End date must be later than start date.")

        return cleaned_data
