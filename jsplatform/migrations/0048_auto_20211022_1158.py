# Generated by Django 3.1.13 on 2021-10-22 09:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jsplatform', '0047_examprogressexercisesthroughmodel_draft_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='examprogressexercisesthroughmodel',
            name='seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='examprogressquestionsthroughmodel',
            name='seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
