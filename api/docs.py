from django.http import HttpResponse
from django.template.loader import get_template
from django.urls import include, path
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

API_DESCRIPTION = """
The Pendeza Connect API powers mobile and partner experiences for sponsorship,
client services, loans, payments, and programme operations.

### Authentication
Most endpoints require a JWT access token from `POST /api/v1/auth/login/`.

```http
Authorization: Bearer token
```

Refresh an expired access token with `POST /api/v1/auth/token/refresh/`.

### Base URL
All version 1 endpoints are relative to `/api/v1/` on the current host.
"""

api_patterns = [path("api/v1/", include("api.v1.urls"))]

schema_view = get_schema_view(
    openapi.Info(
        title="Pendeza Connect API",
        default_version="v1",
        description=API_DESCRIPTION,
        contact=openapi.Contact(name="Pendeza Connect"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
    patterns=api_patterns,
)


@require_GET
@cache_page(300)
def documentation_home(request):
    template = get_template("api/docs_home.html")
    content = template.render({"request": request})
    return HttpResponse(content)
