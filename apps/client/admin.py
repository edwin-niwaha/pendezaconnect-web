from django.contrib import admin

from .models import Client, SevenHillsRegistration
from .profile_fields import PROFILE_SECTIONS


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("full_name", "reg_number", "client_type", "gender", "branch", "mobile_telephone", "is_active")
    list_filter = ("is_active", "client_type", "gender", "branch", "savings_frequency")
    readonly_fields = ("created_at", "updated_at", "is_active", "status_changed_at", "status_changed_by")
    fieldsets = tuple((title, {"fields": fields}) for title, fields in PROFILE_SECTIONS) + (
        ("Client status", {"fields": ("is_active", "status_changed_at", "status_changed_by")}),
        ("Photo and record dates", {"fields": ("picture", "created_at", "updated_at")}),
    )
    search_fields = ("full_name", "reg_number", "email", "mobile_telephone")


@admin.register(SevenHillsRegistration)
class SevenHillsRegistrationAdmin(admin.ModelAdmin):
    list_display = ("full_name", "registration_date", "telephone_1", "email")
    list_filter = ("registration_date", "gender", "marital_status")
    search_fields = ("full_name", "telephone_1", "email")
