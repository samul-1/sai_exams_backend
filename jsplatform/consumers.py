import json

from channels.db import database_sync_to_async
from channels.exceptions import StopConsumer
from channels.generic.websocket import AsyncWebsocketConsumer
from users.models import User

from .models import Exam


class ExamLockConsumer(AsyncWebsocketConsumer):
    """
    A consumer used to guarantee mutual exclusion when editing exams
    """

    async def connect(self):
        self.exam_id = self.scope["url_route"]["kwargs"]["exam_id"]
        self.user = self.scope["user"]
        self.group_name = "exam_%s" % self.exam_id

        # check whether someone else is editing this exam
        who_locked = await self.who_locked(self.exam_id)
        if who_locked is not None and who_locked is not self.user:
            await self.close()
            return

        # join room group
        await self.channel_layer.group_add(self.group_name, self.channel_name)

        # lock exam
        await self.lock_exam(self.exam_id)
        print("locked")

        await self.accept()

    async def disconnect(self, close_code):
        print("unlocked")
        who_locked = await self.who_locked(self.exam_id)
        if who_locked == self.user:
            await self.unlock_exam(self.exam_id)

    @database_sync_to_async
    def who_locked(self, exam_id):
        exam = Exam.objects.get(pk=exam_id)
        return exam.locked_by

    @database_sync_to_async
    def lock_exam(self, exam_id):
        exam = Exam.objects.get(pk=exam_id)
        exam.locked_by = self.scope["user"]
        exam.save()

    @database_sync_to_async
    def unlock_exam(self, exam_id):
        exam = Exam.objects.get(pk=exam_id)
        exam.locked_by = None
        exam.save()
