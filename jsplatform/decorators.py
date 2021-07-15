def exam_participation_and_current_question_required(view_func):
    def wrapper(request, *args, **kwargs):
        exam = get_object_or_404(self.get_queryset(), pk=kwargs.pop("pk"))
        user = request.user
        if exam.closed:
            return Response(
                status=status.HTTP_410_GONE,
                data={"message": constants.MSG_EXAM_OVER},
            )

        try:
            exam_progress = ExamProgress.objects.get(user=user, exam=exam)
        except ExamProgress.DoesNotExist:
            return Response(status=status.HTTP_403_FORBIDDEN)

        current_question = exam_progress.current_item

        if not isinstance(current_question, Question):
            return Response(status=status.HTTP_400_BAD_REQUEST)

        return view_func(request, *args, **kwargs)

    return wrapper
