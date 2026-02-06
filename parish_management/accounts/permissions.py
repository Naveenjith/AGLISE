from rest_framework.permissions import BasePermission

class IsAdminUser(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.role == "ADMIN"
        )

class IsChurchUser(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.role == "CHURCH" and
            request.user.church is not None and
            request.user.church.is_active
        )
    
class IsMemberUser(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.role == "USER" and
            hasattr(request.user, "member") and
            request.user.member is not None
        )

class IsChurchAuthenticated(BasePermission):
    """
    Church user can be active OR inactive.
    Used for login, package listing, subscription.
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.role == "CHURCH" and
            request.user.church is not None
        )
