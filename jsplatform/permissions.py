from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsTeacherOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_teacher:
            return True

        return request.method in SAFE_METHODS
