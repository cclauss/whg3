# Generated by Django 2.2.13 on 2020-12-17 23:48

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('areas', '0008_country'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Country',
        ),
    ]