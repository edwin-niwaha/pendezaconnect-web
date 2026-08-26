from rest_framework import permissions, viewsets
from rest_framework.response import Response
from django.core.cache import cache

from api.v1.selectors import dashboard_for_user


class DashboardViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        cache_key = f"mobile-dashboard:v1:user:{request.user.pk}"
        data = cache.get(cache_key)
        if data is None:
            data = dashboard_for_user(request.user)
            cache.set(cache_key, data, timeout=30)
        return Response(data)
