from django import template

register = template.Library()


@register.filter
def report_label(value):
    labels = {
        "paid_amount": "Paid", "outstanding_principal": "Principal balance",
        "outstanding_interest": "Interest balance", "outstanding_penalties": "Penalties",
        "outstanding_amount": "Total balance", "overdue_amount": "Overdue",
    }
    return labels.get(value, str(value).replace("_", " ").title())


@register.filter
def get_item(mapping, key):
    if not mapping:
        return None
    return mapping.get(key)


@register.simple_tag(takes_context=True)
def report_querystring(context, **kwargs):
    params = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = value
    return params.urlencode()
