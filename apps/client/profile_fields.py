"""Canonical client profile fields shared by forms, reports, and exports."""

PROFILE_SECTIONS = (
    ("Identity", ("reg_number", "full_name", "client_type", "gender", "date_of_birth", "registration_date", "branch")),
    ("Contact and address", ("mobile_telephone", "email", "village", "current_address")),
    (
        "Work and personal details",
        (
            "workplace",
            "occupation",
            "employment_status",
            "employment_sector",
            "marital_status",
            "highest_education_level",
        ),
    ),
    ("Next of kin", ("next_of_kin_name", "next_of_kin_phone", "next_of_kin_relationship")),
    (
        "Savings and interests",
        ("referred_by", "savings_goal", "services_interested", "savings_frequency", "minimum_savings_amount"),
    ),
    (
        "Group details",
        (
            "group_member_count",
            "group_objective",
            "group_savings_cycle_months",
            "group_chairperson",
            "group_secretary",
            "group_treasurer",
        ),
    ),
)
PROFILE_FIELDS = tuple(field for _, fields in PROFILE_SECTIONS for field in fields)


def profile_sections(client):
    sections = []
    for title, fields in PROFILE_SECTIONS:
        values = []
        for name in fields:
            field = client._meta.get_field(name)
            display = getattr(client, f"get_{name}_display", None)
            value = display() if display else getattr(client, name)
            if hasattr(value, "strftime"):
                value = value.strftime("%d/%m/%Y")
            values.append((str(field.verbose_name).capitalize(), value if value not in (None, "") else "Not recorded"))
        sections.append((title, values))
    return sections
