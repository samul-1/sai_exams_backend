# Generated by Django 3.1.13 on 2021-07-12 15:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jsplatform', '0037_auto_20210712_1731'),
    ]

    operations = [
        migrations.AddField(
            model_name='examprogress',
            name='is_initialized',
            field=models.BooleanField(default=False),
        ),
    ]
