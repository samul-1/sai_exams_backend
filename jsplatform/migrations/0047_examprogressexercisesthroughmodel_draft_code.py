# Generated by Django 3.1.13 on 2021-10-21 19:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jsplatform', '0046_auto_20210723_1741'),
    ]

    operations = [
        migrations.AddField(
            model_name='examprogressexercisesthroughmodel',
            name='draft_code',
            field=models.TextField(blank=True),
        ),
    ]