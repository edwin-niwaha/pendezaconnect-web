"""Invalidate reporting snapshots only after source changes commit."""

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core.report_cache import invalidate_report_cache

APP_DOMAINS = {
    "loans": ("loans",),
    "client": ("loans",),
    "auth": ("loans",),
    "child": ("sponsorship",),
    "sponsor": ("sponsorship",),
    "staff": ("sponsorship",),
    "sponsorship": ("sponsorship",),
    "finance": ("sponsorship",),
    "products": ("inventory",),
    "sales": ("inventory",),
}


@receiver(post_save, dispatch_uid="report_cache_saved")
@receiver(post_delete, dispatch_uid="report_cache_deleted")
def source_changed(sender, using, **kwargs):
    for domain in APP_DOMAINS.get(sender._meta.app_label, ()):
        transaction.on_commit(lambda domain=domain: invalidate_report_cache(domain), using=using)
