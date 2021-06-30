from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsTeacherOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_anonymous and request.user.is_teacher:
            return True

        return request.method in SAFE_METHODS


class TeachersOnly(BasePermission):
    def has_permission(self, request, view):
        return not request.user.is_anonymous and request.user.is_teacher


class IsTeacherOrWriteOnly(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_anonymous and request.user.is_teacher:
            return True

        return request.method == "POST"
