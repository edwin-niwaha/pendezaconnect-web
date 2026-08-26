from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from api.v1.selectors import staff_for_user
from api.v1.serializers import StaffSerializer
from api.v1.uploads import validate_image_upload


class StaffViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StaffSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["first_name", "last_name", "email", "job_title"]
    ordering_fields = ["id", "first_name", "last_name", "job_title"]
    ordering = ["id"]

    def get_queryset(self):
        return staff_for_user(self.request.user, self.request.query_params.get("scope", ""))

    @action(detail=True, methods=["post", "delete"], parser_classes=[MultiPartParser, FormParser])
    def photos(self, request, pk=None):
        staff = self.get_object()

        if request.method == "DELETE":
            staff.picture = None
            staff.save(update_fields=["picture", "updated_at"])
            return Response(self.get_serializer(staff).data, status=status.HTTP_200_OK)

        picture = request.FILES.get("picture")
        if not picture:
            return Response({"picture": ["No image file was submitted."]}, status=status.HTTP_400_BAD_REQUEST)

        staff.picture = validate_image_upload(picture)
        staff.save(update_fields=["picture", "updated_at"])
        return Response(self.get_serializer(staff).data, status=status.HTTP_200_OK)
