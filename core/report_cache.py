"""Short-lived data snapshots; authentication and HTML rendering stay uncached."""

import hashlib
import inspect
import json
import logging
from copy import deepcopy
from functools import wraps
from uuid import uuid4

from django.conf import settings
from django.core.cache import cache
from django.db.models import Model
from django.http import HttpResponse
from django.utils import timezone

logger = logging.getLogger(__name__)
REPORT_FILTER_KEYS = {"start_date", "end_date", "status", "client", "loan_product", "loan_officer", "q"}


def invalidate_report_cache(domain):
    """Rotate a domain's generation without scanning or flushing shared Redis."""
    try:
        cache.set(f"report-generation:{domain}", uuid4().hex, timeout=None)
    except Exception:
        logger.warning("Could not invalidate %s report cache", domain, exc_info=True)


def _json_value(value):
    return str(value.pk) if isinstance(value, Model) else str(value)


def report_snapshot(domain, name, parameters, build):
    ttl = getattr(settings, "REPORT_CACHE_TTL", 300)
    if ttl <= 0:
        return build()
    try:
        generation = cache.get(f"report-generation:{domain}", "initial")
        payload = json.dumps(parameters, sort_keys=True, default=_json_value)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        key = f"report:v1:{domain}:{generation}:{timezone.localdate()}:{name}:{digest}"
        snapshot = cache.get(key)
        if snapshot is not None:
            return deepcopy(snapshot)
    except Exception:
        logger.warning("Could not read %s report cache", domain, exc_info=True)
        return build()

    result = build()
    if result is not None:
        try:
            cache.set(key, result, timeout=ttl)
        except Exception:
            logger.warning("Could not store %s report cache", domain, exc_info=True)
    # Some consumers format dates and add columns in place. Never share those
    # mutations with another report, even with a reference-based cache backend.
    return deepcopy(result)


def cached_report(domain):
    def decorate(build):
        signature = inspect.signature(build)

        @wraps(build)
        def wrapped(*args, **kwargs):
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            parameters = dict(bound.arguments)
            if "filters" in parameters:
                parameters["filters"] = {
                    key: _json_value(value)
                    for key, value in parameters["filters"].items()
                    if key in REPORT_FILTER_KEYS and value not in (None, "")
                }
            return report_snapshot(domain, build.__name__, parameters, lambda: build(*args, **kwargs))

        return wrapped
    return decorate


def cached_chart(domain):
    """Cache successful JSON only. Place inside authorization decorators."""
    def decorate(view):
        @wraps(view)
        def wrapped(request):
            if request.method != "GET":
                return view(request)
            response = None

            def build():
                nonlocal response
                response = view(request)
                if response.status_code == 200:
                    return response.content, response["Content-Type"]
                return None

            data = report_snapshot(domain, view.__name__, dict(request.GET.lists()), build)
            if data is None:
                return response
            return HttpResponse(data[0], content_type=data[1])

        return wrapped
    return decorate
