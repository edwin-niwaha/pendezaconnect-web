"""Snapshot reports sharing Aging's cohort and accounting rules."""

from decimal import Decimal

from .forms import LoanAgingReportFilterForm
from .services.reporting import ReportColumn, aging_report_rows, aging_report_summary


class RiskReportFilterForm(LoanAgingReportFilterForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop("arrears_over")


DETAIL_COLUMNS = [
    ReportColumn("client", "Client"),
    ReportColumn("gender", "Gender"),
    ReportColumn("disbursement_date", "Disbursed On"),
    ReportColumn("maturity_date", "Maturity"),
    ReportColumn("outstanding_principal", "Principal Bal.", "right", True),
    ReportColumn("outstanding_interest", "Interest Bal.", "right", True),
    ReportColumn("outstanding_penalties", "Penalties", "right", True),
    ReportColumn("outstanding_amount", "Total Balance", "right", True),
    ReportColumn("overdue_amount", "Overdue", "right", True),
    ReportColumn("days_in_arrears", "Days Arrears", "right"),
    ReportColumn("last_repayment_date", "Last Payment"),
]
DUE_COLUMNS = [
    ReportColumn("client", "Client"),
    ReportColumn("gender", "Gender"),
    ReportColumn("relevant_due_date", "Relevant Due Date"),
    ReportColumn("maturity_date", "Maturity"),
    ReportColumn("due_on_date", "Due on Selected Date", "right", True),
    ReportColumn("overdue_before_date", "Overdue Before Selected Date", "right", True),
    ReportColumn("outstanding_amount", "Total Balance", "right", True),
    ReportColumn("days_in_arrears", "Days Arrears", "right"),
]
PAR_COLUMNS = [
    ReportColumn("bucket", "Risk Threshold"),
    ReportColumn("loan_count", "Loans", "right"),
    ReportColumn("client_count", "Clients", "right"),
    ReportColumn("principal_at_risk", "Principal at Risk", "right", True),
    ReportColumn("par_percent", "PAR %", "right"),
]


def principal_risk_bands(rows):
    denominator = sum((r["outstanding_principal"] for r in rows), Decimal("0"))
    bands = []
    for days in (0, 30, 60, 90, 120, 180):
        affected = [r for r in rows if r["days_in_arrears"] > days]
        principal = sum((r["outstanding_principal"] for r in affected), Decimal("0"))
        percentage = principal / denominator * 100 if denominator > 0 else Decimal("0")
        bands.append(
            {
                "bucket": f"PAR >{days}",
                "loan_count": len(affected),
                "client_count": len({r["borrower_id"] for r in affected}),
                "principal_at_risk": principal,
                "par_percent": f"{percentage:.2f}%",
            }
        )
    return bands


def due_rows(rows, as_of):
    result = []
    for row in rows:
        if row["maturity_date"] and row["maturity_date"] < as_of:
            category = "Past maturity"
        elif row["overdue_before_date"] > 0:
            category = "In arrears"
        elif row["due_on_date"] > 0:
            category = "Due on selected date"
        else:
            continue
        result.append(
            {**row, "category": category, "relevant_due_date": row["relevant_due_date"] or row["maturity_date"]}
        )
    return result


def risk_report_response(request, kind):
    from .views import _standard_report_response

    form = RiskReportFilterForm(request.GET)
    valid = form.is_valid()
    filters = dict(form.cleaned_data)
    # Do not silently accept the old assessment-date parameter.
    if kind == "due" and "date" in request.GET:
        form.add_error(None, "Use End date to select the assessment date.")
        valid = False
    cohort = aging_report_rows(filters) if valid else []
    titles = {
        "arrears": "Loan Arrears Report",
        "par": "Portfolio at Risk Report",
        "npl": "Non-Performing Loans Report",
        "due": "Due and Overdue Report",
        "defaulted": "Defaulted Loans Report",
        "outstanding": "Outstanding Loan Balances Report",
    }
    notes = {
        "defaulted": "Unpaid loans more than 90 days in arrears. Non-performing loans use 90 days or more.",
        "outstanding": (
            "All running loans with a remaining balance at End date, including current loans. "
            "Total balance includes principal, interest, and penalties."
        ),
        "arrears": (
            "Overdue is unpaid scheduled principal and interest. "
            "Total balance includes the remaining loan and penalties."
        ),
        "npl": "Unpaid loans at least 90 days in arrears, including partially paid loans.",
        "par": (
            "PAR uses outstanding principal. Thresholds overlap and must not be added. "
            "NPL uses 90+ days; PAR >90 is strictly over 90."
        ),
        "due": (
            "Due and overdue amounts exclude penalties. "
            "Total balance includes penalties. Past maturity takes priority."
        ),
    }
    rows = cohort
    group_by = "aging_bucket"
    columns = DETAIL_COLUMNS
    if kind in {"defaulted", "outstanding"}:
        columns = [DETAIL_COLUMNS[0], ReportColumn("reg_number", "Reg. No"), *DETAIL_COLUMNS[1:]]
    keys = [
        "outstanding_principal",
        "outstanding_interest",
        "outstanding_penalties",
        "outstanding_amount",
        "overdue_amount",
    ]
    if kind == "arrears":
        rows = [r for r in cohort if r["days_in_arrears"] > 0 and r["overdue_amount"] > 0]
    elif kind == "npl":
        rows = [r for r in cohort if r["days_in_arrears"] >= 90]
    elif kind == "defaulted":
        rows = [r for r in cohort if r["days_in_arrears"] > 90]
    elif kind == "outstanding":
        group_by = None
    elif kind == "due":
        rows = due_rows(cohort, filters["end_date"]) if valid else []
        columns, group_by = DUE_COLUMNS, "category"
        keys = ["due_on_date", "overdue_before_date", "outstanding_amount"]
    summary = aging_report_summary(rows)
    cards = []

    def card(label, value, unit="count"):
        cards.append({"label": label, "value": value, "unit": unit})

    def amount(key):
        return sum((r[key] for r in rows), Decimal("0"))

    if kind == "par":
        card("Portfolio loans", len(cohort))
        card("Active clients", summary["active_borrowers"])
        card("Outstanding principal", amount("outstanding_principal"), "money")
        card("Principal at risk >30", summary["principal_over_30"], "money")
        card("PAR >30", summary["par_over_30_percent"], "percent")
        rows, columns, keys, group_by = principal_risk_bands(cohort), PAR_COLUMNS, [], None
    elif kind == "due":
        card("Affected clients", summary["active_borrowers"])
        for category in ("Due on selected date", "In arrears", "Past maturity"):
            subset = [r for r in rows if r["category"] == category]
            card(category + " loans", len(subset))
            card(
                category + " unpaid",
                sum(
                    (
                        r["outstanding_amount"]
                        if category == "Past maturity"
                        else r["due_on_date"] + r["overdue_before_date"]
                        for r in subset
                    ),
                    Decimal("0"),
                ),
                "money",
            )
    else:
        loan_labels = {
            "arrears": "Overdue loans",
            "npl": "NPL loans (90+ days)",
            "defaulted": "Defaulted loans (>90 days)",
            "outstanding": "Loans with balances",
        }
        card(loan_labels[kind], len(rows))
        client_labels = {"arrears": "Clients in arrears", "outstanding": "Active clients"}
        card(client_labels.get(kind, "Affected clients"), summary["active_borrowers"])
        card("Female", summary["female_borrowers"])
        card("Male", summary["male_borrowers"])
        if summary["unknown_gender_borrowers"]:
            card("Gender not recorded", summary["unknown_gender_borrowers"])
        card("Outstanding principal", amount("outstanding_principal"), "money")
        if kind == "outstanding":
            card("Interest balance", amount("outstanding_interest"), "money")
            card("Penalties", amount("outstanding_penalties"), "money")
        card("Overdue", amount("overdue_amount"), "money")
        card("Total balance", amount("outstanding_amount"), "money")
    if kind != "par":
        rows.sort(key=lambda r: (-r["days_in_arrears"], -r["outstanding_amount"], r["client"]))
        for row in rows:
            for key in ("disbursement_date", "maturity_date", "last_repayment_date", "relevant_due_date"):
                if row.get(key):
                    row[key] = row[key].strftime("%d/%m/%Y")
    if valid:
        filters["export"] = request.GET.get("export", "").strip().lower()
    return _standard_report_response(
        request,
        titles[kind],
        f"{kind}_report.csv",
        columns,
        rows,
        keys,
        filters,
        group_by=group_by,
        compact_filters=True,
        filter_form=form,
        response_status=200 if valid else 400,
        extra_context={
            "risk_report": True,
            "summary_cards": cards,
            "report_note": notes[kind],
            "invalid_filters": not valid,
            "as_of": filters.get("end_date") if valid else None,
            "hide_table_totals": kind == "par",
            "loan_detail_links": kind != "par",
            "historical_closures": any(r["current_status"] == "closed" for r in cohort),
            "incomplete_penalty_history": any(r["penalty_history_incomplete"] for r in cohort),
        },
    )
