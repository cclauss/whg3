# Generated by Django 4.1.7 on 2023-07-22 09:23

import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('places', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='placegeom',
            name='s2',
            field=django.contrib.postgres.fields.ArrayField(base_field=models.BigIntegerField(), null=True, size=None),
        ),
    ]