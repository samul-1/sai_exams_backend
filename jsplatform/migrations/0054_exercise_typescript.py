# Generated by Django 3.1.14 on 2022-03-28 13:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jsplatform', '0053_auto_20211117_1344'),
    ]

    operations = [
        migrations.AddField(
            model_name='exercise',
            name='typescript',
            field=models.BooleanField(default=False),
        ),
    ]
