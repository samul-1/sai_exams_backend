from rest_framework import filters


class TeacherOrOwnedOnly(filters.BaseFilterBackend):
    """
    If the requesting user isn't a teacher, filter queryset to their own
    objects only
    """

    pass
    # def filter_queryset(self, request, queryset, view):
    #     if not request.user.is_teacher:
    #         return queryset.filter(
    #             user=request.user,
    #             exercise__id__in=request.user.assigned_exercises.all(),
    #         )
    #     return queryset


class TeacherOrAssignedOnly(filters.BaseFilterBackend):
    """
    If the requesting user isn't a teacher, filter queryset to their own
    objects only

    Works similar to TeacherOrOwnedOnly, but in this case the filtering is done on a
    many to many relationship
    """

    pass

    # def filter_queryset(self, request, queryset, view):
    #     if not request.user.is_teacher:
    #         # filter for exercises that have been assigned to the user
    #         return queryset.filter(id__in=request.user.assigned_exercises.all())
    #     return queryset
