from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from api.v1.selectors import children_for_user
from api.v1.serializers import ChildPhotoUploadSerializer, ChildSerializer
from apps.child.models import ChildProfilePicture


class ChildViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ChildSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["full_name", "preferred_name", "district", "residence"]
    ordering_fields = ["id", "full_name"]
    ordering = ["id"]

    def get_queryset(self):
        return children_for_user(self.request.user, self.request.query_params.get("scope", ""))

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def photos(self, request, pk=None):
        child = self.get_object()
        serializer = ChildPhotoUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ChildProfilePicture.objects.filter(child=child, is_current=True).update(is_current=False)
        photo = serializer.save(child=child, is_current=True)
        return Response(ChildPhotoUploadSerializer(photo).data, status=status.HTTP_201_CREATED)
