from rest_framework import filters


class TeacherOrOwnedOnly(filters.BaseFilterBackend):
    """
    If the requesting user isn't a teacher, filter queryset to their own
    objects only
    """

    def filter_queryset(self, request, queryset, view):
        if not request.user.is_teacher:
            return queryset.filter(user=request.user)
        return queryset
