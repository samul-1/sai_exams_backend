# Generated by Django 3.1.7 on 2021-03-04 14:39

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('jsplatform', '0007_auto_20210304_1437'),
    ]

    operations = [
        migrations.RenameField(
            model_name='submission',
            old_name='eligible',
            new_name='is_eligible',
        ),
    ]
