from rest_framework import permissions

from api.v1.selectors import is_internal_user, linked_client_id, linked_sponsor_id


class IsInternalUser(permissions.BasePermission):
    message = "This endpoint is only available to staff accounts."

    def has_permission(self, request, view):
        return is_internal_user(request.user)


class IsLinkedClientOrInternal(permissions.BasePermission):
    message = "You can only access your linked client record."

    def has_object_permission(self, request, view, obj):
        return is_internal_user(request.user) or obj.pk == linked_client_id(request.user)


class IsLinkedSponsorOrInternal(permissions.BasePermission):
    message = "You can only access your linked sponsor record."

    def has_object_permission(self, request, view, obj):
        return is_internal_user(request.user) or obj.pk == linked_sponsor_id(request.user)
