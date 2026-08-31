from django.conf import settings
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField


# =================================== customers model ===================================
class Customer(models.Model):
    # Optional link to the User model for online customers
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    # Fields for both online and offline customers
    first_name = models.CharField(max_length=50, verbose_name="First Name")
    last_name = models.CharField(max_length=50, blank=True, null=True, verbose_name="Last Name")
    address = models.TextField(max_length=50, blank=True, null=True, verbose_name="Address")
    email = models.EmailField(max_length=30, blank=True, null=True, verbose_name="Email")
    phone = PhoneNumberField(
        null=True,
        blank=True,
        default="+12125552368",
        verbose_name="Business Telephone",
    )

    # Timestamps for tracking customer creation and updates
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created at")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated at")

    class Meta:
        db_table = "Customers"
        verbose_name = "Customer"
        verbose_name_plural = "Customers"

    # String representation of the customer (either user or offline name)
    def __str__(self) -> str:
        if self.user:
            # Return the online customer's username if linked
            return f"{self.user.username} (Customer)"
        return f"{self.first_name} {self.last_name}".strip()

    # Method to get full name for both online and offline customers
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    # Used for displaying customer names in a dropdown (select2)
    def to_select2(self):
        return {"label": self.get_full_name(), "value": self.id}
