# Generated by Django 3.1.7 on 2021-04-11 09:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='course',
            field=models.CharField(blank=True, choices=[('a', 'Corso A'), ('b', 'Corso B'), ('c', 'Corso C')], max_length=1, null=True),
        ),
    ]
