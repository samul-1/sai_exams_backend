import json

from channels.db import database_sync_to_async
from channels.exceptions import StopConsumer
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from users.models import User

from .models import Exam


class ExamListConsumer(AsyncWebsocketConsumer):
    """
    A consumer used to send updates for when an exam gets locked or unlocked
    """

    async def connect(self):
        self.user = self.scope["user"]

        if self.user == AnonymousUser():
            await self.close()
            return

        await self.accept()
        self.group_name = "exam_list"

        # subscribe to exam list group to receive updates
        await self.channel_layer.group_add(self.group_name, self.channel_name)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        text_data_json = text_data
        action = text_data_json["action"]

        if action == "lock":
            await self.broadcast_lock(text_data_json["id"], text_data_json["by"])
        elif action == "unlock":
            await self.broadcast_unlock(text_data_json["id"])
        else:
            raise Exception("unknown command")

    async def broadcast_lock(self, exam_id, locked_by):
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "exam.lock",
                "exam_id": exam_id,
                "by": locked_by,
            },
        )

    async def broadcast_unlock(self, exam_id):
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "exam.unlock",
                "exam_id": exam_id,
            },
        )
        # todo send new updated data for the exam

    """
    Handlers
    """

    async def exam_lock(self, event):
        if not await self.in_user_scope(event["exam_id"]):
            # exam isn't visible to user; don't send them anything
            return

        await self.send(
            text_data=json.dumps(
                {
                    "msg_type": "lock",
                    "exam_id": event["exam_id"],
                    "by": event["by"],
                }
            ),
        )

    async def exam_unlock(self, event):
        if not await self.in_user_scope(event["exam_id"]):
            # exam isn't visible to user; don't send them anything
            return

        await self.send(
            text_data=json.dumps(
                {
                    "msg_type": "unlock",
                    "exam_id": event["exam_id"],
                }
            ),
        )

    @database_sync_to_async
    def in_user_scope(self, exam_id):
        """
        Returns True if the given exam is visible to the scope user;
        False otherwise
        """
        exam = Exam.objects.get(pk=exam_id)
        return exam.created_by == self.user or self.user in exam.allowed_teachers.all()


class ExamLockConsumer(AsyncWebsocketConsumer):
    """
    A consumer used to guarantee mutual exclusion when editing exams
    """

    async def connect(self):
        """
        Upon connection to this consumer, the relevant exam gets locked by the
        connecting user
        """
        self.exam_id = self.scope["url_route"]["kwargs"]["exam_id"]
        self.user = self.scope["user"]
        self.group_name = "exam_%s" % self.exam_id

        if self.user == AnonymousUser():
            await self.close()
            return

        # check whether someone else is editing this exam
        who_locked = await self.who_locked(self.exam_id)
        if who_locked is not None and who_locked != self.user:
            # exam already locked by someone else
            await self.close()
            return

        # join room group
        await self.channel_layer.group_add(self.group_name, self.channel_name)

        await self.lock_exam(self.exam_id)
        await self.accept()

    async def disconnect(self, close_code):
        who_locked = await self.who_locked(self.exam_id)
        if who_locked == self.user:
            await self.unlock_exam(self.exam_id)

        # broadcast a kill signal to handle the case where the user has multiple
        # tabs or windows open
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "kill.connection",
            },
        )

        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def kill_connection(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "msg_type": "exit",
                }
            ),
        )

    @database_sync_to_async
    def who_locked(self, exam_id):
        try:
            exam = Exam.objects.get(pk=exam_id)
            return exam.locked_by
        except Exam.DoesNotExist:
            return None

    @database_sync_to_async
    def lock_exam(self, exam_id):
        try:
            exam = Exam.objects.get(pk=exam_id)
            exam.locked_by = self.scope["user"]
            exam.save()
        except Exam.DoesNotExist:
            pass

    @database_sync_to_async
    def unlock_exam(self, exam_id):
        try:
            exam = Exam.objects.get(pk=exam_id)
            exam.locked_by = None
            exam.save()
        except Exam.DoesNotExist:
            pass
