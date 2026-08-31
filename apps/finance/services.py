from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import ExtractYear

from apps.finance.models import ChildPayments, Payment, StaffPayments, SupportProgram
from apps.sponsor.models import Sponsor, SponsorshipType

REAL_SUPPORT_PROGRAMS = SupportProgram.REAL_SUPPORT_CODES
PORTAL_PAYMENT_CATEGORIES = (
    {
        "key": "child-support",
        "label": "Child Support",
        "codes": (SupportProgram.CHILD_SUPPORT, SupportProgram.CHILD_CO_SUPPORT),
        "icon": "fas fa-child",
        "description": "Payments connected to child sponsorship.",
    },
    {
        "key": "family-support",
        "label": "Family Support",
        "codes": (SupportProgram.FAMILY_SUPPORT, SupportProgram.FAMILY_CO_SUPPORT),
        "icon": "fas fa-home",
        "description": "Family full support and family co support gifts.",
    },
    {
        "key": "general-support",
        "label": "General Support",
        "codes": (SupportProgram.GENERAL_SUPPORT,),
        "icon": "fas fa-hands-helping",
        "description": "Unrestricted general support gifts.",
    },
    {
        "key": "staff-support",
        "label": "Staff Support",
        "codes": (SupportProgram.STAFF_SUPPORT,),
        "icon": "fas fa-user-tie",
        "description": "Payments connected to staff sponsorship.",
    },
    {
        "key": "one-time-donation",
        "label": "One-time Donation",
        "codes": (SupportProgram.ONE_TIME_DONATION,),
        "icon": "fas fa-gift",
        "description": "One-time gifts outside recurring sponsorship.",
    },
)


def get_active_report_sponsors():
    return Sponsor.objects.active_real_supporters().with_report_related().order_by("id")


def get_departed_report_sponsors():
    return Sponsor.objects.departed_real_supporters().with_report_related().order_by("id")


def get_active_sponsors_count():
    return get_active_report_sponsors().count()


def get_departed_sponsors_count():
    return get_departed_report_sponsors().count()


def get_real_support_payments():
    return Payment.objects.real_support_payments().with_related().order_by("-payment_date")


def get_one_time_only_donors():
    return Sponsor.objects.one_time_only_donors().order_by("id")


def get_child_payment_sponsors():
    return Sponsor.objects.active().child_sponsors().order_by("id")


def get_staff_payment_sponsors():
    return Sponsor.objects.active().staff_sponsors().order_by("id")


def get_general_payment_sponsors():
    return Sponsor.objects.active().filter(Q(is_family_supporter=True) | Q(is_general_donor=True)).order_by("id")


def get_or_create_program(code):
    label = dict(SupportProgram.PROGRAM_CHOICES).get(code, code.replace("_", " ").title())
    program, _ = SupportProgram.objects.get_or_create(
        code=code,
        defaults={"name": label, "is_active": True},
    )
    return program


def sync_child_payment_to_unified(legacy_payment):
    sponsor = legacy_payment.sponsor
    sponsor.is_child_sponsor = True
    sponsor.save(update_fields=["is_child_sponsor", "updated_at"])
    code = (
        SupportProgram.CHILD_CO_SUPPORT
        if sponsor.sponsorship_type == SponsorshipType.CHILD_CO_SUPPORT
        else SupportProgram.CHILD_SUPPORT
    )
    return Payment.objects.update_or_create(
        source_model="ChildPayments",
        source_id=legacy_payment.id,
        defaults={
            "sponsor": sponsor,
            "program": get_or_create_program(code),
            "child": legacy_payment.child,
            "staff": None,
            "amount": legacy_payment.amount,
            "payment_date": legacy_payment.payment_date,
            "notes": f"Legacy child payment: {legacy_payment.month} {legacy_payment.payment_year}",
        },
    )


def sync_staff_payment_to_unified(legacy_payment):
    sponsor = legacy_payment.sponsor
    sponsor.is_staff_sponsor = True
    sponsor.save(update_fields=["is_staff_sponsor", "updated_at"])
    return Payment.objects.update_or_create(
        source_model="StaffPayments",
        source_id=legacy_payment.id,
        defaults={
            "sponsor": sponsor,
            "program": get_or_create_program(SupportProgram.STAFF_SUPPORT),
            "child": None,
            "staff": legacy_payment.staff,
            "amount": legacy_payment.amount,
            "payment_date": legacy_payment.payment_date,
            "notes": f"Legacy staff payment: {legacy_payment.month} {legacy_payment.payment_year}",
        },
    )


def sync_donor_payment_to_unified(legacy_payment, sponsor):
    sponsor.is_one_time_donor = True
    sponsor.save(update_fields=["is_one_time_donor", "updated_at"])
    return Payment.objects.update_or_create(
        source_model="DonorPayment",
        source_id=legacy_payment.id,
        defaults={
            "sponsor": sponsor,
            "program": get_or_create_program(SupportProgram.ONE_TIME_DONATION),
            "child": None,
            "staff": None,
            "amount": legacy_payment.amount,
            "payment_date": legacy_payment.payment_date,
            "notes": "Legacy donor payment recorded as one-time donation",
        },
    )


def apply_sponsor_flags_for_program(sponsor, program):
    code = program.code
    updates = []

    if code in (SupportProgram.FAMILY_SUPPORT, SupportProgram.FAMILY_CO_SUPPORT):
        sponsor.is_family_supporter = True
        updates.append("is_family_supporter")
    elif code == SupportProgram.GENERAL_SUPPORT:
        sponsor.is_general_donor = True
        updates.append("is_general_donor")
    elif code == SupportProgram.ONE_TIME_DONATION:
        sponsor.is_one_time_donor = True
        updates.append("is_one_time_donor")
    elif code in (SupportProgram.CHILD_SUPPORT, SupportProgram.CHILD_CO_SUPPORT):
        sponsor.is_child_sponsor = True
        updates.append("is_child_sponsor")
    elif code == SupportProgram.STAFF_SUPPORT:
        sponsor.is_staff_sponsor = True
        updates.append("is_staff_sponsor")

    if updates:
        sponsor.save(update_fields=[*set(updates), "updated_at"])


def get_sponsor_total_paid(sponsor):
    result = Payment.objects.filter(sponsor=sponsor).aggregate(total=Sum("amount"))
    return result["total"] or 0


def get_sponsor_real_support_total(sponsor):
    result = Payment.objects.filter(
        sponsor=sponsor,
        program__code__in=REAL_SUPPORT_PROGRAMS,
    ).aggregate(total=Sum("amount"))

    return result["total"] or 0


def get_report_sponsors(include_departed=False):
    queryset = Sponsor.objects.real_sponsors_only().with_report_related()
    if include_departed:
        return queryset.order_by("id")
    return queryset.active().order_by("id")


def get_sponsor_portal_payment_summary(sponsor):
    payments = Payment.objects.with_related().filter(sponsor=sponsor)
    unsynced_child_payments = _unsynced_legacy_child_payments(sponsor)
    unsynced_staff_payments = _unsynced_legacy_staff_payments(sponsor)

    payment_categories = _portal_payment_categories(
        payments,
        unsynced_child_payments,
        unsynced_staff_payments,
    )
    other_support_codes = (
        SupportProgram.FAMILY_SUPPORT,
        SupportProgram.FAMILY_CO_SUPPORT,
        SupportProgram.GENERAL_SUPPORT,
    )
    legacy_child_total = _sum_amount(unsynced_child_payments)
    legacy_staff_total = _sum_amount(unsynced_staff_payments)
    recent_payments = _combined_recent_payments(
        payments,
        unsynced_child_payments,
        unsynced_staff_payments,
    )

    return {
        "has_unified_payments": payments.exists(),
        "total_payment_amount": _sum_amount(payments) + legacy_child_total + legacy_staff_total,
        "real_support_total": (_sum_amount(payments.real_support_payments()) + legacy_child_total + legacy_staff_total),
        "other_payment_total": _sum_amount(payments.filter(program__code__in=other_support_codes)),
        "one_time_payment_total": _sum_amount(payments.one_time_donations()),
        "payment_categories": payment_categories,
        "program_payment_totals": payment_categories,
        "recent_payments": recent_payments,
    }


def get_legacy_sponsor_portal_payment_summary(sponsor):
    child_payments = ChildPayments.objects.select_related("child").filter(
        sponsor=sponsor,
        is_valid=True,
    )
    staff_payments = StaffPayments.objects.select_related("staff").filter(
        sponsor=sponsor,
        is_valid=True,
    )
    child_total = _sum_amount(child_payments)
    staff_total = _sum_amount(staff_payments)
    recent_payments = sorted(
        list(child_payments.order_by("-payment_date", "-id")[:5])
        + list(staff_payments.order_by("-payment_date", "-id")[:5]),
        key=lambda payment: (payment.payment_date, payment.id),
        reverse=True,
    )[:5]

    return {
        "has_unified_payments": False,
        "total_payment_amount": child_total + staff_total,
        "real_support_total": child_total + staff_total,
        "other_payment_total": Decimal("0"),
        "one_time_payment_total": Decimal("0"),
        "payment_categories": _legacy_portal_payment_categories(child_total),
        "program_payment_totals": _legacy_portal_payment_categories(child_total),
        "recent_payments": recent_payments,
    }


def empty_sponsor_portal_payment_summary():
    return {
        "has_unified_payments": False,
        "total_payment_amount": Decimal("0"),
        "real_support_total": Decimal("0"),
        "other_payment_total": Decimal("0"),
        "one_time_payment_total": Decimal("0"),
        "payment_categories": _empty_portal_payment_categories(),
        "program_payment_totals": [],
        "recent_payments": [],
    }


def get_sponsor_program_payment_report_context(sponsor, category_key):
    category = get_portal_payment_category(category_key)
    payments = Payment.objects.none()
    total_amount = Decimal("0")
    payment_count = 0
    latest_payment = None
    yearly_totals = []

    if sponsor is not None:
        payments = (
            Payment.objects.with_related()
            .filter(sponsor=sponsor, program__code__in=category["codes"])
            .order_by("-payment_date", "-id")
        )
        total_amount = _sum_amount(payments)
        payment_count = payments.count()
        latest_payment = payments.first()
        yearly_totals = (
            payments.annotate(year=ExtractYear("payment_date"))
            .values("year")
            .annotate(total=Sum("amount"))
            .order_by("-year")
        )

    return {
        "sponsor": sponsor,
        "payments": payments,
        "total_amount": total_amount,
        "payment_count": payment_count,
        "latest_payment": latest_payment,
        "yearly_totals": yearly_totals,
        "report_title": f"{category['label']} Payment Report",
        "report_subtitle": category["description"],
        "beneficiary_label": category["label"],
        "report_kind": "unified",
        "program_category": category,
    }


def get_portal_payment_category(category_key):
    for category in PORTAL_PAYMENT_CATEGORIES:
        if category["key"] == category_key:
            return category
    return PORTAL_PAYMENT_CATEGORIES[0]


def _sum_amount(queryset):
    return queryset.aggregate(total=Sum("amount"))["total"] or Decimal("0")


def _portal_payment_categories(
    payments,
    legacy_child_payments=None,
    legacy_staff_payments=None,
):
    categories = []
    for category in PORTAL_PAYMENT_CATEGORIES:
        amount = _sum_amount(payments.filter(program__code__in=category["codes"]))
        has_legacy_payments = False
        if category["key"] == "child-support" and legacy_child_payments is not None:
            legacy_amount = _sum_amount(legacy_child_payments)
            amount += legacy_amount
            has_legacy_payments = legacy_amount > 0
        if category["key"] == "staff-support" and legacy_staff_payments is not None:
            legacy_amount = _sum_amount(legacy_staff_payments)
            amount += legacy_amount
            has_legacy_payments = legacy_amount > 0
        categories.append(
            {
                **category,
                "amount": amount,
                "has_payments": amount > 0,
                "has_legacy_payments": has_legacy_payments,
            }
        )
    return categories


def _legacy_portal_payment_categories(child_total):
    categories = []
    for category in PORTAL_PAYMENT_CATEGORIES:
        amount = child_total if category["key"] == "child-support" else Decimal("0")
        categories.append({**category, "amount": amount, "has_payments": amount > 0})
    return categories


def _empty_portal_payment_categories():
    return [{**category, "amount": Decimal("0"), "has_payments": False} for category in PORTAL_PAYMENT_CATEGORIES]


def _unsynced_legacy_child_payments(sponsor):
    synced_ids = Payment.objects.filter(
        sponsor=sponsor,
        source_model="ChildPayments",
        source_id__isnull=False,
    ).values("source_id")
    return (
        ChildPayments.objects.select_related("child").filter(sponsor=sponsor, is_valid=True).exclude(id__in=synced_ids)
    )


def _unsynced_legacy_staff_payments(sponsor):
    synced_ids = Payment.objects.filter(
        sponsor=sponsor,
        source_model="StaffPayments",
        source_id__isnull=False,
    ).values("source_id")
    return (
        StaffPayments.objects.select_related("staff").filter(sponsor=sponsor, is_valid=True).exclude(id__in=synced_ids)
    )


def _combined_recent_payments(payments, child_payments, staff_payments):
    recent_payments = sorted(
        list(payments.order_by("-payment_date", "-id")[:8])
        + list(child_payments.order_by("-payment_date", "-id")[:8])
        + list(staff_payments.order_by("-payment_date", "-id")[:8]),
        key=lambda payment: (payment.payment_date, payment.id),
        reverse=True,
    )
    return recent_payments[:5]
